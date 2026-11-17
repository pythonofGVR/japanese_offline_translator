"""Native Windows frozen-window acceptance, with an actual translation worker."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
import traceback

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--gui-smoke-test',action='store_true')
    parser.add_argument('--device',choices=['cpu','cuda'],default='cpu')
    parser.add_argument('--require-device',choices=['cpu','cuda'])
    parser.add_argument('--simulate-no-gpu',action='store_true')
    parser.add_argument('--model',choices=['fast','quality'],default='fast')
    parser.add_argument('--subtitles-dir',type=Path)
    parser.add_argument('--report',type=Path,required=True)
    parser.add_argument('--work-dir',type=Path)
    parser.add_argument('--screenshot',type=Path)
    args=parser.parse_args()
    work=(args.work_dir or Path(tempfile.mkdtemp(prefix='jot-native-gui-'))).resolve()
    work.mkdir(parents=True,exist_ok=True)
    os.environ['LOCALAPPDATA']=str(work/'appdata')
    result=dict(status='FAIL',tests=[],model=args.model,requested_device=args.device)
    app=window=None
    try:
        from .validation import deny_network
        deny_network()
        from .startup import prepare_windows_icu
        result['loaded_icu']=prepare_windows_icu()
        from PySide6.QtCore import QTimer,qVersion
        from PySide6.QtWidgets import QApplication
        from .gui import MainWindow,STYLE
        from .jobs import InputFile
        from .formats import load_document
        from .paths import atomic_write
        if args.simulate_no_gpu:
            import ctranslate2
            ctranslate2.get_cuda_device_count=lambda:0
        app=QApplication([]);app.setStyle('Fusion');app.setStyleSheet(STYLE)
        assert app.platformName()=='windows','Native Windows platform plugin required'
        result['platform_plugin']=app.platformName();result['qt_version']=qVersion()
        window=MainWindow();window.show()
        window.output.setText(str(work/'outputs'))
        window.device.setCurrentIndex(window.device.findData(args.device))
        window.model.setCurrentIndex(window.model.findData(args.model))
        window.quality.setCurrentIndex(window.quality.findData('best'))
        if args.subtitles_dir:
            sources=sorted(args.subtitles_dir.glob('*.srt'))
            assert len(sources)==3
        else:
            source=work/'sample.srt'
            source.write_text('1\n00:00:01,000 --> 00:00:02,000\n今日は晴れです。\n\n2\n00:00:03,000 --> 00:00:04,000\n<i>明日、東京に行きます。</i>\n',encoding='utf-8')
            sources=[source]
        originals=[p.read_bytes() for p in sources]
        window.add_inputs([InputFile(str(p)) for p in sources])
        heartbeats=[0];started=[False];finished=[False];errors=[]
        start=time.monotonic()
        timer=QTimer()
        def tick():
            heartbeats[0]+=1
            try:
                if not started[0]:
                    assert window.isVisible() and window.winId()
                    result['tests'].append('QtCore/QtGui/QtWidgets import and native main window')
                    window.start_button.click();started[0]=True
                    assert window.worker is not None
                    return
                if time.monotonic()-start>1200:
                    raise TimeoutError('GUI translation worker timed out')
                if window.worker is not None:
                    return
                assert heartbeats[0]>3
                result['tests'].append('Qt event loop stays responsive during actual worker translation')
                metrics=[]
                for index,(source,original) in enumerate(zip(sources,originals)):
                    assert window.states[index]=='已完成',window.results.get(index,{}).get('reason','GUI task failed')
                    translated=window.results[index]
                    if args.require_device:
                        assert translated['runtime']['device']==args.require_device,translated['runtime']['fallback_reason']
                    output=Path(translated['output']);assert output.is_file()
                    before=load_document(source);after=load_document(output)
                    assert [u.label for u in before.units]==[u.label for u in after.units]
                    assert source.read_bytes()==original
                    metrics.append(dict(sample=index+1,cues=len(before.units),fallback_cues=translated['fallback_count'],device=translated['runtime']['device'],sha256=hashlib.sha256(original).hexdigest(),status='PASS'))
                assert all(p.suffix=='.srt' for p in (work/'outputs').iterdir())
                result['samples']=metrics
                result['tests'].append('SRT output saved; source, cue labels and timings preserved; output only translations')
                if not args.subtitles_dir:
                    window.files.setCurrentCell(0,0);window.show_review()
                    window.review.item(0,3).setText('今天天气晴朗，已校对。')
                    window.save_button.click()
                    output=Path(window.results[0]['output'])
                    assert '已校对' in output.read_text(encoding='utf-8')
                    window.open_selected_output()
                    window.file_text.setPlainText(window.file_text.toPlainText().replace('已校对','已编辑'))
                    window.save_file_button.click()
                    assert not window.file_dirty and '已编辑' in output.read_text(encoding='utf-8')
                    assert list(output.parent.glob(output.name+'.*.bak'))
                    result['tests'].append('Native review save and standalone output editing with backup')
                    if args.screenshot:
                        args.screenshot.parent.mkdir(parents=True,exist_ok=True)
                        assert window.grab().save(str(args.screenshot))
                result['heartbeats']=heartbeats[0]
                result['status']='PASS';finished[0]=True
                timer.stop();window.review_dirty=False;window.file_dirty=False;window.close();app.quit()
            except Exception:
                errors.append(traceback.format_exc());timer.stop()
                if window.worker:
                    window.control.cancel();window.worker.wait(120000)
                window.review_dirty=False;window.file_dirty=False;window.close();app.exit(1)
        timer.timeout.connect(tick);timer.start(30)
        app.exec()
        if errors:raise RuntimeError(errors[0])
        assert finished[0]
    except Exception:
        result['error']=traceback.format_exc()
    finally:
        from .paths import write_json
        write_json(args.report,result)
    return 0 if result['status']=='PASS' else 1
