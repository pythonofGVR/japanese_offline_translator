"""Standalone translated-file editing, independent of the original or sidecar."""
import hashlib
from pathlib import Path
import re
from datetime import datetime

from .formats import decode, load_document, TextDocument
from .paths import atomic_write, read_json, write_json
from .quality import warnings

EDITABLE = {'.srt','.ass','.ssa','.vtt','.lrc','.txt','.md','.docx'}

class EditableFile:
    def __init__(self, path):
        self.path = Path(path).resolve()
        if self.path.suffix.lower() not in EDITABLE:
            raise ValueError('请选择字幕、TXT、Markdown 或 DOCX。PDF 的翻译结果请打开对应 TXT。')
        self.original = self.path.read_bytes()
        self.document = load_document(self.path)
        self.structured = self.path.suffix.lower() == '.docx'
        self.text = '' if self.structured else decode(self.original)

    def render(self, value):
        if self.structured:
            return self.document.render(value)
        if not isinstance(value, str):
            raise ValueError('文本内容无效')
        if self.path.suffix.lower() in ('.srt','.ass','.ssa','.vtt','.lrc'):
            candidate = TextDocument(value, self.path.suffix)
            result = self.document.render([u.source for u in candidate.units])
            # The edited envelope must still match: do not silently discard edits
            # to timestamps, styles or metadata that the user typed in the editor.
            normalized = lambda s: s.replace('\r\n','\n').replace('\r','\n').rstrip('\n')
            if normalized(result.decode('utf-8-sig')) != normalized(value):
                raise ValueError('字幕时间轴、序号、样式和控制标记受保护，请只修改正文。')
            return result
        return value.encode('utf-8')

    def save(self, value, destination=None, allow_replace=False):
        output = Path(destination).resolve() if destination else self.path
        if output.suffix.lower() != self.path.suffix.lower():
            raise ValueError('另存为时请保持原文件扩展名')
        data = self.render(value)
        same_file = output == self.path
        if same_file and self.path.read_bytes() != self.original:
            raise ValueError('文件已被其他程序修改，请重新打开后编辑，以免覆盖外部修改。')
        if output.exists() and not same_file and not allow_replace:
            raise FileExistsError('目标已存在，请选择其他文件名')
        backup = None
        if output.exists():
            old = output.read_bytes()
            stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
            counter = 0
            while True:
                backup = output.with_name(output.name+f'.{stamp}'+(f'.{counter}' if counter else '')+'.bak')
                try:
                    atomic_write(backup, old, replace=False)
                    break
                except FileExistsError:
                    counter += 1
        atomic_write(output, data, replace=same_file or allow_replace)
        # Keep an existing review record in sync without needing its source file.
        sidecar = output.with_name(output.name+'.review.json')
        result = read_json(sidecar,{})
        if result.get('rows'):
            current = load_document(output)
            if len(result['rows']) == len(current.units):
                for row,unit in zip(result['rows'],current.units):
                    row['target'] = unit.source
                    row['warnings'] = warnings(row.get('source',''),unit.source)
                try:
                    write_json(sidecar,result)
                except OSError:
                    # The document is already saved. A read-only sidecar must not
                    # turn a successful document save into a misleading failure.
                    pass
        self.path, self.original = output, data
        self.document = load_document(output)
        self.text = '' if self.structured else decode(data)
        return backup
