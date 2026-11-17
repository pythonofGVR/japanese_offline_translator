import hashlib
import json
from pathlib import Path
from build_v11 import ROOT,install_and_validate

def main():
    assets=ROOT/'downloads/github-v1.1.2-verify'
    records=[]
    for line in (assets/'SHA256SUMS.txt').read_text(encoding='utf-8').splitlines():
        expected,name=line.split('  ',1)
        path=assets/name
        with path.open('rb') as stream:actual=hashlib.file_digest(stream,'sha256').hexdigest()
        assert expected==actual,name
        records.append(dict(name=name,bytes=path.stat().st_size,sha256=actual))
    checks=install_and_validate(assets,'GitHub 下载 安装验证')
    result=dict(status='PASS',downloaded_from_github=True,all_asset_hashes_match=True,artifacts=records,installed_modes={mode:dict(status=r['status'],checks=len(r['tests']),native_gui_status=r['native_gui']['status'],native_gui_checks=len(r['native_gui']['tests']),loaded_icu=r['native_gui']['loaded_icu']) for mode,r in zip(('cpu','gpu','no-gpu'),checks)},network_scope=checks[0]['offline_scope'],independent_second_windows_host=False)
    (ROOT/'reports/v1.1.2-github-verified.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print('GITHUB-DOWNLOADED INSTALLER VERIFIED: CPU, GPU, fallback, file editing',flush=True)

if __name__=='__main__':main()
