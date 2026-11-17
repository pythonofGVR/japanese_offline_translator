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
from .parameters import DEFAULT_THREADS, THREAD_MIN, THREAD_MAX, BEAM_MIN, BEAM_MAX, validate_integer
from .devices import enable_cuda_libraries

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
        self.device, self.compute_type, self.requested_device = 'cpu', 'int8', 'cpu'
        self.fallback_reason = ''

    def close(self):
        self.unload()
        self.db.close()

    def unload(self):
        self.translator = None
        self.sp = None
        self.key = None
        gc.collect()

    def load(self, key, threads=DEFAULT_THREADS, device='cpu'):
        validate_integer(threads, THREAD_MIN, THREAD_MAX, '线程数')
        if device not in ('cpu','cuda'):
            raise ValueError('无效运行设备')
        if self.key == key and self.threads == threads and self.requested_device == device:
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
            files = None
            identifier = str(folder)
            if os.name == 'nt' and not str(folder).isascii():
                names = ('model.bin','config.json','shared_vocabulary.txt','shared_vocabulary.json','source_vocabulary.json','target_vocabulary.json')
                files = {name:(folder/name).read_bytes() for name in names if (folder/name).is_file()}
                identifier = f'jot-{key}-{self.revision}'
            self.device, self.compute_type, self.fallback_reason = 'cpu', 'int8', ''
            if device == 'cuda':
                try:
                    if ctranslate2.get_cuda_device_count() < 1:
                        raise RuntimeError('没有可用的 NVIDIA CUDA GPU')
                    enable_cuda_libraries(self.root)
                    supported = ctranslate2.get_supported_compute_types('cuda')
                    compute = next(t for t in ('int8_float16','float16','float32') if t in supported)
                    self.translator = ctranslate2.Translator(identifier, device='cuda', compute_type=compute, inter_threads=1, intra_threads=threads, files=files)
                    self.device, self.compute_type = 'cuda', compute
                except Exception as exc:
                    self.translator = None
                    gc.collect()
                    self.fallback_reason = f'GPU 不可用，已回退 CPU：{exc}'
            if self.translator is None:
                self.translator = ctranslate2.Translator(identifier, device='cpu', compute_type='int8', inter_threads=1, intra_threads=threads, files=files)
        except Exception as exc:
            self.unload()
            raise RuntimeError(f'模型加载失败：{exc}。请检查可用内存、模型完整性和 CPU 指令集。') from exc
        self.key, self.threads, self.requested_device = key, threads, device
        self.load_seconds = time.perf_counter() - start

    def infer(self, texts, language='zh-CN', beam=3, retry=0):
        validate_integer(beam, BEAM_MIN, BEAM_MAX, '搜索宽度')
        if not self.translator:
            raise RuntimeError('模型尚未加载')
        target = '__en__' if language == 'en' else '__zh__'
        tokenized = [['__ja__'] + self.sp.encode(t, out_type=str) + ['</s>'] for t in texts]
        if any(len(t) > 480 for t in tokenized):
            raise ValueError('输入超过安全 token 上限')
        try:
            results = self.translator.translate_batch(tokenized, target_prefix=[[target]] * len(texts), beam_size=beam, max_decoding_length=480, repetition_penalty=1.08 if retry else 1.0, no_repeat_ngram_size=4 if retry else 0, batch_type='tokens', max_batch_size=1200)
        except RuntimeError as exc:
            if self.device != 'cuda':
                raise
            key, threads = self.key, self.threads
            self.load(key, threads, 'cpu')
            self.requested_device = 'cuda'
            self.fallback_reason = f'GPU 推理失败，已回退 CPU：{exc}'
            return self.infer(texts, language, beam, retry)
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
        validate_integer(beam, BEAM_MIN, BEAM_MAX, '搜索宽度')
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
                                if cut == 1:
                                    raise ValueError('单个字符超过模型输入上限')
                                cut = max(1, cut // 2)
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
        failure_by_source = {}
        pending = {}
        for i, offset, source in jobs:
            settings = [self.key, self.revision, self.device, self.compute_type, language, quality, beam, source, 'pipeline-v5']
            key = hashlib.sha256(json.dumps(settings, ensure_ascii=False).encode()).hexdigest()
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
            errors = {}
            try:
                first = self.infer(batch, language, beam)
                if len(first) != len(batch):
                    raise ValueError('模型返回条目数不匹配')
            except Exception as exc:
                # Isolate a bad batch; each segment gets finite individual retries.
                first = []
                for source in batch:
                    boundary()
                    try:
                        first.append(self.infer([source], language, beam)[0])
                    except Exception as single:
                        first.append('')
                        errors[source] = f'{type(single).__name__}: {single}（批次：{type(exc).__name__}: {exc}）'
            chosen = list(first)
            for n, (source, candidate) in enumerate(zip(batch, first)):
                initial_by_source[source] = candidate
                attempts = 0 if quality == 'standard' else (2 if quality == 'best' else 1)
                if not candidate.strip():
                    attempts = max(attempts, 2)
                if warnings(source, candidate):
                    for retry in range(attempts):
                        boundary()
                        try:
                            alternate = self.infer([source], language, max(beam, 5 + retry * 2), retry=retry + 1)[0]
                        except Exception as exc:
                            errors[source] = f'{type(exc).__name__}: {exc}'
                            continue
                        if score(source, alternate) < score(source, chosen[n]):
                            chosen[n] = alternate
                severe = [w for w in warnings(source, chosen[n]) if w in ('空译文','残留日文假名','原文未翻译','译文可能过短','译文可能过长','模型输出未知词标记')]
                if severe:
                    chosen[n] = source
                    failure_by_source[source] = '保留原文：有限重试后仍无法翻译；' + (errors.get(source) or '；'.join(severe))
                for i, offset in pending[source]:
                    all_parts[i][offset] = chosen[n]
                    done += 1
                # A failed GPU inference may have switched to CPU within this batch.
                settings = [self.key, self.revision, self.device, self.compute_type, language, quality, beam, source, 'pipeline-v5']
                actual_key = hashlib.sha256(json.dumps(settings, ensure_ascii=False).encode()).hexdigest()
                if source not in failure_by_source:
                    self.db.execute('INSERT OR REPLACE INTO cache VALUES (?,?)', (actual_key, chosen[n]))
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
        for i, offset, source in jobs:
            if source in failure_by_source and failure_by_source[source] not in flags[i]:
                flags[i].append(failure_by_source[source])
        return final, first_pass, flags
