#!/usr/bin/env python3
"""Serve the dashboard locally: python3 serve.py [--port 8000]

The page fetches data/snapshot.json, which browsers block over file://,
so it needs a real server - this is that server, stdlib only.
"""

from __future__ import annotations

import argparse
import functools
import http.server
import os
import socketserver

ROOT = os.path.dirname(os.path.abspath(__file__))


class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 - stdlib naming
        # Redirect rather than rewrite: the page's relative links to
        # styles.css and ../data/snapshot.json need /web/ as their base.
        if self.path in ("/", "/index.html"):
            self.send_response(302)
            self.send_header("Location", "/web/")
            self.end_headers()
            return None
        return super().do_GET()

    def end_headers(self):
        # The snapshot changes under the page; never let a browser pin an old one.
        if self.path.endswith(".json"):
            self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, fmt, *args):
        if not self.path.endswith((".css", ".js", ".svg")):
            super().log_message(fmt, *args)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()

    handler = functools.partial(Handler, directory=ROOT)
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer((args.host, args.port), handler) as httpd:
        print(f"dashboard: http://{args.host}:{args.port}/")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nstopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
