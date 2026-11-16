"""Subtitle envelopes are immutable; only explicitly parsed dialogue spans change."""
from dataclasses import dataclass
from pathlib import Path
import re
import zipfile
import io

SUPPORTED = {'.srt', '.ass', '.ssa', '.vtt', '.lrc', '.txt', '.md', '.docx', '.pdf'}
JAPANESE = re.compile(r'[\u3040-\u30ff\u3400-\u9fff]')
PROTECTED = re.compile(r'(\{[^{}]*\}|<[^>\n]+>|\\[Nnh]|`+[^`]*`+|https?://\S+|\[[^\]\n]{1,32}\]|^[^\s:：]{1,20}[:：])')

@dataclass
class Unit:
    start: int
    end: int
    source: str
    label: str

def decode(data, encoding='auto'):
    if encoding != 'auto':
        return data.decode(encoding)
    if data.startswith((b'\xff\xfe', b'\xfe\xff')):
        return data.decode('utf-16')
    try:
        return data.decode('utf-8-sig')
    except UnicodeDecodeError:
        pass
    from charset_normalizer import from_bytes
    best = from_bytes(data).best()
    if best and best.encoding in ('cp932', 'shift_jis', 'shift_jis_2004', 'utf_16_le', 'utf_16_be'):
        return str(best)
    try:
        return data.decode('cp932')
    except UnicodeDecodeError:
        if best and best.percent_chaos < 10:
            return str(best)
        raise ValueError('无法确定编码，请指定 UTF-8、UTF-16 或 CP932')

class TextDocument:
    def __init__(self, text, extension):
        self.text, self.extension = text, extension.lower()
        self.units, self.warnings = [], []
        self._parse()

    def add(self, start, end, label):
        value = self.text[start:end]
        if value.strip():
            self.units.append(Unit(start, end, value, label))

    def _parse(self):
        lines = [m for m in re.finditer(r'[^\r\n]*(?:\r\n|\r|\n|$)', self.text) if m.group()]
        ext = self.extension
        if ext in ('.srt', '.vtt'):
            if ext == '.vtt' and not self.text.lstrip('\ufeff').startswith('WEBVTT'):
                raise ValueError('VTT 缺少 WEBVTT 文件头')
            for block in re.finditer(r'[^\r\n]+(?:\r?\n(?!\r?\n)[^\r\n]+)*', self.text):
                content = block.group().splitlines()
                if ext == '.vtt' and content[0].startswith(('WEBVTT', 'NOTE', 'STYLE', 'REGION')):
                    continue
                ti = next((i for i, line in enumerate(content) if '-->' in line), None)
                if ti is None:
                    raise ValueError('字幕块缺少时间轴')
                timing = content[ti]
                if not re.fullmatch(r'\s*(?:\d{2}:)?\d{2}:\d{2}[.,]\d{3}\s+-->\s+(?:\d{2}:)?\d{2}:\d{2}[.,]\d{3}(?:\s+.*)?\s*', timing):
                    raise ValueError(f'非法字幕时间轴：{timing}')
                local = list(re.finditer(r'[^\r\n]+', block.group()))
                if ti + 1 >= len(local):
                    raise ValueError('字幕条目缺少正文')
                self.add(block.start() + local[ti+1].start(), block.start() + local[-1].end(), f'{content[0]} | {timing}')
        elif ext in ('.ass', '.ssa'):
            section, fields = '', []
            for match in lines:
                line = match.group().rstrip('\r\n')
                if line.strip().startswith('['):
                    section = line.strip().lower()
                elif section == '[events]' and line.lower().startswith('format:'):
                    fields = [f.strip().lower() for f in line.split(':', 1)[1].split(',')]
                    if not fields or fields[-1] != 'text':
                        raise ValueError('ASS Events Format 必须以 Text 结尾')
                elif section == '[events]' and line.lower().startswith('dialogue:'):
                    if not fields:
                        raise ValueError('ASS 缺少 Events Format')
                    parts = line.split(':', 1)[1].split(',', len(fields) - 1)
                    if len(parts) != len(fields):
                        raise ValueError('ASS 对话字段数不正确')
                    body = parts[-1]
                    if re.search(r'\{[^}]*\\p[1-9]', body):
                        self.warnings.append('ASS 绘图事件保持原样')
                        continue
                    start = parts[fields.index('start')] if 'start' in fields else ''
                    end = parts[fields.index('end')] if 'end' in fields else ''
                    self.add(match.start() + len(line) - len(body), match.start() + len(line), f'{start} → {end}')
        elif ext == '.lrc':
            for match in lines:
                line = match.group().rstrip('\r\n')
                tag = re.match(r'(?:\[\d+:\d{2}(?:[.:]\d{1,3})?\])+', line)
                if tag:
                    self.add(match.start() + tag.end(), match.start() + len(line), tag.group())
        else:
            fence = None
            for match in lines:
                line = match.group().rstrip('\r\n')
                if ext == '.md':
                    marker = re.match(r'\s*(`{3,}|~{3,})', line)
                    if marker:
                        if fence is None:
                            fence = marker.group(1)[0]
                        elif marker.group(1)[0] == fence:
                            fence = None
                        continue
                    if fence or re.match(r'^(?: {4}|\t|\s*\[[^]]+\]:|\s*<|\s*\|?[-: ]+\|)', line):
                        continue
                prefix = re.match(r'\s*(?:#{1,6}\s+|[-*+]\s+|\d+\.\s+|>\s*)?', line) if ext == '.md' else None
                self.add(match.start() + (prefix.end() if prefix else 0), match.start() + len(line), str(len(self.units) + 1))
        if ext in ('.srt', '.ass', '.ssa', '.vtt', '.lrc') and not self.units:
            raise ValueError('未找到可处理的字幕条目')

    def render(self, translations):
        if len(translations) != len(self.units):
            raise ValueError('译文条目数与原文不一致')
        pieces, position = [], 0
        for unit, translated in zip(self.units, translations):
            if not translated.strip():
                raise ValueError('不允许保存空译文')
            if self.extension in ('.srt', '.vtt', '.lrc', '.ass', '.ssa'):
                if PROTECTED.findall(unit.source) != PROTECTED.findall(translated):
                    raise ValueError('字幕格式标记发生变化，请保留控制标记')
                if '\n\n' in translated.replace('\r\n', '\n'):
                    raise ValueError('字幕正文不能含空行')
            pieces.extend((self.text[position:unit.start], translated))
            position = unit.end
        pieces.append(self.text[position:])
        output = ''.join(pieces)
        check = TextDocument(output, self.extension)
        if self.extension in ('.srt', '.vtt', '.lrc', '.ass', '.ssa') and [u.label for u in self.units] != [u.label for u in check.units]:
            raise ValueError('字幕结构校验失败')
        return output.encode('utf-8-sig' if self.extension in ('.ass', '.ssa') else 'utf-8')

class DocxDocument:
    def __init__(self, path):
        from lxml import etree
        self.original = Path(path).read_bytes()
        self.trees, self.nodes, self.units = {}, [], []
        self.warnings = ['DOCX 按文本 run 翻译保留格式；跨 run 句子可能影响连贯性。']
        with zipfile.ZipFile(io.BytesIO(self.original)) as archive:
            for name in archive.namelist():
                if re.fullmatch(r'word/(?:document|header\d+|footer\d+|footnotes|endnotes)\.xml', name):
                    tree = etree.fromstring(archive.read(name), parser=etree.XMLParser(resolve_entities=False))
                    self.trees[name] = tree
                    for node in tree.iter('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t'):
                        if node.text and node.text.strip():
                            self.nodes.append(node)
                            self.units.append(Unit(0, 0, node.text, f'{name} · {len(self.units)+1}'))

    def render(self, translations):
        from lxml import etree
        if len(translations) != len(self.nodes) or any(not t.strip() for t in translations):
            raise ValueError('DOCX 译文缺失')
        for node, value in zip(self.nodes, translations):
            node.text = value
            node.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
        buffer = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(self.original)) as original, zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as output:
            for entry in original.infolist():
                output.writestr(entry, etree.tostring(self.trees[entry.filename], xml_declaration=True, encoding='UTF-8', standalone=True) if entry.filename in self.trees else original.read(entry.filename))
        return buffer.getvalue()

def load_document(path, encoding='auto'):
    path = Path(path)
    if path.suffix.lower() == '.docx':
        return DocxDocument(path)
    if path.suffix.lower() == '.pdf':
        from pypdf import PdfReader
        text = '\n\n'.join(page.extract_text() or '' for page in PdfReader(path).pages)
        if not text.strip():
            raise ValueError('PDF 无可提取文字（可能是扫描版）；未启用 OCR')
        doc = TextDocument(text, '.txt')
        doc.warnings.append('PDF 输出为 TXT，不保留原页面排版。')
        return doc
    if path.suffix.lower() not in SUPPORTED:
        raise ValueError('不支持此文件类型')
    return TextDocument(decode(path.read_bytes(), encoding), path.suffix)

def text_parts(text, markdown=False):
    pattern = PROTECTED if not markdown else re.compile(r'(\{[^{}]*\}|<[^>\n]+>|`+[^`]*`+|!?\[|\]\([^)]*\)|https?://\S+|[*_~|]+)')
    return pattern.split(text)
