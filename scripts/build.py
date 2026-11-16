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
            if any(word in label for word in ('license','copying','copyright','notice')) and Path(str(file)).suffix.lower() not in ('.py','.pyc') and distribution.locate_file(file).is_file():
                source=Path(distribution.locate_file(file))
                target=destination/name/str(file).replace('../','_').replace('..\\','_')
                target.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(source,target)
    (destination/'THIRD_PARTY_COMPONENTS.json').write_text(json.dumps(entries,ensure_ascii=False,indent=2),encoding='utf-8')

def main():
    from build_v11 import main as build_current_release
    build_current_release()

if __name__=='__main__':
    main()
