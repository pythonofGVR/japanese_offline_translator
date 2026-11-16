"""Optional from-source INT8 conversion. Never overwrites the bundled verified models.

Run in a separate conversion venv with scripts/conversion-requirements.txt.
The shipped release uses the pinned, LFS-hash-verified fairseq conversions instead.
This alternative transformers conversion path is supplied for reproducibility and
was not executed during this release; re-run full validation before substituting it.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

from prepare_models import MODELS,ROOT,download

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('model',choices=list(MODELS))
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    destination=args.output.resolve()
    if destination.exists():
        parser.error('Output already exists. Use a new directory to protect prior models.')
    if destination==ROOT/'models'/args.model:
        parser.error('Do not overwrite the bundled verified model.')
    from huggingface_hub import snapshot_download
    import ctranslate2
    _,_,upstream,revision=MODELS[args.model]
    source=Path(snapshot_download(upstream,revision=revision,cache_dir=ROOT/'downloads/hf-conversion',allow_patterns=['config.json','pytorch_model.bin','model.safetensors','sentencepiece.bpe.model','vocab.json','tokenizer_config.json','special_tokens_map.json','README.md']))
    converter=ctranslate2.converters.TransformersConverter(str(source),copy_files=['sentencepiece.bpe.model'])
    converter.convert(str(destination),quantization='int8')
    shutil.copy2(source/'README.md',destination/'UPSTREAM_MODEL_CARD.md')
    download('https://raw.githubusercontent.com/facebookresearch/fairseq/main/LICENSE',destination/'LICENSE')
    hashes={}
    for path in destination.iterdir():
        if path.is_file():
            with path.open('rb') as stream:hashes[path.name]=hashlib.file_digest(stream,'sha256').hexdigest()
    manifest=dict(repository=upstream,revision=revision,upstream=upstream,upstream_revision=revision,quantization='int8',conversion='CTranslate2 4.9.0 TransformersConverter',license='MIT',sha256=hashes)
    (destination/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print('Conversion finished. This output must pass the real-model acceptance suite before distribution.')

if __name__=='__main__':main()
