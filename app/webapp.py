from __future__ import annotations

from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from typing import Callable


def build_mini_app_html(title: str) -> str:
    return f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <script src="https://telegram.org/js/telegram-web-app.js"></script>
  <script src="https://st.max.ru/js/max-web-app.js"></script>
  <style>
    html, body {{
      margin: 0;
      width: 100%;
      min-height: 100%;
      background: #ffffff;
    }}
  </style>
</head>
<body>
  <script>
    const tg = window.Telegram && window.Telegram.WebApp ? window.Telegram.WebApp : null;
    const maxApp = window.WebApp || null;

    if (tg) {{
      try {{
        tg.ready();
        tg.expand();
      }} catch (error) {{
        console.error("Telegram bridge init failed", error);
      }}
    }}

    if (maxApp && typeof maxApp.ready === "function") {{
      try {{
        maxApp.ready();
      }} catch (error) {{
        console.error("MAX bridge init failed", error);
      }}
    }}
  </script>
</body>
</html>
"""


class MiniAppServer:
    def __init__(
        self,
        host: str,
        port: int,
        title: str,
        *,
        logger: Callable[[str], None] | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.title = title
        self.logger = logger
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: Thread | None = None

    @property
    def local_url(self) -> str:
        return f"http://{self.host}:{self.port}/"

    def start(self) -> str:
        if self._httpd is not None:
            return self.local_url

        title = self.title
        logger = self.logger

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                if self.path in {"/", "/index.html"}:
                    content = build_mini_app_html(title).encode("utf-8")
                    self.send_response(HTTPStatus.OK)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(content)))
                    self.end_headers()
                    self.wfile.write(content)
                    return

                if self.path == "/health":
                    content = b'{"ok":true}'
                    self.send_response(HTTPStatus.OK)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Content-Length", str(len(content)))
                    self.end_headers()
                    self.wfile.write(content)
                    return

                self.send_error(HTTPStatus.NOT_FOUND, "Not Found")

            def log_message(self, format: str, *args: object) -> None:
                if logger is not None:
                    logger("Mini App HTTP: " + format % args)

        self._httpd = ThreadingHTTPServer((self.host, self.port), Handler)
        self._thread = Thread(target=self._httpd.serve_forever, name="mini-app-http", daemon=True)
        self._thread.start()
        return self.local_url

    def stop(self) -> None:
        if self._httpd is None:
            return

        self._httpd.shutdown()
        self._httpd.server_close()
        if self._thread is not None:
            self._thread.join(timeout=1)
        self._httpd = None
        self._thread = None
