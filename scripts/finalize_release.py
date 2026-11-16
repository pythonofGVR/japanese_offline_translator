"""Refresh release documents, verify installer in an isolated directory, and hash artifacts."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[1]

def main():
    for name in ('source-offline','frozen-offline','relocated-offline','gui-e2e','stress'):
        report=json.loads((ROOT/'reports'/f'{name}.json').read_text(encoding='utf-8'))
        if report['status']!='PASS':
            raise RuntimeError(f'Cannot finalize failed acceptance: {name}')
    folder=ROOT/'dist/JapaneseTranslator'
    for name in ('README.md','USER_GUIDE.md','LICENSES.md','LICENSE'):
        shutil.copy2(ROOT/name,folder/name)
    shutil.copytree(ROOT/'resources/licenses',folder/'licenses/legal-texts',dirs_exist_ok=True)
    for name in ('src','scripts','resources','tests','test_data','docs'):
        shutil.copytree(ROOT/name,folder/'source'/name,dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    for name in ('pyproject.toml','requirements.lock.txt','README.md','USER_GUIDE.md','LICENSES.md','LICENSE'):
        shutil.copy2(ROOT/name,folder/'source'/name)
    reports=folder/'reports';reports.mkdir(exist_ok=True)
    for name in ('ACCEPTANCE.md','source-offline.json','frozen-offline.json','relocated-offline.json','gui-e2e.json','stress.json','unit-tests.xml'):
        shutil.copy2(ROOT/'reports'/name,reports/name)
    print('Compiling final installer with Inno Setup 6.4.3',flush=True)
    subprocess.run([str(ROOT/'tools/inno6/ISCC.exe'),'/Q',str(ROOT/'scripts/installer.iss')],cwd=ROOT,check=True)
    installer=ROOT/'dist/JapaneseTranslatorSetup.exe'
    target=(ROOT/'dist/Installed Final').resolve()
    assert target.parent==(ROOT/'dist').resolve()
    startup=subprocess.STARTUPINFO();startup.dwFlags|=subprocess.STARTF_USESHOWWINDOW
    print('Installing into an isolated project directory',flush=True)
    subprocess.run([str(installer),'/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/SP-',f'/DIR={target}','/TASKS='],startupinfo=startup,check=True,timeout=300)
    installed_report=ROOT/'reports/installed-offline.json'
    subprocess.run([str(target/'JapaneseTranslator.exe'),'--smoke-test','--report',str(installed_report),'--work-dir',str(ROOT/'reports/local/installed-final')],cwd=target,check=True,timeout=300)
    result=json.loads(installed_report.read_text(encoding='utf-8'))
    assert result['status']=='PASS',result
    shutil.copy2(installed_report,reports/installed_report.name)
    # Remove only this test installation using its own generated uninstaller.
    print('Installed EXE passed; removing the isolated test installation',flush=True)
    assert target.is_relative_to((ROOT/'dist').resolve())
    subprocess.run([str(target/'unins000.exe'),'/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART'],startupinfo=startup,check=True,timeout=120)
    archive=ROOT/'dist/JapaneseTranslatorPortable.zip'
    print('Writing final portable ZIP',flush=True)
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=3,allowZip64=True) as bundle:
        for path in sorted(folder.rglob('*')):
            if path.is_file():bundle.write(path,path.relative_to(folder.parent))
    with zipfile.ZipFile(archive) as bundle:
        assert bundle.testzip() is None
    sums=[]
    for path in (archive,installer,folder/'JapaneseTranslator.exe'):
        with path.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
        sums.append(f'{digest}  {path.relative_to(ROOT/"dist").as_posix()}')
    (ROOT/'dist/SHA256SUMS.txt').write_text('\n'.join(sums)+'\n',encoding='utf-8')
    print('FINAL RELEASE PASS',flush=True)

if __name__=='__main__':main()
