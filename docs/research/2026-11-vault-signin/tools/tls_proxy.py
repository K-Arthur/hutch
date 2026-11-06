"""Minimal TLS-terminating reverse proxy following Hutch's trusted-proxy contract.

usage: tls_proxy.py LISTEN_PORT UPSTREAM_PORT PUBLIC_HOST CERT KEY
Sends exactly one X-Forwarded-Host, X-Forwarded-Proto and X-Forwarded-For, keeps every upstream
Set-Cookie, and does no buffering tricks. Test harness only.
"""
import http.client
import ssl
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

LISTEN, UPSTREAM, PUBLIC, CERT, KEY = int(sys.argv[1]), int(sys.argv[2]), sys.argv[3], sys.argv[4], sys.argv[5]
HOP = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailers",
       "transfer-encoding", "upgrade", "host", "content-length"}


class Proxy(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def handle_any(self):
        length = int(self.headers.get("content-length") or 0)
        body = self.rfile.read(length) if length else None
        headers = {k: v for k, v in self.headers.items() if k.lower() not in HOP}
        headers.update({"Host": f"{PUBLIC}:{LISTEN}", "X-Forwarded-Host": f"{PUBLIC}:{LISTEN}",
                        "X-Forwarded-Proto": "https", "X-Forwarded-For": self.client_address[0]})
        conn = http.client.HTTPConnection("127.0.0.1", UPSTREAM, timeout=60)
        conn.request(self.command, self.path, body=body, headers=headers)
        resp = conn.getresponse()
        data = resp.read()
        self.send_response(resp.status)
        for key, value in resp.getheaders():
            if key.lower() not in HOP:
                self.send_header(key, value)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)
        conn.close()

    do_GET = do_POST = do_PUT = do_DELETE = do_PATCH = handle_any

    def log_message(self, *args):
        pass


server = ThreadingHTTPServer(("127.0.0.1", LISTEN), Proxy)
context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
context.load_cert_chain(CERT, KEY)
server.socket = context.wrap_socket(server.socket, server_side=True)
server.serve_forever()
