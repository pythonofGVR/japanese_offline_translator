from dataclasses import dataclass, asdict
import hashlib
import os
from pathlib import Path
import re
import threading
import time

from .formats import SUPPORTED, load_document, subtitle_problem, original_one_line
from .reviews import review_path
from .paths import atomic_write, default_output, read_json, write_json
from .parameters import THREAD_MIN, THREAD_MAX, DEFAULT_THREADS, BEAM_MIN, BEAM_MAX, DEFAULT_BEAM, validate_integer

@dataclass
class InputFile:
    path: str
    root: str = ''

@dataclass
class Settings:
    model: str = 'fast'
    language: str = 'zh-CN'
    quality: str = 'auto'
    output: str = ''
    preserve: bool = True
    conflict: str = 'rename'
    encoding: str = 'auto'
    threads: int = DEFAULT_THREADS
    beam: int = DEFAULT_BEAM
    device: str = 'cpu'

    def __post_init__(self):
        validate_integer(self.threads, THREAD_MIN, THREAD_MAX, '线程数')
        validate_integer(self.beam, BEAM_MIN, BEAM_MAX, '搜索宽度')
        if self.device not in ('cpu','cuda'):
            raise ValueError('设备必须是 CPU 或 GPU 优先')

def generated(path):
    return bool(re.search(r'\.(?:zh-CN|zh-TW|en)(?:\.\d+)?\.[^.]+$', path.name, re.I))

def scan(folder, recursive=True, output=None, extensions=None):
    folder = Path(folder).resolve()
    excluded = Path(output).resolve() if output else default_output().resolve()
    extensions = set(extensions or SUPPORTED)
    files, skipped = [], []
    for current, dirs, names in os.walk(folder, followlinks=False):
        dirs[:] = sorted(d for d in dirs if not (Path(current)/d).is_symlink() and not getattr((Path(current)/d).lstat(), 'st_file_attributes', 0) & 0x400 and (Path(current)/d).resolve() != excluded)
        if Path(current).resolve() == excluded:
            dirs[:] = []
            continue
        for name in sorted(names):
            path = Path(current) / name
            if path.is_symlink() or getattr(path.lstat(), 'st_file_attributes', 0) & 0x400:
                skipped.append(str(path))
            elif path.suffix.lower() in extensions and not generated(path):
                files.append(InputFile(str(path), str(folder)))
            else:
                skipped.append(str(path))
        if not recursive:
            dirs[:] = []
    return files, skipped

class Cancelled(Exception):
    pass

class Control:
    def __init__(self):
        self.cancelled = threading.Event()
        self.running = threading.Event()
        self.running.set()

    def boundary(self):
        while not self.running.wait(.1):
            if self.cancelled.is_set():
                raise Cancelled('用户取消任务')
        if self.cancelled.is_set():
            raise Cancelled('用户取消任务')

    def cancel(self):
        self.cancelled.set()
        self.running.set()

def source_hash(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def reservation_path(output):
    return output.with_name('.' + output.name + '.jot-reserve')

def reserve_output(item, settings):
    source = Path(item.path).resolve()
    destination = Path(settings.output) if settings.output else default_output()
    relative = source.relative_to(Path(item.root).resolve()).parent if item.root and settings.preserve else Path()
    destination = destination / relative
    destination.mkdir(parents=True, exist_ok=True)
    suffix = '.txt' if source.suffix.lower() == '.pdf' else source.suffix.lower()
    base = f'{source.stem}.{settings.language}'
    counter = 0
    while True:
        path = destination / f'{base}{"." + str(counter) if counter else ""}{suffix}'
        if path.resolve() == source:
            raise ValueError('输出路径不能覆盖原文')
        lock = reservation_path(path)
        try:
            if path.exists() or path.with_name(path.name + '.review.json').exists():
                raise FileExistsError(str(path))
            with lock.open('xb'):
                pass
            if path.exists() or path.with_name(path.name + '.review.json').exists():
                lock.unlink(missing_ok=True)
                raise FileExistsError(str(path))
            return path
        except FileExistsError:
            if settings.conflict == 'skip':
                return None
            counter += 1

def translate_file(item, settings, engine, control, progress=lambda a,b: None):
    try:
        return _translate_file(item, settings, engine, control, progress)
    except Cancelled:
        raise
    except Exception as exc:
        raise RuntimeError(f'文件：{item.path}\n{type(exc).__name__}：{exc}') from exc

def _translate_file(item, settings, engine, control, progress):
    control.boundary()
    source = Path(item.path)
    digest = source_hash(source)
    try:
        doc = load_document(source, settings.encoding)
    except Exception as exc:
        raise ValueError(f'读取/解析失败：{exc}') from exc
    try:
        output = reserve_output(item, settings)
    except OSError as exc:
        raise OSError(f'无法创建目标文件；请检查输出路径、写入权限及磁盘空间：{exc}') from exc
    if output is None:
        return {'status': '已跳过', 'source': str(source), 'output': '', 'reason': '同名目标已存在'}
    try:
        target, initial, flags = engine.translate([u.source for u in doc.units], settings.language, settings.quality, settings.beam, markdown=source.suffix.lower()=='.md', boundary=control.boundary, progress=progress)
        control.boundary()
        if source.suffix.lower() in ('.srt','.vtt','.ass','.ssa','.lrc'):
            for index, unit in enumerate(doc.units):
                problem = subtitle_problem(unit.source, target[index])
                fallback = any(w.startswith('保留原文：') for w in flags[index])
                if problem or fallback:
                    target[index] = original_one_line(unit.source)
                    if problem:
                        flags[index].append('保留原文：' + problem)
                    flags[index].append('原文压为单行，最多 42 个可见字符（含省略号）；完整原文见校对记录')
        data = doc.render(target)
        if source_hash(source) != digest:
            raise ValueError('翻译期间原文已变更，已停止保存；请重新导入')
        result = dict(status='已完成', source=str(source), source_hash=digest, output=str(output), settings=asdict(settings), rows=[dict(source=u.source, label=u.label, initial=a, target=b, warnings=f) for u,a,b,f in zip(doc.units, initial, target, flags)], warnings=doc.warnings, completed=time.time())
        result['runtime'] = dict(device=engine.device, compute_type=engine.compute_type, fallback_reason=engine.fallback_reason)
        result['fallback_count'] = sum(any(w.startswith('保留原文：') for w in row['warnings']) for row in result['rows'])
        result['reason'] = f'已保存；{result["fallback_count"]} 条保留单行原文。输出：{output}'
        try:
            atomic_write(output, data, replace=False)
        except OSError as exc:
            raise OSError(f'保存译文失败；目标：{output}；请检查权限/磁盘空间：{exc}') from exc
        # Review/cache failure must never discard an already completed translation.
        try:
            result['review'] = str(review_path(output))
            write_json(result['review'], result)
        except OSError as exc:
            result['warnings'].append(f'译文已保存，但本机校对记录保存失败：{type(exc).__name__}: {exc}')
        return result
    finally:
        reservation_path(output).unlink(missing_ok=True)

def save_review(result, targets):
    if source_hash(result['source']) != result['source_hash']:
        raise ValueError('原文已变更，无法安全重建。请重新翻译。')
    doc = load_document(result['source'], result['settings']['encoding'])
    output = Path(result['output'])
    if output.resolve() == Path(result['source']).resolve():
        raise ValueError('校对输出不能覆盖原文')
    data = doc.render(targets)
    for row, target in zip(result['rows'], targets):
        row['target'] = target
    atomic_write(output, data)
    write_json(review_path(output), result)
