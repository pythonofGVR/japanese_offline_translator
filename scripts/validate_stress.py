import dataclasses
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from jot.engine import Engine
from jot.jobs import Control,InputFile,Settings,Cancelled,translate_file
from jot.formats import load_document
from jot.validation import deny_network

def main():
    deny_network()
    work=ROOT/'reports/local/stress'
    work.mkdir(parents=True,exist_ok=True)
    source=work/'10000-cues.srt'
    def timestamp(second):
        return f'{second//3600:02d}:{second//60%60:02d}:{second%60:02d},000'
    source.write_text('\n\n'.join(f'{i+1}\n{timestamp(i)} --> {timestamp(i+1)}\n今日は晴れです。' for i in range(10000))+'\n',encoding='utf-8')
    engine=Engine(cache_path=work/'cache.sqlite3');engine.load('fast',4)
    config=Settings(output=str(work/'output'))
    start=time.perf_counter()
    result=translate_file(InputFile(str(source)),config,engine,Control())
    seconds=time.perf_counter()-start
    assert len(load_document(result['output']).units)==10000
    assert len(result['rows'])==10000
    # Count actual infer calls; wrapper delegates to the real engine, never fabricates results.
    actual_infer=engine.infer
    calls=[0]
    def counted(*args,**kwargs):
        calls[0]+=1
        return actual_infer(*args,**kwargs)
    engine.infer=counted
    engine.translate(['これは別の文章です。'],quality='standard')
    first=calls[0]
    engine.translate(['これは別の文章です。'],quality='standard')
    assert calls[0]==first
    engine.translate(['これは別の文章です。'],language='en',quality='standard')
    assert calls[0]>first
    control=Control()
    cancelled=work/'cancel.txt';cancelled.write_text('これは中止する文章です。',encoding='utf-8')
    cancel_settings=Settings(output=str(work/'cancel-output'))
    try:
        translate_file(InputFile(str(cancelled)),cancel_settings,engine,control,lambda a,b: control.cancel())
        raise AssertionError('cancellation did not stop output')
    except Cancelled:
        pass
    assert not list((work/'cancel-output').glob('*'))
    engine.close()
    # The actual batch worker must continue after a malformed subtitle.
    from PySide6.QtCore import QCoreApplication
    from jot.gui import Worker
    app=QCoreApplication.instance() or QCoreApplication([])
    bad=work/'bad.srt';bad.write_text('not a subtitle',encoding='utf-8')
    events=[]
    worker=Worker([(0,InputFile(str(bad))),(1,InputFile(str(source)))],config,Control())
    worker.file_state.connect(lambda i,state,result:events.append((i,state)))
    worker.start()
    while worker.isRunning():
        app.processEvents();time.sleep(.01)
    app.processEvents()
    assert (0,'失败') in events and (1,'已完成') in events,events
    report=dict(status='PASS',cues=10000,seconds=seconds,cache_hit_avoids_infer=True,language_cache_isolation=True,cancel_no_final_or_temp_output=True,batch_error_isolation=True,meaning_accuracy='not assessed by this stress test; repeated synthetic source text')
    (ROOT/'reports/stress.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print('10000 cues, cache isolation, safe cancellation, batch failure recovery PASS')

if __name__=='__main__':main()
