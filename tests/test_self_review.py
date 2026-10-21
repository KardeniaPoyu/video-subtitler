"""Behavioral regressions found during the 0.5.0 independent review."""
import copy
import io
import json
import sqlite3
from pathlib import Path

import pytest

from subtitler.cli import main
from subtitler.delivery import deliver
from subtitler.evolution import sources
from subtitler.evolution.rules import canonical
from subtitler.evolution.runtime import open_policy
from subtitler.evolution.store import Memory
from subtitler.plugins.llm import to_id_map, windows
from subtitler.project import Project
from subtitler.subtitle import save_to_vtt
from subtitler.asr import SubtitleSegment


def invoke(args, expected=0):
    with pytest.raises(SystemExit) as error:
        main(args)
    assert error.value.code == expected


@pytest.fixture
def learned(tmp_path):
    memory = Memory.create(tmp_path / 'memory.sqlite3')
    scope = {'profile': 'course', 'source_lang': 'en', 'target_lang': 'zh', 'domains': ['education']}
    rule = {'kind': 'term', 'scope': scope, 'trigger': 'agent', 'replacement': '智能体',
            'aliases': ['代理'], 'exclude': []}
    quote = canonical(rule)
    with memory.db(write=True) as db:
        source = memory.add_source(db, 'local', 'glossary.json', quote)
    rid = memory.propose(source, rule, quote)
    memory.add_cases(rid, [
        {'name': 'course', 'context': scope,
         'input': {'text': 'An agent learns.', 'translation': '代理会学习。'},
         'expected': {'text': 'An agent learns.', 'translation': '智能体会学习。'}},
        {'name': 'other client', 'context': {**scope, 'profile': 'other'},
         'input': {'text': 'An agent learns.', 'translation': '代理会学习。'},
         'expected': {'text': 'An agent learns.', 'translation': '代理会学习。'}},
    ])
    memory.activate(rid, 'fixture-author')
    p = Project(path=str(tmp_path / 'project.json'), source_lang='en', target_lang='zh', domains=['education'],
                segments=[{'id': 1, 'start': 0.0, 'end': 4.0, 'text': 'An agent learns.', 'translation': ''},
                          {'id': 2, 'start': 5.0, 'end': 9.0, 'text': 'An agent helps.', 'translation': ''}])
    with open_policy(memory.path) as policy:
        policy.bind(p, 'course')
    return memory, p


def finish(memory, p):
    with open_policy(memory.path) as policy:
        p.apply({'1': '代理会学习。', '2': '代理会帮忙。'}, glossary=False, policy=policy)
        p.save()


def test_incremental_translation_saves_progress_but_cannot_deliver_pending_lines(learned, tmp_path):
    memory, p = learned
    with open_policy(memory.path) as policy:
        result = p.apply({'1': '代理会学习。'}, glossary=False, policy=policy)
        assert result['evolution']['pending_translations'] == 1
        p.save()
    saved = Project.load(p.path)
    assert saved.segments[0]['translation'] == '智能体会学习。'
    assert saved.segments[1]['translation'] == ''
    for draft in (False, True):
        with pytest.raises(ValueError, match='constraints violated'):
            deliver(saved, str(tmp_path / 'incomplete'), memory=memory.path, draft=draft)
    with open_policy(memory.path) as policy:
        saved.apply({'2': '代理会帮忙。'}, glossary=False, policy=policy)
    deliver(saved, str(tmp_path / 'complete'), memory=memory.path)


def test_unknown_nonempty_translation_is_still_rejected_atomically(learned):
    memory, p = learned
    before = copy.deepcopy(p)
    with open_policy(memory.path) as policy:
        with pytest.raises(ValueError, match='unresolved'):
            p.apply({'1': '他会学习。'}, glossary=False, policy=policy)
    assert p.segments == before.segments and p.evolution == before.evolution


def test_profile_change_invalidates_receipt_even_if_other_scope_has_no_rules(learned):
    memory, p = learned
    finish(memory, p)
    p.evolution['profile'] = 'other'
    with open_policy(memory.path) as policy:
        with pytest.raises(ValueError, match='content changed'):
            policy.check(p)


def test_wal_memory_is_rejected_before_policy_can_allow_concurrent_revision(learned):
    memory, _ = learned
    with sqlite3.connect(memory.path) as db:
        assert db.execute('PRAGMA journal_mode=WAL').fetchone()[0] == 'wal'
    with pytest.raises(ValueError, match='rollback journaling'):
        with open_policy(memory.path):
            pytest.fail('WAL policy must never be returned')
    with sqlite3.connect(memory.path) as db:
        db.execute('PRAGMA journal_mode=DELETE')
    assert memory.snapshot()['rules']


def test_bound_delivery_and_render_preserve_validated_punctuation(learned, tmp_path):
    memory, p = learned
    finish(memory, p)
    out = deliver(p, str(tmp_path / 'delivery'), memory=memory.path)
    for ext in ('srt', 'vtt', 'ass'):
        assert '智能体会学习。' in (out / ('subtitles.' + ext)).read_text('utf-8')
    invoke(['render', p.path, '--format', 'srt,vtt,ass', '-o', str(tmp_path / 'render'), '--memory', str(memory.path)])
    assert '智能体会学习。' in (tmp_path / 'render.srt').read_text('utf-8')


@pytest.mark.parametrize('formats', ['json', 'srt,', 'srt,srt', ''])
def test_render_rejects_invalid_formats_without_output(learned, tmp_path, formats):
    memory, p = learned
    finish(memory, p)
    invoke(['render', p.path, '--format', formats, '-o', str(tmp_path / 'out'), '--memory', str(memory.path)], 1)
    assert not list(tmp_path.glob('out*'))


def test_render_collision_does_not_overwrite_or_publish_first_format(learned, tmp_path):
    memory, p = learned
    finish(memory, p)
    existing = tmp_path / 'out.vtt'
    existing.write_text('keep the editor\'s work', 'utf-8')
    invoke(['render', p.path, '--format', 'srt,vtt', '-o', str(tmp_path / 'out'), '--memory', str(memory.path)], 1)
    assert existing.read_text('utf-8') == "keep the editor's work"
    assert not (tmp_path / 'out.srt').exists()


def test_render_rechecks_expiry_after_staging(learned, tmp_path, monkeypatch):
    import subtitler.evolution.runtime as runtime
    import subtitler.subtitle as subtitle
    memory, p = learned
    finish(memory, p)
    with memory.db(write=True) as db:
        db.execute('UPDATE sources SET expires=1000')
    monkeypatch.setattr(runtime.time, 'time', lambda: 999)
    original_save = subtitle.save_subtitles
    def save_then_expire(*args, **kwargs):
        result = original_save(*args, **kwargs)
        monkeypatch.setattr(runtime.time, 'time', lambda: 1001)
        return result
    monkeypatch.setattr(subtitle, 'save_subtitles', save_then_expire)
    invoke(['render', p.path, '--format', 'srt', '-o', str(tmp_path / 'out'), '--memory', str(memory.path)], 1)
    assert not (tmp_path / 'out.srt').exists()


def test_publish_files_rolls_back_on_late_collision(tmp_path, monkeypatch):
    import subtitler.safe_io as safe
    a, b, x, y = [tmp_path / n for n in ['a', 'b', 'x', 'y']]
    a.write_bytes(b'a'); b.write_bytes(b'b')
    original = safe.publish_file
    def collide(source, destination):
        if destination == y:
            y.write_bytes(b'other process')
        original(source, destination)
    monkeypatch.setattr(safe, 'publish_file', collide)
    with pytest.raises(FileExistsError):
        safe.publish_files([(a, x), (b, y)])
    assert not x.exists() and y.read_bytes() == b'other process'


def test_untrusted_project_cannot_read_glossary_until_explicitly_approved(tmp_path, capsys):
    kb = tmp_path / 'private.json'
    kb.write_text(json.dumps({'domain': 'private', 'glossary': {'agent': 'PRIVATE_TERM'}}), 'utf-8')
    p = Project(path=str(tmp_path / 'project.json'), domains=['private'], kb_files=[str(kb)],
                segments=[{'id': 1, 'start': 0, 'end': 4, 'text': 'agent', 'translation': ''}])
    p.save()
    invoke(['batch', p.path], 1)
    assert 'PRIVATE_TERM' not in capsys.readouterr().out
    invoke(['batch', p.path, '--kb-file', str(kb)])
    assert 'PRIVATE_TERM' in capsys.readouterr().out


def test_model_null_and_structures_never_turn_into_successful_translations():
    result = to_id_map({'0': None, '1': False, '2': ['text'], '3': {'translation': None},
                        '4': {'text': 'wrong field'}, '5': '正确译文'}, 'translation')
    assert result == {5: '正确译文'}
    assert to_id_map([{'id': True, 'translation': 'bad'}, {'id': 1.5, 'translation': 'bad'},
                      {'id': '7', 'translation': 'good'}], 'translation') == {7: 'good'}
    with pytest.raises(ValueError, match='duplicate'):
        to_id_map([{'id': 1, 'translation': 'A'}, {'id': 1, 'translation': 'B'}], 'translation')


@pytest.mark.parametrize('size,context', [(0, 2), (-1, 2), (2, -1)])
def test_bad_batch_settings_never_silently_skip_work(size, context):
    with pytest.raises(ValueError):
        list(windows(10, size, context))


def test_webvtt_preserves_literal_code_as_text(tmp_path):
    path = tmp_path / 'code.vtt'
    save_to_vtt([SubtitleSegment(0, 4, 'Use <Agent> & <b>literal</b>.')], str(path), max_chars=100)
    payload = path.read_text('utf-8')
    assert '&lt;Agent&gt; &amp; &lt;b&gt;literal&lt;/b&gt;' in payload
    assert '<b>' not in payload


def test_truncated_evidence_rejected_and_unicode_url_encoded(monkeypatch):
    from test_evolution_sources import Response, fake_connection
    response = Response(b'agent')
    response.length = 100  # read1 EOF before advertised Content-Length is exhausted
    captured = fake_connection(monkeypatch, response)
    with pytest.raises(ValueError, match='incomplete'):
        sources.fetch_public('https://example.org/术语', ['example.org'])
    assert captured['closed'] and captured['path'] == '/%E6%9C%AF%E8%AF%AD'


def test_change_preview_is_read_only_source_backed_and_safe_html(learned, tmp_path):
    from subtitler.evolution.preview import preview
    memory, p = learned
    p.segments[0]['translation'] = '代理会学习。<script>alert(1)</script>'
    p.save()
    original = Path(p.path).read_bytes()
    report = preview(p, memory.path, tmp_path / 'preview')
    assert report['changed_segments'] == 1 and report['pending_translations'] == 1
    assert report['segments'][0]['evidence'][0]['quote']
    assert Path(p.path).read_bytes() == original
    assert p.segments[0]['translation'].startswith('代理')
    body = (tmp_path / 'preview' / 'index.html').read_text('utf-8')
    assert '<script>' not in body and '&lt;script&gt;' in body
    assert '智能体会学习。' in body
    with pytest.raises(FileExistsError):
        preview(p, memory.path, tmp_path / 'preview')


def test_preview_reports_unresolved_sentence_without_hiding_other_changes(learned, tmp_path):
    memory, p = learned
    p.segments[0]['translation'] = '他会学习。'
    p.segments[1]['translation'] = '代理会帮忙。'
    p.save()
    invoke(['evolve', 'preview', p.path, '--memory', str(memory.path), '--output', str(tmp_path / 'preview')], 1)
    report = json.loads((tmp_path / 'preview' / 'preview.json').read_text('utf-8'))
    assert report['blocked_segments'] == report['changed_segments'] == 1
    assert report['segments'][0]['after'] is None and report['segments'][0]['error']
    assert report['segments'][1]['after']['translation'] == '智能体会帮忙。'


@pytest.mark.parametrize('url', ['http://api.example.org/v1', 'https://user:secret@example.org/v1',
                                'https://example.org/v1?token=secret'])
def test_llm_rejects_unsafe_endpoint_before_sending_data(url, monkeypatch):
    from subtitler.plugins.llm import LLMClient
    import urllib.request
    monkeypatch.setattr(urllib.request, 'build_opener', lambda *a: pytest.fail('must not open network'))
    with pytest.raises(ValueError, match='HTTPS'):
        LLMClient(api_key='fake-test-key', base_url=url).chat('system', 'private transcript')


def test_llm_redirect_does_not_forward_credentials_or_echo_response_body(monkeypatch):
    import urllib.error
    import urllib.request
    from subtitler.plugins.llm import LLMClient, NoCredentialRedirect
    request = urllib.request.Request('https://example.org/v1/chat/completions', headers={'Authorization': 'Bearer fake-key'})
    with pytest.raises(urllib.error.HTTPError):
        NoCredentialRedirect().redirect_request(request, io.BytesIO(), 307, 'redirect', {}, 'https://other.org/')
    class Opener:
        def open(self, req, **kwargs):
            raise urllib.error.HTTPError(req.full_url, 302, 'redirect', {}, io.BytesIO(b'fake-key private transcript'))
    monkeypatch.setattr(urllib.request, 'build_opener', lambda *a: Opener())
    with pytest.raises(RuntimeError, match='redirects are disabled') as error:
        LLMClient(api_key='fake-key').chat('system', 'private transcript')
    assert 'fake-key' not in str(error.value) and 'private transcript' not in str(error.value)


def test_local_server_detection_uses_hostname_not_substring(monkeypatch):
    from subtitler.plugins.llm import LLMClient
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    monkeypatch.delenv('SUBTITLER_LLM_API_KEY', raising=False)
    assert LLMClient(base_url='http://127.0.0.1:8080/v1').available
    assert LLMClient(base_url='http://[::1]:8080/v1').available
    assert not LLMClient(base_url='https://localhost.example.org/v1').available
    assert not LLMClient(base_url='https://example.org/127.0.0.1').available


def test_batch_output_cannot_overwrite_project(learned):
    memory, p = learned
    p.save()
    original = Path(p.path).read_bytes()
    invoke(['batch', p.path, '--memory', str(memory.path), '--out', p.path], 1)
    assert Path(p.path).read_bytes() == original
