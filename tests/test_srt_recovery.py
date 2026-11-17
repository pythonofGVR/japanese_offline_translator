import json
from pathlib import Path
import pytest

from jot.engine import Engine
from jot.formats import TextDocument, original_one_line, subtitle_problem
from jot.jobs import Control, InputFile, Settings, translate_file, save_review
from jot.reviews import review_path, load_review

def test_generated_colon_is_dialogue_but_tags_are_protected():
    doc = TextDocument('1\n00:00:01,000 --> 00:00:02,000\nこんにちは。\n', '.srt')
    assert '答：你好。' in doc.render(['答：你好。']).decode()
    assert subtitle_problem('<i>こんにちは。</i>', '你好。')
    assert subtitle_problem('太郎：こんにちは。', '小王：你好。')

def test_unknown_model_tokens_are_not_accepted_as_translation():
    from jot.quality import warnings
    assert '模型输出未知词标记' in warnings('こんにちは。','你好<unk>。')
    assert '模型输出未知词标记' in warnings('こんにちは。','⁇')

def test_original_fallback_is_single_bounded_line_and_preserves_tags():
    source = '<i>' + 'これは長い文です。'*20 + '</i>\n次の行です。'
    result = original_one_line(source)
    assert result.startswith('<i>') and '</i>' in result and '…' in result
    assert len(result.replace('<i>','').replace('</i>','')) == 42
    assert '\n' not in result and not subtitle_problem(source,result)

class Tokenizer:
    def encode(self, text):
        return list(text)

def test_batch_exception_isolated_and_failure_not_cached(tmp_path):
    engine = Engine(cache_path=tmp_path/'cache.sqlite3')
    engine.sp = Tokenizer()
    engine.key, engine.revision = 'fake','test'
    calls = []
    def infer(texts, language, beam, retry=0):
        calls.append(list(texts))
        if len(texts)>1 or '失敗' in texts[0]:
            raise RuntimeError('synthetic decoder error')
        return ['你好。']
    engine.infer = infer
    target, initial, flags = engine.translate(['こんにちは。','失敗です。'],quality='best')
    assert target == ['你好。','失敗です。']
    assert any('synthetic decoder error' in w for w in flags[1])
    assert len(calls) <= 5
    assert engine.db.execute('SELECT count(*) FROM cache').fetchone()[0] == 1
    engine.close()

class BrokenCueEngine:
    device, compute_type, fallback_reason = 'cpu','int8',''
    def translate(self, texts, *args, **kwargs):
        return ['你好。',''], ['你好。',''], [[],['保留原文：测试模型返回空结果']]

def test_partial_failure_saves_only_translation_and_local_review(tmp_path, monkeypatch):
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path/'local'))
    source = tmp_path/'sample.srt'
    text = '1\n00:00:01,000 --> 00:00:02,000\nこんにちは。\n\n2\n00:00:03,000 --> 00:00:04,000\n' + '長い文章です。'*20 + '\n次の行。\n'
    source.write_text(text, encoding='utf-8')
    result = translate_file(InputFile(str(source)),Settings(output=str(tmp_path/'out')),BrokenCueEngine(),Control())
    assert source.read_text(encoding='utf-8') == text
    output = Path(result['output'])
    assert list(output.parent.iterdir()) == [output]
    parsed = TextDocument(output.read_text(encoding='utf-8'),'.srt')
    assert len(parsed.units)==2 and parsed.units[0].source == '你好。'
    assert '\n' not in parsed.units[1].source and len(parsed.units[1].source)==42
    assert result['fallback_count']==1
    assert review_path(output).is_file()
    save_review(result,[u.source for u in parsed.units])
    assert load_review(output)['rows'][1]['source'].endswith('次の行。')

def test_review_store_failure_cannot_lose_output(tmp_path,monkeypatch):
    import jot.jobs as jobs
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path/'local'))
    source=tmp_path/'source.srt'
    source.write_text('1\n00:00:01,000 --> 00:00:02,000\n日本語\n\n2\n00:00:03,000 --> 00:00:04,000\n日本語\n',encoding='utf-8')
    def fail(*args,**kwargs):
        raise PermissionError('synthetic local review store denied')
    monkeypatch.setattr(jobs,'write_json',fail)
    result=translate_file(InputFile(str(source)),Settings(output=str(tmp_path/'out')),BrokenCueEngine(),Control())
    assert Path(result['output']).is_file() and result['status']=='已完成'
    assert any('synthetic local review store denied' in w for w in result['warnings'])

def test_invalid_srt_has_actionable_file_error(tmp_path):
    source=tmp_path/'broken.srt';source.write_text('missing timestamps',encoding='utf-8')
    with pytest.raises(RuntimeError,match='读取/解析失败') as error:
        translate_file(InputFile(str(source)),Settings(output=str(tmp_path/'out')),BrokenCueEngine(),Control())
    assert str(source) in str(error.value) and '时间轴' in str(error.value)
