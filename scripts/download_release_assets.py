"""Download real GitHub asset bytes, verify each range and the assembled SHA-256."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import os
from pathlib import Path
import shutil
import subprocess

def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()

def download_verified(gh, repo, release, records, source, destination):
    destination.mkdir(parents=True,exist_ok=True)
    cache=destination.parent/(destination.name+'-ranges')
    pending=[];jobs=[];step=16*1024*1024
    for record in records:
        target=destination/record['name']
        if target.is_file() and target.stat().st_size==record['bytes'] and digest(target)==record['sha256']:
            print('Verified existing download: '+record['name'],flush=True)
            continue
        master=source/record['name']
        if digest(master)!=record['sha256']:raise RuntimeError('Local release changed: '+record['name'])
        asset=next(a for a in release['assets'] if a['name']==record['name'])
        chunks=cache/record['name'];chunks.mkdir(parents=True,exist_ok=True)
        parts=[]
        with master.open('rb') as stream:
            for start in range(0,record['bytes'],step):
                # The local file supplies expected hashes only, never download data.
                expected=stream.read(min(step,record['bytes']-start))
                sha=hashlib.sha256(expected).hexdigest()
                path=chunks/str(start)
                part=(asset['id'],record['name'],start,len(expected),sha,path)
                parts.append(part)
                if not (path.is_file() and path.stat().st_size==len(expected) and digest(path)==sha):jobs.append(part)
        pending.append((record,target,parts))
    def fetch(part):
        asset_id,name,start,size,sha,path=part
        temporary=path.with_suffix('.partial')
        for attempt in range(4):
            try:
                with temporary.open('wb') as output:
                    process=subprocess.run([gh,'api',f'repos/{repo}/releases/assets/{asset_id}?segment={start}','-H','Accept: application/octet-stream','-H',f'Range: bytes={start}-{start+size-1}'],stdout=output,timeout=100)
                if process.returncode==0 and temporary.stat().st_size==size and digest(temporary)==sha:
                    os.replace(temporary,path)
                    return
            except subprocess.TimeoutExpired:
                pass
            print(f'Retry remote range: {name}, {start}, attempt {attempt+2}',flush=True)
        raise RuntimeError(f'Cannot verify downloaded range: {name}, {start}')
    with ThreadPoolExecutor(max_workers=16) as pool:
        futures=[pool.submit(fetch,part) for part in jobs]
        for count,future in enumerate(as_completed(futures),1):
            future.result()
            if count%8==0 or count==len(jobs):print(f'Verified GitHub ranges: {count}/{len(jobs)}',flush=True)
    for record,target,parts in pending:
        assembling=target.with_suffix(target.suffix+'.assembling')
        with assembling.open('wb') as output:
            for part in parts:
                with part[-1].open('rb') as stream:shutil.copyfileobj(stream,output)
        if assembling.stat().st_size!=record['bytes'] or digest(assembling)!=record['sha256']:
            raise RuntimeError('Downloaded file hash mismatch: '+record['name'])
        os.replace(assembling,target)
        print('Verified GitHub download: '+record['name'],flush=True)
