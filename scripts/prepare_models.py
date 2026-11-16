"""Build-time only downloader. Runtime never imports this module or accesses the network."""
import concurrent.futures
import hashlib
import json
from pathlib import Path
import time
import urllib.request
import shutil
import os

def download_large(url, dest, size, digest):
    """Bounded HTTP ranges; validate the server's range and the upstream LFS hash."""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler())
    chunks = dest.parent / (dest.name + '.chunks')
    chunks.mkdir(exist_ok=True)
    step = 4 * 1024 * 1024
    def part(start):
        end = min(start + step, size) - 1
        path = chunks / str(start)
        if path.exists() and path.stat().st_size == end - start + 1:
            return path
        for attempt in range(10):
            try:
                request = urllib.request.Request(url + f'&range_start={start}', headers={'Range': f'bytes={start}-{end}'})
                with opener.open(request, timeout=60) as response:
                    if response.status != 206 or not response.headers.get('Content-Range','').startswith(f'bytes {start}-{end}/'):
                        raise IOError('server did not honor requested range')
                    data = response.read(end - start + 2)
                if len(data) != end - start + 1:
                    raise IOError('truncated range')
                path.write_bytes(data)
                print(f'{dest.parent.name}: {end+1:,} / {size:,}', flush=True)
                return path
            except Exception as exc:
                print(f'Range retry {dest.parent.name} {start} ({attempt}): {exc}', flush=True)
                time.sleep(min(2**attempt,10))
        raise IOError(f'cannot download range {start}')
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        paths = list(pool.map(part, range(0,size,step)))
    temporary = dest.with_name(dest.name+'.assembling')
    with temporary.open('wb') as stream:
        for path in paths:
            with path.open('rb') as chunk:
                shutil.copyfileobj(chunk,stream)
    with temporary.open('rb') as stream:
        if hashlib.file_digest(stream,'sha256').hexdigest() != digest:
            raise IOError('upstream model SHA256 mismatch')
    temporary.replace(dest)
    shutil.rmtree(chunks)
    dest.with_name(dest.name+'.partial').unlink(missing_ok=True)
    print(f'VERIFIED {dest.parent.name} model',flush=True)

ROOT = Path(__file__).resolve().parents[1]
MODELS = {
    'fast': ('JustFrederik/m2m_100_418m_ct2_int8', '1aeed44db4dd61a486bba44acf54c76507082a2c', 'facebook/m2m100_418M', '55c2e61bbf05dfb8d7abccdc3fae6fc8512fd636'),
    'quality': ('JustFrederik/m2m_100_1.2b_ct2_int8', '0e07f3608b9be1a81df0813b53c3e338ecc3890a', 'facebook/m2m100_1.2B', '7b36184180524c1a1bbfa37f120a608046250b98'),
}

def download(url, dest, expected_size=None, expected_hash=None):
    dest.parent.mkdir(parents=True, exist_ok=True)
    partial = dest.with_name(dest.name + '.partial')
    for attempt in range(6):
        try:
            offset = partial.stat().st_size if partial.exists() else 0
            request = urllib.request.Request(url, headers={'Range': f'bytes={offset}-'} if offset else {})
            with urllib.request.urlopen(request, timeout=90) as response:
                mode = 'ab' if response.status == 206 and offset else 'wb'
                with partial.open(mode) as stream:
                    while data := response.read(1024 * 1024):
                        stream.write(data)
            if expected_size and partial.stat().st_size != expected_size:
                raise IOError(f'incomplete file: {partial.stat().st_size} / {expected_size}')
            if expected_hash:
                with partial.open('rb') as stream:
                    if hashlib.file_digest(stream, 'sha256').hexdigest() != expected_hash:
                        partial.unlink()
                        raise IOError('upstream SHA256 mismatch')
            partial.replace(dest)
            print(f'Downloaded {dest.name}: {dest.stat().st_size:,} bytes', flush=True)
            return
        except Exception as exc:
            print(f'Retry {attempt + 1}: {dest.name}: {exc}', flush=True)
            time.sleep(min(2 ** attempt, 20))
    raise RuntimeError(f'Download failed: {url}')

def prepare(key, spec):
    repo, revision, original, original_revision = spec
    folder = ROOT / 'models' / key
    folder.mkdir(parents=True, exist_ok=True)
    for attempt in range(6):
        try:
            with urllib.request.urlopen(f'https://huggingface.co/api/models/{repo}/tree/{revision}?recursive=true', timeout=30) as r:
                metadata = json.load(r)
            break
        except Exception as exc:
            print(f'Metadata retry {key}: {exc}',flush=True)
            if attempt==5:
                raise
    names = [x for x in metadata if x['path'] in ('model.bin', 'config.json', 'shared_vocabulary.txt', 'shared_vocabulary.json', 'source_vocabulary.json', 'target_vocabulary.json', 'spm.128k.model', 'README.md')]
    for info in names:
        name = info['path']
        dest = folder / ('sentencepiece.bpe.model' if name == 'spm.128k.model' else name)
        if dest.exists() and dest.stat().st_size != info['size']:
            dest.replace(dest.with_name(dest.name + '.partial'))
        if not dest.exists():
            url = f'https://huggingface.co/{repo}/resolve/{revision}/{name}?download=true'
            if name == 'model.bin':
                download_large(url, dest, info['size'], info['lfs']['oid'])
            else:
                download(url, dest, info['size'], info.get('lfs', {}).get('oid'))
    if not (folder / 'sentencepiece.bpe.model').exists():
        download(f'https://huggingface.co/{original}/resolve/{original_revision}/sentencepiece.bpe.model', folder / 'sentencepiece.bpe.model')
    download(f'https://huggingface.co/{original}/raw/{original_revision}/README.md', folder / 'UPSTREAM_MODEL_CARD.md')
    # The model card declares MIT; retain the original project's full copyright/license.
    download('https://raw.githubusercontent.com/facebookresearch/fairseq/main/LICENSE', folder / 'LICENSE')
    hashes = {}
    for p in folder.iterdir():
        if p.is_file() and p.name != 'manifest.json' and not p.name.endswith(('.partial','.assembling')):
            with p.open('rb') as stream:
                hashes[p.name] = hashlib.file_digest(stream,'sha256').hexdigest()
    (folder / 'manifest.json').write_text(json.dumps(dict(repository=repo, revision=revision, upstream=original, upstream_revision=original_revision, quantization='int8', license='MIT', sha256=hashes), indent=2), encoding='utf-8')
    print(f'READY {key}', flush=True)

if __name__ == '__main__':
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda item: prepare(*item), MODELS.items()))
