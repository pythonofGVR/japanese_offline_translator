"""Local-only full subtitle acceptance; public report contains metrics, no dialogue."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from jot.engine import Engine
from jot.formats import load_document, STRUCTURAL, FALLBACK_LINE_LIMIT
from jot.jobs import InputFile, Settings, Control, source_hash, translate_file
from jot.validation import deny_network

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--inputs', type=Path, required=True)
    parser.add_argument('--model', choices=['fast','quality'], default='fast')
    parser.add_argument('--device', default='cuda')
    args = parser.parse_args()
    work = ROOT/'reports/local'/f'srt-{args.model}-{args.device}'
    work.mkdir(parents=True, exist_ok=True)
    os.environ['LOCALAPPDATA'] = str(work/'appdata')
    deny_network()
    engine = Engine(cache_path=work/'cache.sqlite3')
    engine.load(args.model, 8, args.device)
    records = []
    for index, source in enumerate(sorted(args.inputs.glob('*.srt')),1):
        before = source_hash(source)
        doc = load_document(source)
        start = time.monotonic()
        result = translate_file(InputFile(str(source)),Settings(model=args.model,device=args.device,threads=8,quality='best',output=str(work/'outputs')),engine,Control())
        output = Path(result['output'])
        parsed = load_document(output)
        assert source_hash(source) == before
        assert [u.label for u in doc.units] == [u.label for u in parsed.units]
        assert len(parsed.units) == len(doc.units)
        fallback = []
        for n, (unit, row) in enumerate(zip(parsed.units,result['rows'])):
            assert unit.source.strip()
            if any(w.startswith('保留原文：') for w in row['warnings']):
                assert not re.search(r'[\r\n]|\\[Nn]',unit.source)
                visible = re.sub(r'\{[^{}]*\}|<[^>\n]+>', '', unit.source)
                assert len(visible) <= FALLBACK_LINE_LIMIT
                fallback.append(n+1)
        assert all(p.suffix == '.srt' for p in output.parent.iterdir())
        assert not (output.parent/source.name).exists()
        record = dict(sample=index,sha256=before,cues=len(doc.units),status='PASS',fallback_cues=len(fallback),translated_or_non_japanese_cues=len(doc.units)-len(fallback),nonempty=True,timings_and_count_preserved=True,source_unchanged=True,output_directory_only_translations=True,fallback_limit=FALLBACK_LINE_LIMIT,seconds=round(time.monotonic()-start,2))
        records.append(record)
        print(json.dumps(record),flush=True)
        # Full private review stays ignored, available for manual quality inspection.
        (work/f'sample-{index}.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    engine.close()
    report=dict(status='PASS',model=args.model,device=engine.device,samples=records,network_scope='Python socket connections denied; no whole-system firewall isolation',quality_scope='Structural and failure-recovery acceptance; machine translation still requires human review')
    (ROOT/'reports'/f'v1.1.1-srt-{args.model}-{args.device}.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')

if __name__ == '__main__':
    main()
