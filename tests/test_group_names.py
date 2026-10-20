from types import SimpleNamespace
from app.group_names import capture_name, clean_name, read_names


def test_capture_persists_name_without_changing_manual_config(tmp_path, monkeypatch):
    monkeypatch.setenv('MONITOR_CONFIG_PATH', str(tmp_path/'settings.json'))
    page = SimpleNamespace(url='https://www.facebook.com/groups/123/', evaluate=lambda script: [None, '二手交易社團', 'Facebook'])
    assert capture_name(page, 'https://www.facebook.com/groups/123/') == '二手交易社團'
    assert read_names() == {'123': '二手交易社團'}
    assert not (tmp_path/'settings.json').exists()
    page.evaluate = lambda script: ['新社團名稱 | Facebook']
    capture_name(page, 'https://www.facebook.com/groups/123')
    assert read_names()['123'] == '新社團名稱'


def test_generic_or_unavailable_page_does_not_replace_cached_name(tmp_path, monkeypatch):
    monkeypatch.setenv('MONITOR_CONFIG_PATH', str(tmp_path/'settings.json'))
    page = SimpleNamespace(url='https://www.facebook.com/groups/123/', evaluate=lambda script: ['交易社團'])
    capture_name(page, 'https://www.facebook.com/groups/123')
    page.evaluate = lambda script: ['Facebook', None, '此內容目前無法顯示']
    assert capture_name(page, 'https://www.facebook.com/groups/123') is None
    assert read_names()['123'] == '交易社團'
    assert clean_name('(3) 交易社團 | Facebook') == '交易社團'


def test_capture_failure_does_not_interrupt_scan(tmp_path, monkeypatch):
    monkeypatch.setenv('MONITOR_CONFIG_PATH', str(tmp_path/'settings.json'))
    def fail(script):
        raise RuntimeError('page closed')
    assert capture_name(SimpleNamespace(url='https://www.facebook.com/groups/123/', evaluate=fail), 'https://www.facebook.com/groups/123') is None


def test_notification_heading_never_becomes_group_name(tmp_path, monkeypatch):
    monkeypatch.setenv('MONITOR_CONFIG_PATH', str(tmp_path/'settings.json'))
    page = SimpleNamespace(url='https://www.facebook.com/groups/123/',
                           evaluate=lambda script: [None, '通知', '二手iphone手機 自售交易區 | Facebook'])
    assert capture_name(page, page.url) == '二手iphone手機 自售交易區'
    page.evaluate = lambda script: [None, '通知', 'Facebook']
    assert capture_name(page, page.url) is None
    assert read_names()['123'] == '二手iphone手機 自售交易區'


def test_bad_existing_names_hidden_and_redirect_not_cached(tmp_path, monkeypatch):
    from app.group_names import names_path
    monkeypatch.setenv('MONITOR_CONFIG_PATH', str(tmp_path/'settings.json'))
    names_path().write_text('{"123": "通知", "456": "正常社團"}')
    assert read_names() == {'456': '正常社團'}
    page = SimpleNamespace(url='https://www.facebook.com/groups/999/', evaluate=lambda script: ['其他社團'])
    assert capture_name(page, 'https://www.facebook.com/groups/123/') is None
    assert '123' not in read_names()
