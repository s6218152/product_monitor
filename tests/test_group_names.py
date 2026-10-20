from types import SimpleNamespace
from app.group_names import capture_name, clean_name, read_names


def test_capture_persists_name_without_changing_manual_config(tmp_path, monkeypatch):
    monkeypatch.setenv('MONITOR_CONFIG_PATH', str(tmp_path/'settings.json'))
    page = SimpleNamespace(evaluate=lambda script: [None, '二手交易社團', 'Facebook'])
    assert capture_name(page, 'https://www.facebook.com/groups/123/') == '二手交易社團'
    assert read_names() == {'123': '二手交易社團'}
    assert not (tmp_path/'settings.json').exists()
    page.evaluate = lambda script: ['新社團名稱 | Facebook']
    capture_name(page, 'https://www.facebook.com/groups/123')
    assert read_names()['123'] == '新社團名稱'


def test_generic_or_unavailable_page_does_not_replace_cached_name(tmp_path, monkeypatch):
    monkeypatch.setenv('MONITOR_CONFIG_PATH', str(tmp_path/'settings.json'))
    page = SimpleNamespace(evaluate=lambda script: ['交易社團'])
    capture_name(page, 'https://www.facebook.com/groups/123')
    page.evaluate = lambda script: ['Facebook', None, '此內容目前無法顯示']
    assert capture_name(page, 'https://www.facebook.com/groups/123') is None
    assert read_names()['123'] == '交易社團'
    assert clean_name('(3) 交易社團 | Facebook') == '交易社團'


def test_capture_failure_does_not_interrupt_scan(tmp_path, monkeypatch):
    monkeypatch.setenv('MONITOR_CONFIG_PATH', str(tmp_path/'settings.json'))
    def fail(script):
        raise RuntimeError('page closed')
    assert capture_name(SimpleNamespace(evaluate=fail), 'https://www.facebook.com/groups/123') is None
