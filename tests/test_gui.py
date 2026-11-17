import os
import pytest

@pytest.fixture
def window(tmp_path,monkeypatch):
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path/'local'))
    from PySide6.QtWidgets import QApplication
    from jot.gui import MainWindow,STYLE
    app=QApplication.instance() or QApplication([])
    app.setStyleSheet(STYLE)
    w=MainWindow()
    w.show()
    app.processEvents()
    yield w,app
    w.review_dirty=False
    w.file_dirty=False
    w.close()

def test_add_remove_and_restore(window,tmp_path):
    from jot.jobs import InputFile
    from jot.gui import MainWindow
    w,app=window
    path=tmp_path/'日本語 空格.txt'
    path.write_text('今日は晴れです。',encoding='utf-8')
    w.add_inputs([InputFile(str(path)),InputFile(str(path))])
    assert w.files.rowCount()==1
    assert w.files.item(0,0).text()=='日本語 空格.txt'
    other=MainWindow()
    assert len(other.inputs)==1
    other.close()
    w.files.selectRow(0)
    w.remove_selected()
    assert w.files.rowCount()==0

def test_busy_and_small_layout(window):
    w,app=window
    w.resize(1000,700)
    app.processEvents()
    w.busy(True)
    assert not w.start_button.isEnabled()
    assert w.cancel_button.isEnabled()
    assert not w.model.isEnabled()
    w.busy(False)
    assert w.start_button.isEnabled()
    assert not w.cancel_button.isEnabled()

def test_failure_reason_is_visible_and_persisted(window,tmp_path):
    from jot.jobs import InputFile
    from jot.gui import MainWindow
    w,app=window
    source=tmp_path/'broken.srt';source.write_text('bad',encoding='utf-8')
    w.add_inputs([InputFile(str(source))])
    reason='保存译文失败：目标目录不可写（PermissionError）'
    w.file_state(0,'失败',{'reason':reason})
    w.files.selectRow(0);app.processEvents()
    assert w.files.item(0,4).text()==reason
    assert reason in w.task_details.toPlainText()
    other=MainWindow()
    assert other.results[0]['reason']==reason
    other.close()

def test_legacy_review_survives_two_session_restores(window,tmp_path):
    from dataclasses import asdict
    from jot.gui import MainWindow
    from jot.jobs import Settings,source_hash
    from jot.paths import write_json
    w,app=window
    source=tmp_path/'old-input.txt';source.write_text('こんにちは。',encoding='utf-8')
    output=tmp_path/'old-input.zh-CN.txt';output.write_text('你好。',encoding='utf-8')
    legacy=output.with_name(output.name+'.review.json')
    result=dict(status='已完成',source=str(source),source_hash=source_hash(source),output=str(output),settings=asdict(Settings()),rows=[dict(source='こんにちは。',target='你好。',initial='你好。',label='1',warnings=[])],warnings=[])
    write_json(legacy,result)
    write_json(w.session_path,[dict(path=str(source),root='',state='已完成',review=str(legacy))])
    first=MainWindow();assert first.states[0]=='已完成';first.close()
    second=MainWindow();assert second.states[0]=='已完成'
    assert second.results[0]['rows'][0]['target']=='你好。'
    second.close()

def test_gpu_and_parameter_controls(window):
    from jot.parameters import THREAD_MAX,DEFAULT_THREADS,DEFAULT_BEAM
    w,app=window
    assert w.device.count()==2
    assert w.threads.minimum()==1 and w.threads.maximum()==THREAD_MAX
    assert w.beam.minimum()==1 and w.beam.maximum()==10
    w.threads.setValue(THREAD_MAX);w.beam.setValue(10)
    w.reset_parameters.click()
    assert w.threads.value()==DEFAULT_THREADS and w.beam.value()==DEFAULT_BEAM
    w.device.setCurrentIndex(1)
    assert w.settings().device=='cuda'

def test_open_and_edit_output_directly(window,tmp_path):
    w,app=window
    path=tmp_path/'translation.txt';path.write_text('你好。',encoding='utf-8')
    w.load_translated_file(str(path))
    assert w.tabs.currentIndex()==3
    w.file_text.setPlainText('您好。')
    assert w.file_dirty
    w.save_translated_file()
    assert not w.file_dirty and path.read_text(encoding='utf-8')=='您好。'
    assert list(tmp_path.glob('translation.txt.*.bak'))

def test_single_retranslation_uses_selected_device_and_parameters(window,tmp_path,monkeypatch):
    from dataclasses import asdict
    from PySide6.QtCore import QThread,Signal
    from jot.jobs import Settings,source_hash
    import jot.gui as module
    captured=[]
    class RecordingWorker(QThread):
        message=Signal(str);file_state=Signal(int,str,object);progress=Signal(int,int);single_result=Signal(int,object)
        def __init__(self,items,settings,control,single=None):
            super().__init__();captured.append(settings)
        def run(self):pass
    monkeypatch.setattr(module,'Worker',RecordingWorker)
    w,app=window
    source=tmp_path/'s.txt';source.write_text('こんにちは。',encoding='utf-8')
    w.fill_review(dict(source=str(source),source_hash=source_hash(source),output=str(tmp_path/'t.txt'),settings=asdict(Settings(device='cpu')),rows=[dict(source='こんにちは。',target='你好。',initial='你好。',label='1',warnings=[])],warnings=[]))
    w.review.setCurrentCell(0,3)
    w.device.setCurrentIndex(1);w.threads.setValue(1);w.beam.setValue(7)
    w.retranslate()
    w.worker.wait(2000);app.processEvents()
    assert captured[0].device=='cuda' and captured[0].threads==1 and captured[0].beam==7

def test_review_edit_save(window,tmp_path):
    from jot.jobs import source_hash,Settings
    from dataclasses import asdict
    w,app=window
    source=tmp_path/'input.txt';source.write_text('こんにちは。',encoding='utf-8')
    output=tmp_path/'input.zh-CN.txt';output.write_text('你好。',encoding='utf-8')
    result=dict(status='已完成',source=str(source),source_hash=source_hash(source),output=str(output),settings=asdict(Settings()),rows=[dict(source='こんにちは。',target='你好。',initial='你好。',label='1',warnings=[])],warnings=[])
    w.fill_review(result)
    assert not w.review_dirty
    w.review.item(0,3).setText('您好。')
    assert w.review_dirty
    w.save_edits()
    assert output.read_text(encoding='utf-8')=='您好。'
    assert source.read_text(encoding='utf-8')=='こんにちは。'
    assert not w.review_dirty
    w.load_translated_file(str(output))
    w.file_text.setPlainText('再见。')
    w.save_translated_file()
    assert w.review.item(0,3).text()=='再见。'
    w.save_edits()
    assert output.read_text(encoding='utf-8')=='再见。'
