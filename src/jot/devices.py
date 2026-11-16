import ctypes
from importlib import metadata
import os
from pathlib import Path

_DIRECTORY_HANDLES = {}
_LIBRARY_HANDLES = {}

def enable_cuda_libraries(root):
    """Use bundled cuBLAS; drivers remain the operating system's responsibility."""
    if os.name != 'nt':
        return
    candidates = [Path(root)/'runtime/cuda']
    try:
        candidates.append(Path(metadata.distribution('nvidia-cublas-cu12').locate_file('nvidia/cublas/bin')))
    except metadata.PackageNotFoundError:
        pass
    folder = next((p for p in candidates if (p/'cublas64_12.dll').is_file() and (p/'cublasLt64_12.dll').is_file()), None)
    if folder is None:
        raise RuntimeError('缺少离线 GPU 运行库，请使用包含 runtime/cuda 的完整发行包')
    key = str(folder.resolve())
    if key not in _DIRECTORY_HANDLES:
        _DIRECTORY_HANDLES[key] = os.add_dll_directory(key)
    for name in ('cublasLt64_12.dll','cublas64_12.dll'):
        path = str(folder/name)
        if path not in _LIBRARY_HANDLES:
            _LIBRARY_HANDLES[path] = ctypes.WinDLL(path)

def gpu_summary():
    try:
        import ctranslate2
        count = ctranslate2.get_cuda_device_count()
        return f'检测到 {count} 个 NVIDIA CUDA 设备' if count else '未检测到兼容 GPU；GPU 模式将使用 CPU'
    except Exception:
        return 'GPU 检测不可用；将使用 CPU'
