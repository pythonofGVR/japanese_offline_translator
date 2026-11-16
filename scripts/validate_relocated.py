import json
import os
from pathlib import Path
import subprocess
import zipfile

ROOT=Path(__file__).resolve().parents[1]

def main():
    archive=ROOT/'dist/JapaneseTranslatorPortable.zip'
    destination=ROOT/'dist/独立 验证目录'
    with zipfile.ZipFile(archive) as bundle:
        assert bundle.testzip() is None
        bundle.extractall(destination)
    folder=destination/'JapaneseTranslator'
    env=dict(os.environ)
    for key in ('PYTHONPATH','PYTHONHOME','QT_PLUGIN_PATH','QT_QPA_PLATFORM','VIRTUAL_ENV'):
        env.pop(key,None)
    env['PATH']=str(Path(os.environ['SYSTEMROOT'])/'System32')
    env['LOCALAPPDATA']=str(ROOT/'reports/local/relocated-appdata')
    report=ROOT/'reports/relocated-offline.json'
    process=subprocess.run([str(folder/'JapaneseTranslator.exe'),'--smoke-test','--report',str(report),'--work-dir',str(ROOT/'reports/local/relocated')],cwd=destination,env=env,timeout=300)
    assert process.returncode==0,process.returncode
    result=json.loads(report.read_text(encoding='utf-8'))
    assert result['status']=='PASS',result
    print('ZIP CRC + Chinese/space relocation + clean runtime PATH PASS',len(result['tests']))

if __name__=='__main__':
    main()
