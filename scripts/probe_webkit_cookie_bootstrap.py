"""Probe real Strict-cookie startup semantics with system PyGObject/WebKitGTK.

Run under DBus/Xvfb with the OS Python that provides gi. Uses a new ephemeral
WebKit context and a synthetic cookie, never a personal profile or Hutch token.
"""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading

import gi

gi.require_version('Gtk', '3.0')
gi.require_version('WebKit2', '4.1')
gi.require_version('Soup', '3.0')
from gi.repository import GLib, Gtk, Soup, WebKit2  # noqa: E402


def main():
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_GET(self):
            requests.append({'path': self.path,
                             'probe_cookie_received': 'hutch_probe=' in (self.headers.get('Cookie') or '')})
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.end_headers()
            self.wfile.write(b'<p>Local synthetic cookie probe</p>')

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    target = f'http://127.0.0.1:{server.server_port}/'
    context = WebKit2.WebContext.new_ephemeral()
    view = WebKit2.WebView.new_with_context(context)
    window = Gtk.Window(title='Synthetic Strict-cookie probe')
    window.add(view)
    window.show_all()
    manager = context.get_cookie_manager()
    loop = GLib.MainLoop()
    phase = 0
    result = {'contract_version': 1, 'scope': 'native cookie semantics; not installed Hutch GUI acceptance',
              'webkit': f'{WebKit2.get_major_version()}.{WebKit2.get_minor_version()}.{WebKit2.get_micro_version()}'}

    def complete(manager, response):
        cookies = manager.get_all_cookies_finish(response)
        result['cookie_attributes'] = [{'name': cookie.get_name(), 'http_only': cookie.get_http_only(),
                                        'strict': cookie.get_same_site_policy() == Soup.SameSitePolicy.STRICT}
                                       for cookie in cookies]
        result['requests'] = requests
        result['passed'] = (result.get('native_add_success') is True
                            and result.get('cookies_before_navigation') == 1
                            and [row['probe_cookie_received'] for row in requests] == [False, True]
                            and len(cookies) == 1 and cookies[0].get_http_only()
                            and cookies[0].get_same_site_policy() == Soup.SameSitePolicy.STRICT)
        loop.quit()

    def queried(manager, response):
        result['cookies_before_navigation'] = len(manager.get_cookies_finish(response))
        view.load_uri(target)

    def added(manager, response):
        result['native_add_success'] = manager.add_cookie_finish(response)
        manager.get_cookies(target, None, queried)

    def loaded(view, event):
        nonlocal phase
        if event != WebKit2.LoadEvent.FINISHED:
            return
        if phase == 0:
            phase = 1
            cookie = Soup.Cookie.new('hutch_probe', 'synthetic-only', '127.0.0.1', '/', -1)
            cookie.set_http_only(True)
            cookie.set_same_site_policy(Soup.SameSitePolicy.STRICT)
            manager.add_cookie(cookie, None, added)
        elif phase == 1:
            phase = 2
            view.load_uri(target)
        else:
            manager.get_all_cookies(None, complete)

    def timeout():
        result.update(passed=False, timeout=True)
        loop.quit()
        return False

    timer = GLib.timeout_add_seconds(10, timeout)
    view.connect('load-changed', loaded)
    view.load_html('<p>Trusted startup</p>', 'tauri://localhost/')
    try:
        loop.run()
    finally:
        if not result.get('timeout'):
            GLib.source_remove(timer)
        window.destroy()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get('passed') else 1


if __name__ == '__main__':
    raise SystemExit(main())
