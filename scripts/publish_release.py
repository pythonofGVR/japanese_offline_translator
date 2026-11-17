"""Upload this task's draft assets, then download and hash them before publishing."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor,as_completed

ROOT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--gh',required=True)
    parser.add_argument('--repo',default='pythonofGVR/japanese_offline_translator')
    parser.add_argument('--tag',default='v1.1.1')
    args=parser.parse_args()
    assets=ROOT/'dist/release-v1.1.1'
    receipt_path=ROOT/'reports/v1.1.1-release-upload.json'
    def gh(*arguments,capture=False,check=True):
        for attempt in range(3 if capture else 1):
            result=subprocess.run([args.gh,*map(str,arguments)],cwd=ROOT,text=True,encoding='utf-8',stdout=subprocess.PIPE if capture else None,stderr=subprocess.PIPE if capture else None,timeout=1800)
            if result.returncode==0:break
            if capture:time.sleep(1)
        if check and result.returncode:
            raise RuntimeError(result.stderr or f'GitHub CLI failed: {arguments[0]}')
        return result
    def find_release():
        releases=json.loads(gh('api',f'repos/{args.repo}/releases?per_page=100','-H','Cache-Control: no-cache',capture=True).stdout)
        return next((r for r in releases if r['tag_name']==args.tag),None)
    release=find_release()
    if release:
        receipt=json.loads(receipt_path.read_text(encoding='utf-8')) if receipt_path.exists() else {}
        if receipt.get('id')!=release['id'] or receipt.get('repository')!=args.repo or not release['draft']:
            raise RuntimeError('Existing release is not this task draft; refusing to overwrite it.')
    else:
        branch=subprocess.check_output(['git','-c',f'safe.directory={ROOT.as_posix()}','branch','--show-current'],cwd=ROOT,text=True).strip()
        gh('release','create',args.tag,'--repo',args.repo,'--target',branch,'--draft','--title','Japanese Offline Translator v1.1.1','--notes-file',ROOT/'reports/v1.1.1-release-notes.md')
        for attempt in range(5):
            release=find_release()
            if release:break
            time.sleep(1)
        if not release:raise RuntimeError('Draft receipt unavailable')
    receipt=dict(id=release['id'],repository=args.repo,tag=args.tag,draft=True,uploaded=[])
    receipt_path.write_text(json.dumps(receipt,indent=2),encoding='utf-8')
    def upload(path):
        if path.stat().st_size>=2*1024**3:raise RuntimeError('Asset exceeds 2 GiB')
        with path.open('rb') as stream:expected=hashlib.file_digest(stream,'sha256').hexdigest()
        remote=next((a for a in release['assets'] if a['name']==path.name),None)
        if not (remote and remote.get('digest')=='sha256:'+expected):
            for attempt in range(1,4):
                print(f'Uploading {path.name} ({path.stat().st_size:,} bytes), attempt {attempt}',flush=True)
                result=gh('release','upload',args.tag,path,'--repo',args.repo,'--clobber',check=False)
                if result.returncode==0:break
            else:raise RuntimeError('Upload failed; task draft retained for resuming')
        return dict(name=path.name,sha256=expected,bytes=path.stat().st_size)
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures=[pool.submit(upload,path) for path in sorted(assets.iterdir()) if path.is_file()]
        for future in as_completed(futures):
            receipt['uploaded'].append(future.result())
            receipt_path.write_text(json.dumps(receipt,indent=2),encoding='utf-8')
    destination=ROOT/'downloads/github-v1.1.1-verify';destination.mkdir(parents=True,exist_ok=True)
    print('Downloading complete draft assets for independent hash verification',flush=True)
    gh('release','download',args.tag,'--repo',args.repo,'--dir',destination,'--clobber')
    for record in receipt['uploaded']:
        with (destination/record['name']).open('rb') as stream:actual=hashlib.file_digest(stream,'sha256').hexdigest()
        if actual!=record['sha256']:raise RuntimeError('Downloaded hash mismatch: '+record['name'])
        print('Verified download: '+record['name'],flush=True)
    receipt['download_hashes_verified']=True
    receipt_path.write_text(json.dumps(receipt,indent=2),encoding='utf-8')
    print('DRAFT UPLOAD AND DOWNLOAD VERIFIED. Installer verification required before publication.',flush=True)

if __name__=='__main__':main()
