"""Publish only this task's verified draft, then verify unauthenticated access."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import time
import urllib.request
import hashlib

ROOT=Path(__file__).resolve().parents[1]

def require(condition,message):
    if not condition:raise RuntimeError(message)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--gh',required=True)
    parser.add_argument('--tag',default='v1.1.2')
    parser.add_argument('--repo',default='pythonofGVR/japanese_offline_translator')
    args=parser.parse_args()
    require(bool(re.fullmatch(r'v\d+\.\d+\.\d+',args.tag)),'Invalid version tag')
    def read(suffix):return json.loads((ROOT/'reports'/f'{args.tag}-{suffix}.json').read_text(encoding='utf-8'))
    uploaded=read('release-upload');verified=read('github-verified')
    require(uploaded['repository']==args.repo and uploaded['tag']==args.tag,'Draft ownership mismatch')
    require(uploaded.get('download_hashes_verified') and len(uploaded['uploaded'])==7,'All downloads must be verified')
    require(verified['status']=='PASS' and verified['all_asset_hashes_match'],'Downloaded installer failed acceptance')
    require(set(verified['installed_modes'])=={'cpu','gpu','no-gpu'},'All three installation modes are required')
    require(all(m['status']=='PASS' and m['checks']==27 and m.get('native_gui_status')=='PASS' and m.get('native_gui_checks')==4 for m in verified['installed_modes'].values()),'Native GUI and translation checks required in every mode')
    require(read('normal-startup')['status']=='PASS' and read('native-real-quality')['status']=='PASS','Normal startup and full subtitle GUI acceptance required')
    def gh(*arguments):
        for attempt in range(5):
            try:return subprocess.check_output([args.gh,*map(str,arguments)],cwd=ROOT,text=True,encoding='utf-8',timeout=120)
            except (subprocess.CalledProcessError,subprocess.TimeoutExpired):
                if attempt==4:raise
                time.sleep(2)
    remote=json.loads(gh('api',f'repos/{args.repo}/releases/{uploaded["id"]}'))
    require(remote['id']==uploaded['id'] and remote['tag_name']==args.tag,'Remote draft changed')
    require(len(remote['assets'])==7,'Unexpected release attachments')
    for record in uploaded['uploaded']:
        asset=next(a for a in remote['assets'] if a['name']==record['name'])
        require(asset['state']=='uploaded' and asset['size']==record['bytes'] and asset['digest']=='sha256:'+record['sha256'],'Remote asset mismatch')
    if remote['draft']:
        payload=ROOT/'reports/local/publish-payload.json'
        payload.write_text(json.dumps(dict(draft=False,make_latest='true',body=(ROOT/'reports'/f'{args.tag}-release-notes.md').read_text(encoding='utf-8'))),encoding='utf-8')
        gh('api','--method','PATCH',f'repos/{args.repo}/releases/{uploaded["id"]}','--input',payload)
    opener=urllib.request.build_opener(urllib.request.ProxyHandler())
    public=None
    for attempt in range(8):
        try:
            request=urllib.request.Request(f'https://api.github.com/repos/{args.repo}/releases/tags/{args.tag}?verify={time.time_ns()}',headers={'User-Agent':'OfflineTranslator-Release-Verification','Cache-Control':'no-cache'})
            with opener.open(request,timeout=60) as response:public=json.load(response)
            break
        except Exception:
            if attempt==7:raise
            time.sleep(2)
    require(public and public['id']==uploaded['id'] and not public['draft'],'Anonymous release access failed')
    asset=next(a for a in public['assets'] if a['name']=='INSTALL_OFFLINE.md')
    with opener.open(asset['browser_download_url']+'?verify='+str(time.time_ns()),timeout=60) as response:
        actual=hashlib.sha256(response.read()).hexdigest()
    require(actual==next(a['sha256'] for a in uploaded['uploaded'] if a['name']=='INSTALL_OFFLINE.md'),'Anonymous download mismatch')
    result=dict(id=public['id'],tag=args.tag,url=public['html_url'],draft=False,anonymous_api_access=True,anonymous_asset_access=True,downloaded_installer_verified='PASS',assets=uploaded['uploaded'])
    (ROOT/'reports'/f'{args.tag}-release-published.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print('PUBLISHED AND ANONYMOUS DOWNLOAD VERIFIED: '+public['html_url'],flush=True)

if __name__=='__main__':main()
