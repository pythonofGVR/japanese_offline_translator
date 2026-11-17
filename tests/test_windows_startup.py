import os
from pathlib import Path
import subprocess
import sys
import pytest

def test_bundle_excludes_foreign_icu_and_keeps_application_dlls():
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
    from windows_bundle import filter_binaries
    rows=[('icuuc.dll','poppler/icuuc.dll','BINARY'),('icudt78.dll','poppler/icudt78.dll','BINARY'),('PySide6/Qt6Core.dll','qt/Qt6Core.dll','BINARY'),('runtime/cuda/cublas64_12.dll','cuda/cublas64_12.dll','BINARY')]
    assert [x[0] for x in filter_binaries(rows)]==['PySide6/Qt6Core.dll','runtime/cuda/cublas64_12.dll']

@pytest.mark.skipif(os.name!='nt',reason='Windows system ICU')
def test_system_icu_has_required_unversioned_exports():
    code="from jot.startup import prepare_windows_icu; import pathlib; p=pathlib.Path(prepare_windows_icu()); assert p.name.lower()=='icuuc.dll' and p.parent.name.lower()=='system32'"
    subprocess.run([sys.executable,'-c',code],check=True,timeout=30)

def test_bundle_guard_rejects_stale_icu(tmp_path):
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
    from windows_bundle import verify_windows_bundle
    (tmp_path/'icuuc.dll').write_bytes(b'foreign ABI')
    with pytest.raises(RuntimeError,match='Foreign ICU'):
        verify_windows_bundle(tmp_path)
