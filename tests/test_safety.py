import threading
import time
import pytest
from jot.paths import atomic_write
from jot.jobs import Control, Cancelled, InputFile, Settings, reserve_output, reservation_path

def test_atomic_create_refuses_existing(tmp_path):
    path=tmp_path/'existing.txt'
    path.write_bytes(b'user content')
    with pytest.raises(FileExistsError): atomic_write(path,b'new',replace=False)
    assert path.read_bytes()==b'user content'
    assert list(tmp_path.iterdir())==[path]

def test_reservation_not_visible_as_final_file(tmp_path):
    source=tmp_path/'input.txt';source.write_text('original')
    target=reserve_output(InputFile(str(source)),Settings(output=str(tmp_path)))
    assert not target.exists()
    assert reservation_path(target).is_file()

def test_orphan_review_never_overwritten(tmp_path):
    source=tmp_path/'input.txt';source.write_text('original')
    review=tmp_path/'input.zh-CN.txt.review.json';review.write_text('user record')
    target=reserve_output(InputFile(str(source)),Settings(output=str(tmp_path)))
    assert target.name=='input.zh-CN.1.txt'
    assert review.read_text()=='user record'

def test_pause_resume_real_boundary():
    control=Control();control.running.clear()
    reached=threading.Event()
    thread=threading.Thread(target=lambda:(control.boundary(),reached.set()))
    thread.start()
    assert not reached.wait(.15)
    control.running.set()
    thread.join(2)
    assert reached.is_set()

def test_numeric_and_currency_quality_flags():
    from jot.quality import warnings
    assert any('币种' in w for w in warnings('価格は1000円です。','价格是1000元。'))
    assert any('数字' in w for w in warnings('午後3時に会います。','下午5点见。'))
    assert not warnings('価格は1000円です。','价格是1000日元。')
