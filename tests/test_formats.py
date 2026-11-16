import io
from pathlib import Path
import zipfile
import pytest
from jot.formats import TextDocument, load_document, decode
from jot.jobs import scan, Settings, InputFile, reserve_output, Control, Cancelled
from jot.paths import atomic_write, default_output
from jot.quality import warnings, safe_cleanup

SRT = '1\r\n00:00:01,000 --> 00:00:02,000\r\nこんにちは。\r\n\r\n2\r\n00:00:03,000 --> 00:00:05,000\r\n<i>今日は晴れです。</i>\r\n'
ASS = '[Script Info]\nTitle: テスト\n[V4+ Styles]\nFormat: Name, Fontname, Fontsize\nStyle: Default,Arial,20\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\nDialogue: 0,0:00:01.00,0:00:02.00,Default,太郎,0,0,0,,{\\an8}こんにちは。\\Nはい。\nComment: 0,0:00:01.00,0:00:02.00,Default,,0,0,0,,変更しない\n'
VTT = 'WEBVTT\n\nSTYLE\n::cue {color: white;}\n\nNOTE 日本語の注釈\n\ncue-1\n00:01.000 --> 00:03.000 position:50% line:90%\n<v 太郎>こんにちは。</v>\n'
LRC = '[ar:日本人]\n[offset:200]\n[00:01.20][00:02.30]こんにちは。\n[00:04.00]今日は晴れです。\n'

@pytest.mark.parametrize('ext,text,translations',[('.srt',SRT,['你好。','<i>今天天气晴朗。</i>']),('.ass',ASS,['{\\an8}你好。\\N是的。']),('.ssa',ASS,['{\\an8}你好。\\N是的。']),('.vtt',VTT,['<v 太郎>你好。</v>']),('.lrc',LRC,['你好。','今天天气晴朗。'])])
def test_subtitle_envelope(ext,text,translations):
    doc=TextDocument(text,ext)
    parsed=TextDocument(doc.render(translations).decode('utf-8-sig'),ext)
    assert [u.label for u in doc.units]==[u.label for u in parsed.units]
    assert [u.source for u in parsed.units]==translations
    assert doc.render([u.source for u in doc.units]).decode('utf-8-sig')==text

@pytest.mark.parametrize('ext,text',[('.srt','1\nwrong\nこんにちは'),('.vtt','not vtt'),('.ass','[Events]\nDialogue: bad'),('.lrc','[ar:artist]')])
def test_reject_malformed(ext,text):
    with pytest.raises(ValueError): TextDocument(text,ext)

def test_tags_and_empty_protected():
    doc=TextDocument(SRT,'.srt')
    with pytest.raises(ValueError): doc.render(['你好','今天天气好'])
    with pytest.raises(ValueError): doc.render(['','<i>天气好</i>'])

@pytest.mark.parametrize('encoding',['utf-8','utf-8-sig','utf-16','cp932','shift_jis'])
def test_encoding(encoding):
    text='こんにちは。今日は晴れです。'
    assert decode(text.encode(encoding))==text

def test_text_markdown():
    text='# 日本語\n\n```python\nprint("日本語")\n```\n\n- こんにちは [公式](https://example.com)\n'
    doc=TextDocument(text,'.md')
    assert len(doc.units)==2
    out=doc.render(['日语','你好 [官方](https://example.com)']).decode()
    assert 'print("日本語")' in out and out.startswith('# 日语\n\n')

def test_docx_structure(tmp_path):
    from docx import Document
    path=tmp_path/'日本語.docx'
    doc=Document()
    doc.add_paragraph().add_run('こんにちは。').bold=True
    doc.add_table(rows=1,cols=1).cell(0,0).text='今日は晴れです。'
    doc.sections[0].header.paragraphs[0].text='日本語'
    doc.save(path)
    loaded=load_document(path)
    result=loaded.render(['翻译'+str(i) for i in range(len(loaded.units))])
    out=Document(io.BytesIO(result))
    assert out.paragraphs[0].runs[0].bold and len(out.tables)==1
    with zipfile.ZipFile(path) as before,zipfile.ZipFile(io.BytesIO(result)) as after:
        assert before.namelist()==after.namelist()
        assert before.read('word/styles.xml')==after.read('word/styles.xml')

def test_scanner_and_output_exclusion(tmp_path):
    (tmp_path/'sub').mkdir(); (tmp_path/'out').mkdir()
    (tmp_path/'a.srt').write_text(SRT,encoding='utf-8')
    (tmp_path/'a.zh-CN.srt').write_text(SRT,encoding='utf-8')
    (tmp_path/'sub'/'b.txt').write_text('こんにちは',encoding='utf-8')
    (tmp_path/'out'/'c.srt').write_text(SRT,encoding='utf-8')
    files,skipped=scan(tmp_path,True,tmp_path/'out')
    assert {Path(f.path).name for f in files}=={'a.srt','b.txt'} and skipped
    assert len(scan(tmp_path,False,tmp_path/'out')[0])==1

def test_output_collision_preserves_input(tmp_path):
    original=tmp_path/'a.srt'; original.write_bytes(SRT.encode())
    config=Settings(output=str(tmp_path))
    a=reserve_output(InputFile(str(original)),config)
    b=reserve_output(InputFile(str(original)),config)
    assert a!=b and a.name=='a.zh-CN.srt' and b.name=='a.zh-CN.1.srt'
    config.conflict='skip'
    assert reserve_output(InputFile(str(original)),config) is None
    assert original.read_bytes()==SRT.encode()

def test_default_output():
    assert default_output().is_absolute() and default_output().name=='JapaneseTranslatorOutput'

def test_cancellation_and_pause():
    control=Control(); control.running.clear(); control.cancel()
    with pytest.raises(Cancelled): control.boundary()

def test_quality_conservative():
    assert warnings('こんにちは。','こんにちは。')
    assert warnings('これはテストです。','嗯，嗯，嗯，嗯，嗯')
    assert safe_cleanup('  不，不，我不去！  ')=='不，不，我不去！'

def test_pdf_no_text(tmp_path):
    from pypdf import PdfWriter
    path=tmp_path/'scan.pdf'; writer=PdfWriter()
    writer.add_blank_page(width=200,height=200); writer.write(path)
    with pytest.raises(ValueError,match='OCR'): load_document(path)

def test_atomic_write(tmp_path):
    path=tmp_path/'中文 空格.txt'
    atomic_write(path,b'first'); atomic_write(path,b'second')
    assert path.read_bytes()==b'second' and list(tmp_path.iterdir())==[path]
