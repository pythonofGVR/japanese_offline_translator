"""Do not redistribute a foreign ICU implementation under Windows system names."""
from pathlib import Path
import re

def is_icu_dll(name):
    return bool(re.fullmatch(r'icu(?:uc|in|dt|io|tu)\d*\.dll', Path(name).name.lower()))

def filter_binaries(entries):
    return [entry for entry in entries if not is_icu_dll(entry[0]) and 'cudnn' not in Path(entry[0]).name.lower()]

def verify_windows_bundle(folder):
    unexpected = [str(p.relative_to(folder)) for p in Path(folder).rglob('*.dll') if is_icu_dll(p.name)]
    if unexpected:
        raise RuntimeError('Foreign ICU DLLs in Windows bundle: ' + ', '.join(unexpected))
    return dict(foreign_icu_dlls=[],windows_icu='System32/icuuc.dll; loaded explicitly before Qt')
