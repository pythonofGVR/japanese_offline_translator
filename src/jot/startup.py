"""Select the Windows ICU ABI before importing Qt; never use build-tool ICU DLLs."""
import ctypes
import os
from pathlib import Path
import sys
import traceback

_SYSTEM_ICU = None

def prepare_windows_icu():
    global _SYSTEM_ICU
    if os.name != 'nt':
        return ''
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.GetSystemDirectoryW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint]
    kernel.GetSystemDirectoryW.restype = ctypes.c_uint
    buffer = ctypes.create_unicode_buffer(32768)
    length = kernel.GetSystemDirectoryW(buffer, len(buffer))
    if not 0 < length < len(buffer):
        raise ctypes.WinError(ctypes.get_last_error())
    path = Path(buffer.value) / 'icuuc.dll'
    # Windows' unversioned ICU API is different from Poppler/Conda ICU's *_78 ABI.
    # Pin the system copy before Qt loads, including when upgrading an old folder.
    if _SYSTEM_ICU is None:
        _SYSTEM_ICU = ctypes.WinDLL(str(path), winmode=0x800)  # SEARCH_SYSTEM32
        for name in ('ucnv_open', 'ucnv_close', 'ucnv_toUnicode'):
            getattr(_SYSTEM_ICU, name)
    kernel.GetModuleFileNameW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_uint]
    kernel.GetModuleFileNameW.restype = ctypes.c_uint
    if not kernel.GetModuleFileNameW(_SYSTEM_ICU._handle, buffer, len(buffer)):
        raise ctypes.WinError(ctypes.get_last_error())
    if Path(buffer.value).resolve() != path.resolve():
        raise RuntimeError('Windows ICU 路径校验失败')
    return str(path)

def launch_gui():
    try:
        prepare_windows_icu()
        from .gui import launch
        return launch()
    except Exception:
        details = traceback.format_exc()
        from .paths import user_data, atomic_write
        log = user_data() / 'startup-error.log'
        atomic_write(log, details.encode('utf-8'))
        if os.name == 'nt':
            ctypes.windll.user32.MessageBoxW(None, '界面启动失败。请使用完整安装包重新安装。\n详细原因已保存到：\n' + str(log), '日文离线翻译器：启动失败', 0x10)
        else:
            print(details, file=sys.stderr)
        return 1
