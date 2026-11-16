import ctypes
import json
import os
from pathlib import Path
import sys
import tempfile

def app_root():
    return Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parents[2]

def user_data():
    path = Path(os.environ.get('LOCALAPPDATA', Path.home() / '.local/share')) / 'JapaneseOfflineTranslator'
    path.mkdir(parents=True, exist_ok=True)
    return path

def default_output():
    if os.name == 'nt':
        buffer = ctypes.create_unicode_buffer(32768)
        result = ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buffer)
        if result != 0:
            raise OSError('无法获取系统文档目录，请手动选择输出目录')
        return Path(buffer.value) / 'JapaneseTranslatorOutput'
    return Path.home() / 'Documents/JapaneseTranslatorOutput'

def atomic_write(path, data, replace=True):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.jot-', suffix=path.suffix, dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if replace:
            os.replace(name, path)
        elif os.name == 'nt':
            # Windows rename is atomic and refuses an existing destination.
            os.rename(name, path)
        else:
            os.link(name, path)
            os.unlink(name)
    finally:
        if os.path.exists(name):
            os.unlink(name)

def write_json(path, value, replace=True):
    atomic_write(path, json.dumps(value, ensure_ascii=False, indent=2).encode('utf-8'), replace)

def read_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8-sig'))
    except (OSError, ValueError):
        return default
