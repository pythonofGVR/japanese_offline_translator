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
