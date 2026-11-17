"""Real, network-denied release smoke test, also callable from the frozen EXE."""
import argparse
import dataclasses
import hashlib
import json
import os
from pathlib import Path
import platform
import socket
import tempfile
import threading
import time

from .engine import Engine, MODEL_NAMES
from .jobs import Control, InputFile, Settings, translate_file, scan, save_review
from .formats import TextDocument, load_document, FALLBACK_LINE_LIMIT
from .paths import app_root, write_json

SAMPLES = [
    ('今日は晴れです。','今天天气晴朗。','简单陈述'),
    ('昨日買った本を電車の中で読んでいたら、降りる駅を通り過ぎてしまいました。','在电车里读昨天买的书时，坐过了要下车的站。','长句'),
    ('えっ、本当に？そんなこと聞いてないよ。','啊，真的吗？我没听说过这种事。','口语'),
    ('あの、あの、私は、私は何も知りません。','那个，那个，我、我什么都不知道。','重复语气'),
    ('そうですね。','是啊。','短句'),
    ('田中さんは明日、東京に行きます。','田中先生明天去东京。','专名'),
    ('はい。でも、まだ決めていません。','是的。不过还没有决定。','对话'),
    ('この商品の価格は1000円です。谢谢。','这件商品的价格是1000日元。谢谢。','混合文本'),
    ('午後3時に、駅の前で会いましょう！','下午3点在车站前见吧！','数字符号'),
    ('ねえ、もう少し待って。','喂，再等一下。','语气'),
]

def deny_network():
    def denied(*args,**kwargs):
        raise RuntimeError('NETWORK FORBIDDEN by offline acceptance test')
    socket.socket.connect=denied
    socket.socket.connect_ex=denied
    socket.create_connection=denied
    socket.getaddrinfo=denied

def verify_models(root, keys=None):
    report={}
    for key in (keys or MODEL_NAMES):
        folder=root/'models'/key
        manifest=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
        for name,expected in manifest['sha256'].items():
            with (folder/name).open('rb') as stream:
                actual=hashlib.file_digest(stream,'sha256').hexdigest()
            if actual!=expected:
                raise ValueError(f'模型文件校验失败：{key}/{name}')
        report[key]={'bytes':sum(p.stat().st_size for p in folder.iterdir() if p.is_file()),'repository':manifest['repository'],'revision':manifest['revision']}
    return report

def fixtures(folder):
    folder.mkdir(parents=True,exist_ok=True)
    srt='1\n00:00:01,000 --> 00:00:03,000\n今日は晴れです。\n\n2\n00:00:04,000 --> 00:00:06,000\n<i>明日、東京に行きます。</i>\n'
    ass='[Script Info]\nTitle: テスト\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\nDialogue: 0,0:00:01.00,0:00:03.00,Default,田中,0,0,0,,{\\an8}今日は晴れです。\\Nはい。\n'
    texts={'sample.srt':srt,'second.srt':srt,'sample.ass':ass,'sample.ssa':ass,'sample.vtt':'WEBVTT\n\ncue-1\n00:01.000 --> 00:03.000 line:80%\n<v 田中>今日は晴れです。</v>\n','sample.lrc':'[ar:田中]\n[00:01.20]今日は晴れです。\n','sample.txt':'今日は晴れです。\n\n明日、東京に行きます。\n','sample.md':'# 日本語\n\n今日は晴れです。[公式](https://example.com)\n\n```python\nprint("日本語")\n```\n'}
    for name,text in texts.items():
        (folder/name).write_text(text,encoding='utf-8')
    sub=folder/'子目录';sub.mkdir(exist_ok=True)
    (sub/'字幕.srt').write_text(srt,encoding='cp932')
    from docx import Document
    doc=Document();doc.add_paragraph().add_run('今日は晴れです。').bold=True
    doc.add_table(rows=1,cols=1).cell(0,0).text='明日、東京に行きます。'
    doc.save(folder/'sample.docx')
    # A small valid PDF using a standard Japanese CID font; no font download.
    from pypdf import PdfWriter
    from pypdf.generic import DictionaryObject,NameObject,ArrayObject,NumberObject,TextStringObject,DecodedStreamObject
    writer=PdfWriter();page=writer.add_blank_page(width=595,height=842)
    descendant=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/CIDFontType0'),NameObject('/BaseFont'):NameObject('/HeiseiMin-W3'),NameObject('/CIDSystemInfo'):DictionaryObject({NameObject('/Registry'):TextStringObject('Adobe'),NameObject('/Ordering'):TextStringObject('Japan1'),NameObject('/Supplement'):NumberObject(5)})})
    font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type0'),NameObject('/BaseFont'):NameObject('/HeiseiMin-W3'),NameObject('/Encoding'):NameObject('/UniJIS-UTF16-H'),NameObject('/DescendantFonts'):ArrayObject([writer._add_object(descendant)])})
    chars=sorted(set('今日は晴れです。'))
    mappings='\n'.join(f'<{ord(c):04X}> <{ord(c):04X}>' for c in chars)
    cmap=DecodedStreamObject()
    cmap.set_data(('/CIDInit /ProcSet findresource begin\n12 dict begin\nbegincmap\n/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def\n/CMapName /Adobe-Identity-UCS def\n/CMapType 2 def\n1 begincodespacerange\n<0000> <FFFF>\nendcodespacerange\n'+str(len(chars))+' beginbfchar\n'+mappings+'\nendbfchar\nendcmap\nCMapName currentdict /CMap defineresource pop\nend\nend').encode('ascii'))
    font[NameObject('/ToUnicode')]=writer._add_object(cmap)
    page[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):writer._add_object(font)})})
    content=DecodedStreamObject();content.set_data(b'BT /F1 16 Tf 50 750 Td <'+'今日は晴れです。'.encode('utf-16-be').hex().encode()+b'> Tj ET')
    page[NameObject('/Contents')]=writer._add_object(content);writer.write(folder/'sample.pdf')
    return folder

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--smoke-test',action='store_true')
    parser.add_argument('--report',required=True)
    parser.add_argument('--work-dir')
    parser.add_argument('--skip-hashes',action='store_true')
    parser.add_argument('--models',nargs='+',choices=list(MODEL_NAMES),default=list(MODEL_NAMES))
    parser.add_argument('--device',choices=['cpu','cuda'],default='cpu')
    parser.add_argument('--require-device',choices=['cpu','cuda'])
    parser.add_argument('--simulate-no-gpu',action='store_true')
    parser.add_argument('--subtitles-dir',type=Path,help='Optional private local SRT acceptance inputs; report contains metrics only')
    args=parser.parse_args()
    root=app_root()
    result={'status':'FAIL','platform':platform.platform(),'cpu':platform.processor(),'logical_cpus':os.cpu_count(),'offline_scope':'Python socket connect/connect_ex/create_connection/getaddrinfo disabled before model loading; native library not firewall-blocked','models':{},'tests':[]}
    deny_network()
    if args.simulate_no_gpu:
        import ctranslate2
        ctranslate2.get_cuda_device_count=lambda:0
        result['gpu_absence_simulated']=True
    import psutil
    process=psutil.Process()
    result['memory_total_bytes']=psutil.virtual_memory().total
    peak=[process.memory_info().rss]
    stop=threading.Event()
    def sample_memory():
        while not stop.wait(.02):
            peak[0]=max(peak[0],process.memory_info().rss)
    sampler=threading.Thread(target=sample_memory,daemon=True);sampler.start()
    work=Path(args.work_dir or tempfile.mkdtemp(prefix='jot-offline-')).resolve()
    work.mkdir(parents=True,exist_ok=True)
    engine=None
    try:
        if not args.skip_hashes:
            result['models']=verify_models(root,args.models)
        source_dir=fixtures(work/'日本語 空格')
        assert load_document(source_dir/'sample.pdf').units[0].source=='今日は晴れです。'
        engine=Engine(cache_path=work/'validation.sqlite3')
        for key in args.models:
            engine.load(key,4,args.device)
            model=result['models'].setdefault(key,{})
            model['load_seconds']=engine.load_seconds
            peak[0]=process.memory_info().rss
            start=time.perf_counter()
            texts=[s[0] for s in SAMPLES]
            target,initial,flags=engine.translate(texts,quality='auto',force=True)
            model['sample_seconds']=time.perf_counter()-start
            model['samples']=[dict(source=s[0],reference=s[1],category=s[2],initial=a,target=b,warnings=f) for s,a,b,f in zip(SAMPLES,initial,target,flags)]
            assert all(t.strip() for t in target)
            assert any(t!=s for t,s in zip(target,texts))
            model['peak_rss_bytes']=peak[0]
            files,skipped=scan(source_dir,True,work/'output')
            settings=Settings(model=key,output=str(work/'output'/key),device=args.device)
            for entry in files:
                original=Path(entry.path).read_bytes()
                start=time.perf_counter()
                translated=translate_file(entry,settings,engine,Control())
                assert translated['status']=='已完成'
                assert original==Path(entry.path).read_bytes()
                assert Path(translated['output']).is_file()
                if Path(entry.path).suffix in ('.srt','.ass','.ssa','.vtt','.lrc'):
                    before=load_document(entry.path);after=load_document(translated['output'])
                    assert [u.label for u in before.units]==[u.label for u in after.units]
                if Path(entry.path).suffix=='.docx':
                    from docx import Document
                    checked=Document(translated['output'])
                    assert checked.paragraphs[0].runs[0].bold and len(checked.tables)==1
                if Path(entry.path).suffix=='.md':
                    content=Path(translated['output']).read_text(encoding='utf-8')
                    assert 'print("日本語")' in content and 'https://example.com' in content
                # Exercise actual review reconstruction without altering the original.
                save_review(translated,[r['target'] for r in translated['rows']])
                result['tests'].append({'model':key,'file':str(Path(entry.path).relative_to(source_dir)),'status':'PASS','seconds':time.perf_counter()-start})
            # Traditional Chinese and English use the same real local model.
            for language in ('zh-TW','en'):
                value=engine.translate(['今日は晴れです。'],language=language,force=True)[0][0]
                assert value.strip()
                model[language]=value
            model['device']=engine.device
            model['compute_type']=engine.compute_type
            model['fallback_reason']=engine.fallback_reason
            if args.require_device:
                assert engine.device==args.require_device,engine.fallback_reason
            if args.subtitles_dir:
                import re
                for number, path in enumerate(sorted(args.subtitles_dir.glob('*.srt')),1):
                    original=path.read_bytes()
                    before=load_document(path)
                    translated=translate_file(InputFile(str(path)),Settings(model=key,device=args.device,quality='best',output=str(work/'private-output'/key)),engine,Control())
                    output=Path(translated['output'])
                    after=load_document(output)
                    assert path.read_bytes()==original
                    assert [u.label for u in before.units]==[u.label for u in after.units]
                    assert all(p.suffix=='.srt' for p in output.parent.iterdir())
                    for unit,row in zip(after.units,translated['rows']):
                        assert unit.source.strip()
                        if any(w.startswith('保留原文：') for w in row['warnings']):
                            assert not re.search(r'[\r\n]|\\[Nn]',unit.source)
                            assert len(re.sub(r'\{[^{}]*\}|<[^>\n]+>','',unit.source))<=FALLBACK_LINE_LIMIT
                    result['tests'].append(dict(case='private SRT complete-file acceptance',model=key,sample=number,cues=len(before.units),fallback_cues=translated['fallback_count'],sha256=hashlib.sha256(original).hexdigest(),status='PASS'))
        # Switching back must unload the larger model and reload the smaller one.
        if len(args.models)>1:
            engine.load('fast',4,args.device)
            assert engine.key=='fast'
            result['tests'].append({'case':'model switch quality -> fast','status':'PASS'})
        from .editor import EditableFile
        # Fault injection exercises the packaged recovery code, not just source tests.
        failed_input=work/'decoder-failure.srt'
        failed_input.write_text('1\n00:00:01,000 --> 00:00:03,000\n'+'長い原文です。'*20+'\n次の行。\n',encoding='utf-8')
        saved_infer=engine.infer
        def broken_decoder(*args,**kwargs):
            raise RuntimeError('injected decoder failure')
        try:
            engine.infer=broken_decoder
            recovery=translate_file(InputFile(str(failed_input)),Settings(output=str(work/'failure-output')),engine,Control())
        finally:
            engine.infer=saved_infer
        recovered=load_document(recovery['output']).units[0].source
        assert recovery['fallback_count']==1 and len(recovered)<=FALLBACK_LINE_LIMIT and '\n' not in recovered
        assert any('injected decoder failure' in w for w in recovery['rows'][0]['warnings'])
        assert [p.name for p in Path(recovery['output']).parent.iterdir()]==[Path(recovery['output']).name]
        result['tests'].append({'case':'decoder failure produces saved bounded original with specific reason; output only translation','status':'PASS'})
        translated=engine.translate([SAMPLES[0][0]],force=True)[0][0]
        standalone=work/'standalone-translation.txt'
        standalone.write_text(translated,encoding='utf-8')
        editor=EditableFile(standalone)
        backup=editor.save(translated+' 已编辑。')
        assert backup and backup.read_text(encoding='utf-8')==translated
        assert standalone.read_text(encoding='utf-8').endswith('已编辑。')
        result['tests'].append({'case':'standalone translated text editing and backup','status':'PASS'})
        from docx import Document
        word=work/'standalone-translation.docx'
        doc=Document();doc.add_paragraph().add_run(translated).bold=True;doc.save(word)
        editor=EditableFile(word)
        editor.save([translated+' 已编辑。'])
        checked=Document(word)
        assert checked.paragraphs[0].runs[0].bold
        assert checked.paragraphs[0].text.endswith('已编辑。')
        result['tests'].append({'case':'standalone translated DOCX editing preserving format','status':'PASS'})
        try:
            socket.create_connection(('example.com',443))
            raise AssertionError('network unexpectedly enabled')
        except RuntimeError:
            result['tests'].append({'case':'Python network denied','status':'PASS'})
        result['status']='PASS'
    except Exception as exc:
        import traceback
        result['error']=str(exc)
        result['traceback']=traceback.format_exc()
    finally:
        stop.set();sampler.join()
        if engine: engine.close()
        write_json(args.report,result)
    return 0 if result['status']=='PASS' else 1

if __name__=='__main__':
    raise SystemExit(main())
