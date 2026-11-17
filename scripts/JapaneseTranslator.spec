from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs
import sys

root = Path(SPECPATH).parent
sys.path.insert(0, str(root / 'scripts'))
from windows_bundle import filter_binaries
binaries = [entry for entry in collect_dynamic_libs('ctranslate2') if 'cudnn' not in Path(entry[0]).name.lower()]
a = Analysis(
    [str(root / 'scripts/launch.py')],
    pathex=[str(root / 'src')],
    binaries=binaries,
    datas=collect_data_files('opencc'),
    hiddenimports=['sentencepiece._sentencepiece', 'jot.validation', 'jot.gui_validation'],
    excludes=['tkinter', 'torch', 'transformers', 'huggingface_hub'],
    noarchive=False,
)
# These text models use cuBLAS for CUDA. cuDNN is not required and is not bundled.
a.binaries = filter_binaries(a.binaries)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='JapaneseTranslator', debug=False, bootloader_ignore_signals=False, strip=False, upx=False, console=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='JapaneseTranslator')
