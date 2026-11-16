from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

root = Path(SPECPATH).parent
binaries = [entry for entry in collect_dynamic_libs('ctranslate2') if 'cudnn' not in Path(entry[0]).name.lower()]
a = Analysis(
    [str(root / 'scripts/launch.py')],
    pathex=[str(root / 'src')],
    binaries=binaries,
    datas=collect_data_files('opencc'),
    hiddenimports=['sentencepiece._sentencepiece', 'jot.validation'],
    excludes=['tkinter', 'torch', 'transformers', 'huggingface_hub'],
    noarchive=False,
)
# This is a CPU-only release. cuDNN is neither used nor required by the PE imports.
a.binaries = [entry for entry in a.binaries if 'cudnn' not in entry[0].lower()]
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='JapaneseTranslator', debug=False, bootloader_ignore_signals=False, strip=False, upx=False, console=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='JapaneseTranslator')
