from pathlib import Path
import pytest
from jot.jobs import Settings
from jot.parameters import THREAD_MAX, DEFAULT_THREADS, DEFAULT_BEAM, restored_integer
from jot.editor import EditableFile

@pytest.mark.parametrize('value',[0,-1,THREAD_MAX+1,True,'4',1.5])
def test_thread_limits(value):
    with pytest.raises(ValueError): Settings(threads=value)

@pytest.mark.parametrize('value',[0,-1,11,True,'3',2.5])
def test_beam_limits(value):
    with pytest.raises(ValueError): Settings(beam=value)

def test_defaults_and_legacy_settings():
    assert Settings().threads==DEFAULT_THREADS
    assert Settings().beam==DEFAULT_BEAM
    assert Settings().device=='cpu'
    assert Settings(**{'model':'fast','threads':DEFAULT_THREADS,'beam':3}).device=='cpu'
    assert restored_integer('broken',4,1,32)==4
    assert restored_integer(999,4,1,32)==32

def test_edit_srt_without_source_or_sidecar(tmp_path):
    path=tmp_path/'译文.zh-CN.srt'
    original='1\r\n00:00:01,000 --> 00:00:03,000\r\n<i>你好。</i>\r\n'
    path.write_bytes(original.encode())
    editor=EditableFile(path)
    backup=editor.save(editor.text.replace('你好。','您好。'))
    assert backup.read_bytes()==original.encode()
    assert '<i>您好。</i>' in path.read_text(encoding='utf-8')
    with pytest.raises(ValueError): editor.save(editor.text.replace('00:00:01,000','00:00:02,000'))
    with pytest.raises(ValueError): editor.save(editor.text.replace('<i>',''))

def test_external_change_protected(tmp_path):
    path=tmp_path/'a.txt';path.write_text('first',encoding='utf-8')
    editor=EditableFile(path);path.write_text('external',encoding='utf-8')
    with pytest.raises(ValueError,match='其他程序'):editor.save('new')
    assert path.read_text()=='external'

def test_save_as_and_docx_format(tmp_path):
    from docx import Document
    source=tmp_path/'译文.docx';doc=Document()
    doc.add_paragraph().add_run('你好。').bold=True
    doc.add_table(rows=1,cols=1).cell(0,0).text='表格'
    doc.save(source)
    editor=EditableFile(source)
    output=tmp_path/'edited.docx'
    editor.save(['您好。','新表格'],output)
    result=Document(output)
    assert result.paragraphs[0].runs[0].bold
    assert result.tables[0].cell(0,0).text=='新表格'
    assert Document(source).paragraphs[0].text=='你好。'

def test_gpu_absent_falls_back_to_real_cpu(tmp_path,monkeypatch):
    import ctranslate2
    from jot.engine import Engine
    from jot.validation import SAMPLES
    monkeypatch.setattr(ctranslate2,'get_cuda_device_count',lambda:0)
    engine=Engine(cache_path=tmp_path/'cache.sqlite3')
    try:
        engine.load('fast',device='cuda')
        assert engine.device=='cpu' and engine.fallback_reason
        target=engine.translate([SAMPLES[0][0]],force=True)[0][0]
        assert target and target!=SAMPLES[0][0]
    finally:engine.close()

def test_gpu_runtime_missing_falls_back(tmp_path,monkeypatch):
    import jot.engine as module
    from jot.engine import Engine
    def unavailable(root): raise OSError('GPU library unavailable in test')
    monkeypatch.setattr(module,'enable_cuda_libraries',unavailable)
    monkeypatch.setattr(__import__('ctranslate2'),'get_cuda_device_count',lambda:1)
    engine=Engine(cache_path=tmp_path/'cache.sqlite3')
    try:
        engine.load('fast',device='cuda')
        assert engine.device=='cpu'
        assert 'GPU library unavailable' in engine.fallback_reason
    finally:engine.close()

def test_gpu_inference_failure_retries_with_real_cpu(tmp_path):
    from jot.engine import Engine
    from jot.validation import SAMPLES
    class SimulatedDriverFailure:
        def translate_batch(self,*args,**kwargs):
            raise RuntimeError('injected GPU out of memory')
    engine=Engine(cache_path=tmp_path/'cache.sqlite3')
    try:
        engine.load('fast')
        engine.device='cuda'
        engine.translator=SimulatedDriverFailure()
        target=engine.infer([SAMPLES[0][0]])[0]
        assert target and target!=SAMPLES[0][0]
        assert engine.device=='cpu' and 'injected GPU' in engine.fallback_reason
    finally:engine.close()
