import json
from threading import Thread
from http.server import HTTPServer
from urllib.request import Request, urlopen
from urllib.error import HTTPError
import pytest
from app.monitor_config import save_config, read_config, validate
from app.web.server import Handler
from app.config import load_settings
from app.products.target_filter import rejection_reason


def test_saved_settings_drive_groups_and_matching(tmp_path, monkeypatch):
    monkeypatch.setenv('MONITOR_CONFIG_PATH', str(tmp_path / 'settings.json'))
    save_config({'groups': [{'url': 'https://www.facebook.com/groups/123/?foo=bar'}],
                 'products': [{'keyword': 'Nintendo Switch', 'max_price': 6000}]})
    assert read_config()['groups'][0]['url'] == 'https://www.facebook.com/groups/123/'
    assert load_settings(tmp_path / '.env').facebook_group_urls == ('https://www.facebook.com/groups/123/',)
    assert rejection_reason('Nintendo Switch', 5500, None) is None
    assert rejection_reason('Nintendo Switch', 6001, None) == 'custom_product_or_price'
    assert rejection_reason('Nintendo Switch', None, None) is not None
    assert rejection_reason('Other product', 1000, None) is not None


@pytest.mark.parametrize('url', ['https://evil.com/groups/123', 'https://www.facebook.com.evil.com/groups/123', 'https://www.facebook.com/groups/', 'javascript:alert(1)'])
def test_reject_invalid_group(url):
    with pytest.raises(ValueError):
        validate({'groups': [{'url': url}], 'products': [{'keyword': 'test', 'max_price': 100}]})


def test_http_save_reload_and_cross_origin(tmp_path, monkeypatch):
    monkeypatch.setenv('MONITOR_CONFIG_PATH', str(tmp_path / 'settings.json'))
    server = HTTPServer(('127.0.0.1', 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f'http://127.0.0.1:{server.server_port}'
    payload = json.dumps({'groups': [{'name': 'Test', 'url': 'https://www.facebook.com/groups/123'}], 'products': [{'keyword': '相機', 'max_price': 5000}]}).encode()
    try:
        assert '商品與價格' in urlopen(base).read().decode()
        request = Request(base + '/api/settings', payload, {'Content-Type': 'application/json'})
        with urlopen(request) as response:
            assert response.status == 200
        assert json.load(urlopen(base + '/api/settings'))['products'][0]['keyword'] == '相機'
        request.add_header('Origin', 'https://evil.example')
        with pytest.raises(HTTPError) as error:
            urlopen(request)
        assert error.value.code == 403
        bad = Request(base + '/api/settings', b'{}', {'Content-Type': 'application/json'})
        with pytest.raises(HTTPError) as error:
            urlopen(bad)
        assert error.value.code == 400
        assert read_config()['products'][0]['max_price'] == 5000
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
