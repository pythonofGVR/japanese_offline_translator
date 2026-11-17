"""Complete CPU/CUDA onedir and spanned offline installer (GitHub assets < 2 GiB)."""
import hashlib
from importlib import metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from jot.validation import verify_models
from windows_bundle import verify_windows_bundle

def clean_environment():
    env=dict(os.environ)
    for key in ('PYTHONPATH','PYTHONHOME','QT_PLUGIN_PATH','QT_QPA_PLATFORM','VIRTUAL_ENV','CUDA_PATH','CUDA_HOME'):
        env.pop(key,None)
    env['PATH']=str(Path(os.environ['SYSTEMROOT'])/'System32')
    env['LOCALAPPDATA']=str(ROOT/'reports/local/v1.1.2-appdata')
    return env

def smoke(executable, name, mode, simulated=False):
    report=ROOT/'reports'/f'v1.1.2-{name}.json'
    parent=ROOT/'reports/local';parent.mkdir(parents=True,exist_ok=True)
    work=tempfile.mkdtemp(prefix=name+'-',dir=parent)
    command=[str(executable),'--smoke-test','--device',mode,'--require-device','cpu' if simulated else mode,'--report',str(report),'--work-dir',work]
    if simulated:command.append('--simulate-no-gpu')
    process=subprocess.run(command,cwd=executable.parent,env=clean_environment(),timeout=300)
    if process.returncode or not report.exists():
        raise RuntimeError(f'Acceptance failed: {report}')
    result=json.loads(report.read_text(encoding='utf-8'))
    if result['status']!='PASS':raise RuntimeError(json.dumps(result,ensure_ascii=False))
    print(f'PASS {name}: {len(result["tests"])} checks',flush=True)
    return result

def gui_smoke(executable, name, mode, simulated=False):
    report=ROOT/'reports'/f'v1.1.2-{name}-gui.json'
    work=Path(tempfile.mkdtemp(prefix=name+'-gui-',dir=ROOT/'reports/local'))
    command=[str(executable),'--gui-smoke-test','--device',mode,'--require-device','cpu' if simulated else mode,'--report',str(report),'--work-dir',str(work),'--screenshot',str(report.with_suffix('.png'))]
    if simulated:command.append('--simulate-no-gpu')
    process=subprocess.run(command,cwd=executable.parent,env=clean_environment(),timeout=300)
    if process.returncode or not report.is_file():raise RuntimeError(f'Native GUI failed: {report}')
    result=json.loads(report.read_text(encoding='utf-8'))
    if result['status']!='PASS':raise RuntimeError(json.dumps(result,ensure_ascii=False))
    print(f'PASS native window {name}: {len(result["tests"])} checks',flush=True)
    return result

def install_and_validate(assets, name, seed_legacy_icu=False):
    target=(ROOT/'dist'/name).resolve()
    assert target.parent==(ROOT/'dist').resolve()
    if seed_legacy_icu:
        (target/'_internal').mkdir(parents=True,exist_ok=True)
        for dll in ('icuuc.dll','icudt78.dll'):
            shutil.copy2(ROOT/'JapaneseTranslator/_internal'/dll,target/'_internal'/dll)
    startup=subprocess.STARTUPINFO();startup.dwFlags|=subprocess.STARTF_USESHOWWINDOW
    subprocess.run([str(assets/'JapaneseTranslatorSetup.exe'),'/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/SP-',f'/DIR={target}','/TASKS='],startupinfo=startup,check=True,timeout=600)
    executable=target/'JapaneseTranslator.exe'
    verify_windows_bundle(target)
    results=[smoke(executable,f'{name}-cpu','cpu'),smoke(executable,f'{name}-gpu','cuda'),smoke(executable,f'{name}-no-gpu','cuda',True)]
    for result,mode,simulated in zip(results,('cpu','cuda','cuda'),(False,False,True)):
        result['native_gui']=gui_smoke(executable,f'{name}-'+('no-gpu' if simulated else 'gpu' if mode=='cuda' else 'cpu'),mode,simulated)
        result['upgrade_stale_icu_removed']=seed_legacy_icu
    subprocess.run([str(target/'unins000.exe'),'/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART'],startupinfo=startup,check=True,timeout=120)
    return results

def main(freeze=True):
    from build import licenses
    verify_models(ROOT)
    subprocess.run([sys.executable,'-m','pytest','-q','--junitxml=reports/v1.1.2-tests.xml'],cwd=ROOT,env={**os.environ,'QT_QPA_PLATFORM':'offscreen'},check=True)
    if freeze:
        subprocess.run([sys.executable,'-m','PyInstaller','--noconfirm','--clean',str(ROOT/'scripts/JapaneseTranslator.spec')],cwd=ROOT,check=True)
    folder=ROOT/'dist/JapaneseTranslator'
    verify_windows_bundle(folder)
    shutil.copytree(ROOT/'models',folder/'models',dirs_exist_ok=True,ignore=shutil.ignore_patterns('*.partial','*.chunks','*.assembling'))
    cuda=folder/'runtime/cuda';cuda.mkdir(parents=True,exist_ok=True)
    try:
        package=metadata.distribution('nvidia-cublas-cu12')
    except metadata.PackageNotFoundError:
        package=None
    retained=ROOT/'runtime/cuda'
    manifest=json.loads((retained/'manifest.json').read_text(encoding='utf-8')) if not package else None
    for name in ('cublas64_12.dll','cublasLt64_12.dll'):
        source=package.locate_file('nvidia/cublas/bin/'+name) if package else retained/name
        if not package:
            with source.open('rb') as stream:
                assert hashlib.file_digest(stream,'sha256').hexdigest()==manifest['sha256'][name]
        shutil.copy2(source,cuda/name)
    hashes={}
    for path in cuda.glob('*.dll'):
        with path.open('rb') as stream:hashes[path.name]=hashlib.file_digest(stream,'sha256').hexdigest()
    (cuda/'manifest.json').write_text(json.dumps(dict(package='nvidia-cublas-cu12',version=package.version if package else manifest['version'],sha256=hashes),indent=2),encoding='utf-8')
    licenses(folder/'licenses')
    if not package:
        # Reusing the retained official DLLs also requires their redistribution notice.
        shutil.copytree(ROOT/'JapaneseTranslator/licenses/nvidia-cublas-cu12',folder/'licenses/nvidia-cublas-cu12',dirs_exist_ok=True)
        notices=folder/'licenses/THIRD_PARTY_COMPONENTS.json'
        entries=json.loads(notices.read_text(encoding='utf-8'))
        entries.append(dict(name='nvidia-cublas-cu12',version=manifest['version'],license='NVIDIA license; see bundled notice'))
        notices.write_text(json.dumps(entries,ensure_ascii=False,indent=2),encoding='utf-8')
    shutil.copytree(ROOT/'resources/licenses',folder/'licenses/legal-texts',dirs_exist_ok=True)
    for name in ('README.md','USER_GUIDE.md','LICENSES.md','LICENSE'):
        shutil.copy2(ROOT/name,folder/name)
    executable=folder/'JapaneseTranslator.exe'
    smoke(executable,'frozen-cpu','cpu')
    smoke(executable,'frozen-gpu','cuda')
    smoke(executable,'frozen-no-gpu','cuda',True)
    gui_smoke(executable,'frozen-cpu','cpu')
    gui_smoke(executable,'frozen-gpu','cuda')
    gui_smoke(executable,'frozen-no-gpu','cuda',True)
    assets=ROOT/'dist/release-v1.1.2';assets.mkdir(exist_ok=True)
    # No model/runtime is omitted to fit GitHub's per-file limit: use installer
    # data slices, each < 2 GiB, with a small ordinary Windows setup executable.
    subprocess.run([str(ROOT/'tools/inno6/ISCC.exe'),'/Q',f'/O{assets}',str(ROOT/'scripts/installer.iss')],cwd=ROOT,check=True)
    shutil.copy2(ROOT/'docs/INSTALL_OFFLINE.md',assets/'INSTALL_OFFLINE.md')
    install_and_validate(assets,'安装 验证 v1.1.2',seed_legacy_icu=True)
    sums=[]
    for path in sorted(assets.iterdir()):
        if path.name=='SHA256SUMS.txt' or not path.is_file():continue
        if path.stat().st_size>=2*1024**3:raise RuntimeError(f'GitHub asset too large: {path.name}')
        with path.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
        sums.append(f'{digest}  {path.name}')
    (assets/'SHA256SUMS.txt').write_text('\n'.join(sums)+'\n',encoding='utf-8')
    print('COMPLETE OFFLINE INSTALLER READY: '+str(assets),flush=True)

if __name__=='__main__':main()
