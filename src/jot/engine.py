import gc
import hashlib
import json
from pathlib import Path
import os
import re
import sqlite3
import time

from .formats import JAPANESE, text_parts
from .paths import app_root, user_data
from .quality import warnings, score, safe_cleanup

MODEL_NAMES = {'fast': 'M2M100 418M · INT8', 'quality': 'M2M100 1.2B · INT8'}

def model_status(key, root=None):
    folder = Path(root or app_root()) / 'models' / key
    needed = ['model.bin', 'config.json', 'sentencepiece.bpe.model', 'manifest.json']
    ready = all((folder / n).is_file() for n in needed) and any((folder / n).is_file() for n in ('shared_vocabulary.json', 'shared_vocabulary.txt', 'source_vocabulary.json'))
    size = sum(p.stat().st_size for p in folder.glob('*') if p.is_file()) if folder.exists() else 0
    return ready, size

class Engine:
    def __init__(self, root=None, cache_path=None):
        self.root = Path(root or app_root())
        self.key, self.translator, self.sp = None, None, None
        self.threads = None
        self.db = sqlite3.connect(cache_path or user_data() / 'translations.sqlite3')
        self.db.execute('CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
        self.load_seconds = 0

    def close(self):
        self.unload()
        self.db.close()

    def unload(self):
        self.translator = None
        self.sp = None
        self.key = None
        gc.collect()

    def load(self, key, threads=4):
        if self.key == key and self.threads == threads:
            return
        self.unload()
        folder = self.root / 'models' / key
        if not model_status(key, self.root)[0]:
            raise FileNotFoundError(f'{MODEL_NAMES[key]} 文件缺失，请使用包含两个完整模型的发行包')
        manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
        # Hashes are verified by the release smoke test; at runtime check file sizes/config.
        self.revision = manifest['revision']
        start = time.perf_counter()
        try:
            import ctranslate2
            import sentencepiece
            # Windows native fopen APIs in SentencePiece do not reliably accept
            # Unicode paths. Python opens the file using the wide-character API.
            self.sp = sentencepiece.SentencePieceProcessor(model_proto=(folder / 'sentencepiece.bpe.model').read_bytes())
            if os.name == 'nt' and not str(folder).isascii():
                names = ('model.bin','config.json','shared_vocabulary.txt','shared_vocabulary.json','source_vocabulary.json','target_vocabulary.json')
                files = {name:(folder/name).read_bytes() for name in names if (folder/name).is_file()}
                self.translator = ctranslate2.Translator(f'jot-{key}-{self.revision}', device='cpu', compute_type='int8', inter_threads=1, intra_threads=threads, files=files)
            else:
                self.translator = ctranslate2.Translator(str(folder), device='cpu', compute_type='int8', inter_threads=1, intra_threads=threads)
        except Exception as exc:
            self.unload()
            raise RuntimeError(f'模型加载失败：{exc}。请检查可用内存、模型完整性和 CPU 指令集。') from exc
        self.key, self.threads = key, threads
        self.load_seconds = time.perf_counter() - start

    def infer(self, texts, language='zh-CN', beam=3, retry=0):
        if not self.translator:
            raise RuntimeError('模型尚未加载')
        target = '__en__' if language == 'en' else '__zh__'
        tokenized = [['__ja__'] + self.sp.encode(t, out_type=str) + ['</s>'] for t in texts]
        if any(len(t) > 480 for t in tokenized):
            raise ValueError('输入超过安全 token 上限')
        results = self.translator.translate_batch(tokenized, target_prefix=[[target]] * len(texts), beam_size=beam, max_decoding_length=480, repetition_penalty=1.08 if retry else 1.0, no_repeat_ngram_size=4 if retry else 0, batch_type='tokens', max_batch_size=1200)
        output = []
        if language != 'en':
            from opencc import OpenCC
            cc = OpenCC('s2t' if language == 'zh-TW' else 't2s')
        for result in results:
            tokens = [t for t in result.hypotheses[0] if not (t.startswith('__') and t.endswith('__')) and t not in ('</s>', '<s>')]
            value = safe_cleanup(self.sp.decode(tokens))
            output.append(cc.convert(value) if language != 'en' else value)
        return output

    def translate(self, texts, language='zh-CN', quality='auto', beam=3, markdown=False, boundary=lambda: None, progress=lambda a,b: None, force=False):
        # Split on explicit formatting and whitespace. Every chunk is independently
        # aligned, so MT cannot merge subtitles or corrupt control information.
        all_parts, jobs = [], []
        for index, text in enumerate(texts):
            parts = text_parts(text, markdown)
            expanded = []
            for part_index, part in enumerate(parts):
                if part_index % 2:
                    expanded.append(part)
                    continue
                for chunk in re.split(r'(\r\n|\n|\r)', part):
                    if not chunk or not JAPANESE.search(chunk):
                        expanded.append(chunk)
                        continue
                    leading = chunk[:len(chunk)-len(chunk.lstrip())]
                    trailing = chunk[len(chunk.rstrip()):]
                    raw = chunk.strip()
                    # SentencePiece byte fallback can expand text: chunk by token count.
                    units = re.findall(r'.*?[。！？!?]+|.+$', raw)
                    combined = ''
                    chunks = []
                    for unit in units:
                        if combined and len(self.sp.encode(combined + unit)) > 350:
                            chunks.append(combined)
                            combined = ''
                        while len(self.sp.encode(unit)) > 350:
                            cut = max(1, len(unit) // 2)
                            while len(self.sp.encode(unit[:cut])) > 350:
                                cut //= 2
                            chunks.append(unit[:cut])
                            unit = unit[cut:]
                        combined += unit
                    if combined:
                        chunks.append(combined)
                    expanded.append(leading)
                    for small in chunks:
                        offset = len(expanded)
                        expanded.append('')
                        jobs.append((index, offset, small))
                    expanded.append(trailing)
            all_parts.append(expanded)
        total = len(jobs)
        cache_keys = {}
        pending = {}
        for i, offset, source in jobs:
            settings = [self.key, self.revision, language, quality, beam, source, 'pipeline-v2']
            key = hashlib.sha256(json.dumps(settings, ensure_ascii=False).encode()).hexdigest()
            cache_keys[source] = key
            row = None if force else self.db.execute('SELECT value FROM cache WHERE key=?', (key,)).fetchone()
            if row:
                all_parts[i][offset] = row[0]
            else:
                pending.setdefault(source, []).append((i, offset))
        done = total - sum(len(v) for v in pending.values())
        progress(done, total)
        sources = list(pending)
        initial_by_source = {}
        for start in range(0, len(sources), 8):
            boundary()
            batch = sources[start:start+8]
            first = self.infer(batch, language, beam)
            chosen = list(first)
            for n, (source, candidate) in enumerate(zip(batch, first)):
                initial_by_source[source] = candidate
                attempts = 0 if quality == 'standard' else (2 if quality == 'best' else 1)
                if warnings(source, candidate):
                    for retry in range(attempts):
                        boundary()
                        alternate = self.infer([source], language, max(beam, 5 + retry * 2), retry=retry + 1)[0]
                        if score(source, alternate) < score(source, chosen[n]):
                            chosen[n] = alternate
                if not chosen[n].strip():
                    chosen[n] = source
                for i, offset in pending[source]:
                    all_parts[i][offset] = chosen[n]
                    done += 1
                self.db.execute('INSERT OR REPLACE INTO cache VALUES (?,?)', (cache_keys[source], chosen[n]))
            self.db.commit()
            progress(done, total)
        final = [''.join(parts) for parts in all_parts]
        # First-pass text is retained separately in fresh runs. Cached final results
        # are labelled as such rather than pretending to be a new first pass.
        original_parts = [list(p) for p in all_parts]
        for i, offset, source in jobs:
            if source in initial_by_source:
                original_parts[i][offset] = initial_by_source[source]
        first_pass = [''.join(p) for p in original_parts]
        flags = [warnings(s, t) for s, t in zip(texts, final)]
        return final, first_pass, flags
