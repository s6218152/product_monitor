"""Loopback-only settings server; no third-party dependencies."""
from http.server import BaseHTTPRequestHandler, HTTPServer
import argparse
import json
from pathlib import Path
from app.config import load_settings
from app.monitor_config import read_config, save_config


class Handler(BaseHTTPRequestHandler):
    def respond(self, status, value, content_type='application/json; charset=utf-8'):
        body = value if isinstance(value, bytes) else json.dumps(value, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == '/':
            return self.respond(200, Path(__file__).with_name('index.html').read_bytes(), 'text/html; charset=utf-8')
        if self.path == '/api/status':
            from app.monitor_status import read_status
            return self.respond(200, read_status())
        if self.path == '/api/settings':
            try:
                settings = load_settings()
                value = read_config() or {'groups': [{'name': '', 'url': url} for url in settings.facebook_group_urls], 'products': []}
                from app.group_names import read_names, group_key
                names = read_names()
                value = {**value, 'groups': [{**group, 'auto_name': names.get(group_key(group['url']), '')} for group in value['groups']]}
                return self.respond(200, value)
            except (OSError, ValueError) as error:
                return self.respond(500, {'error': str(error)})
        self.respond(404, {'error': '找不到頁面'})

    def do_POST(self):
        if self.path != '/api/settings':
            return self.respond(404, {'error': '找不到頁面'})
        # JSON-only and same-origin requests prevent cross-site form submissions.
        origin = self.headers.get('Origin')
        if origin and origin != f'http://127.0.0.1:{self.server.server_port}' and origin != f'http://localhost:{self.server.server_port}':
            return self.respond(403, {'error': '不允許跨網站儲存設定'})
        if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
            return self.respond(415, {'error': '需要 JSON 格式'})
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 65536:
                raise ValueError('設定大小不正確')
            value = save_config(json.loads(self.rfile.read(length)))
            self.respond(200, value)
        except (ValueError, TypeError) as error:
            self.respond(400, {'error': str(error)})
        except OSError:
            self.respond(500, {'error': '無法儲存設定，請檢查檔案權限'})


def main():
    parser = argparse.ArgumentParser(description='Facebook monitor settings UI')
    parser.add_argument('--port', type=int, default=8080)
    args = parser.parse_args()
    server = HTTPServer(('127.0.0.1', args.port), Handler)
    print(f'設定頁面：http://127.0.0.1:{args.port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
