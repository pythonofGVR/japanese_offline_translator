"""Reproducible onedir release, model/notice inclusion and ZIP64 archive."""
import hashlib
import importlib.metadata
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from jot.validation import verify_models

def licenses(destination):
    destination.mkdir(parents=True,exist_ok=True)
    entries=[]
    for distribution in importlib.metadata.distributions():
        name=distribution.metadata['Name']
        if name.lower() in ('pip','japanese-offline-translator'):
            continue
        entry={'name':name,'version':distribution.version,'license':distribution.metadata.get('License-Expression') or distribution.metadata.get('License','see bundled notices'),'homepage':distribution.metadata.get('Home-page','')}
        entries.append(entry)
        for file in distribution.files or []:
            label=str(file).lower()
            if any(word in label for word in ('license','copying','copyright','notice')) and distribution.locate_file(file).is_file():
                source=Path(distribution.locate_file(file))
                target=destination/name/str(file).replace('../','_').replace('..\\','_')
                target.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(source,target)
    (destination/'THIRD_PARTY_COMPONENTS.json').write_text(json.dumps(entries,ensure_ascii=False,indent=2),encoding='utf-8')

def main():
    verify_models(ROOT)
    subprocess.run([sys.executable,'-m','pytest','-q'],cwd=ROOT,check=True,env={**__import__('os').environ,'QT_QPA_PLATFORM':'offscreen'})
    command=[sys.executable,'-m','PyInstaller','--noconfirm','--clean',str(ROOT/'scripts/JapaneseTranslator.spec')]
    subprocess.run(command,cwd=ROOT,check=True)
    folder=ROOT/'dist/JapaneseTranslator'
    shutil.copytree(ROOT/'models',folder/'models',dirs_exist_ok=True,ignore=shutil.ignore_patterns('*.partial','*.chunks','*.assembling'))
    licenses(folder/'licenses')
    shutil.copytree(ROOT/'resources/licenses',folder/'licenses/legal-texts',dirs_exist_ok=True)
    for name in ('README.md','USER_GUIDE.md','LICENSES.md','LICENSE'):
        shutil.copy2(ROOT/name,folder/name)
    (folder/'source').mkdir(exist_ok=True)
    # LGPL users may replace Qt DLLs in _internal/PySide6. Supply app source and build instructions.
    for name in ('src','scripts'):
        shutil.copytree(ROOT/name,folder/'source'/name,dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    for name in ('pyproject.toml','requirements.lock.txt'):
        shutil.copy2(ROOT/name,folder/'source'/name)
    report=ROOT/'reports/frozen-offline.json'
    process=subprocess.run([str(folder/'JapaneseTranslator.exe'),'--smoke-test','--report',str(report),'--work-dir',str(ROOT/'reports/local/frozen')],cwd=folder,timeout=1800)
    if process.returncode or not report.exists() or json.loads(report.read_text(encoding='utf-8'))['status']!='PASS':
        raise RuntimeError('Frozen executable failed offline acceptance. Do not ship.')
    archive=ROOT/'dist/JapaneseTranslatorPortable.zip'
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=3,allowZip64=True) as output:
        for path in sorted(folder.rglob('*')):
            if path.is_file():
                output.write(path,path.relative_to(folder.parent))
    sums=[]
    for path in (archive,folder/'JapaneseTranslator.exe'):
        with path.open('rb') as stream:
            sums.append(f'{hashlib.file_digest(stream,"sha256").hexdigest()}  {path.relative_to(ROOT/"dist").as_posix()}')
    (ROOT/'dist/SHA256SUMS.txt').write_text('\n'.join(sums)+'\n',encoding='utf-8')
    print(f'Release ready: {archive}')

if __name__=='__main__':
    main()
