"""Native Qt end-to-end checks with real worker, real model, and screenshots."""
import json
import os
from pathlib import Path
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
os.environ['LOCALAPPDATA']=tempfile.mkdtemp(prefix='jot-gui-validation-')
from PySide6.QtCore import QTimer,Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from jot.gui import MainWindow,STYLE
from jot.jobs import InputFile
from jot.validation import fixtures,deny_network

def main():
    deny_network()
    work=Path(tempfile.mkdtemp(prefix='jot-gui-files-'))
    source=fixtures(work/'inputs')/'sample.srt'
    original=source.read_bytes()
    app=QApplication([]);app.setStyle('Fusion');app.setStyleSheet(STYLE)
    window=MainWindow();window.show()
    window.device.setCurrentIndex(1)
    window.output.setText(str(work/'output'))
    window.add_inputs([InputFile(str(source))])
    heartbeat=[0]
    timer=QTimer();timer.timeout.connect(lambda:heartbeat.__setitem__(0,heartbeat[0]+1));timer.start(20)
    QTest.mouseClick(window.start_button,Qt.MouseButton.LeftButton)
    QTest.qWait(50)
    assert window.worker is not None and not window.model.isEnabled()
    QTest.mouseClick(window.pause_button,Qt.MouseButton.LeftButton)
    assert not window.control.running.is_set()
    QTest.qWait(100)
    QTest.mouseClick(window.pause_button,Qt.MouseButton.LeftButton)
    start=time.perf_counter()
    while window.worker and time.perf_counter()-start<120:
        QTest.qWait(30)
    assert window.worker is None,'worker did not finish'
    assert window.states[0]=='已完成',window.log.toPlainText()
    assert window.results[0]['runtime']['device']=='cuda',window.log.toPlainText()
    assert heartbeat[0]>=5,'GUI event loop did not remain responsive'
    window.files.setCurrentCell(0,0);window.show_review()
    assert window.review.rowCount()==2
    window.review.item(0,3).setText('GUI\u6821\u5bf9\u4fdd\u5b58\u6d4b\u8bd5\u3002')
    QTest.mouseClick(window.save_button,Qt.MouseButton.LeftButton)
    output=Path(window.review_result['output'])
    assert 'GUI\u6821\u5bf9' in output.read_text(encoding='utf-8')
    window.review.setCurrentCell(0,3)
    QTest.mouseClick(window.retranslate_button,Qt.MouseButton.LeftButton)
    start=time.perf_counter()
    while window.worker and time.perf_counter()-start<120:
        QTest.qWait(30)
    assert window.worker is None
    assert 'GUI' not in window.review.item(0,3).text()
    QTest.mouseClick(window.save_button,Qt.MouseButton.LeftButton)
    assert source.read_bytes()==original
    window.grab().save(str(ROOT/'reports/gui-review.png'))
    window.open_selected_output()
    assert window.editable_file is not None
    old=window.file_text.toPlainText()
    target=window.review_result['rows'][0]['target']
    window.file_text.setPlainText(old.replace(target,target+' 已校对。',1))
    QTest.mouseClick(window.save_file_button,Qt.MouseButton.LeftButton)
    assert not window.file_dirty and '已校对' in output.read_text(encoding='utf-8')
    assert list(output.parent.glob(output.name+'.*.bak'))
    window.grab().save(str(ROOT/'reports/v1.1-editor.png'))
    window.tabs.setCurrentIndex(0)
    window.grab().save(str(ROOT/'reports/gui-native.png'))
    window.resize(1000,700);app.processEvents()
    window.grab().save(str(ROOT/'reports/gui-small.png'))
    report={'status':'PASS','device':'cuda','standalone_file_edit':True,'automatic_backup':True,'real_worker':True,'pause_resume':True,'event_loop_heartbeats':heartbeat[0],'manual_edit_save':True,'single_row_real_retranslation':True,'source_unchanged':True,'output':str(output)}
    (ROOT/'reports/gui-e2e.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    window.close()
    print('Native GUI end-to-end PASS')

if __name__=='__main__':
    main()
