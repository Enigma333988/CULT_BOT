from __future__ import annotations

import json
import mimetypes
from html import escape as html_escape
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from typing import Callable
from urllib.parse import parse_qs, unquote, urlparse


OrderProvider = Callable[[str], dict[str, object] | None]


def _mini_app_template_path() -> Path:
    return Path(__file__).resolve().parent.parent / "miniapp" / "index.html"


def _mini_app_root_path() -> Path:
    return Path(__file__).resolve().parent.parent / "miniapp"


def build_mini_app_html(title: str) -> str:
    template = _mini_app_template_path().read_text(encoding="utf-8")
    return template.replace("__CULT_MINI_APP_TITLE__", html_escape(title, quote=True))


class MiniAppServer:
    def __init__(
        self,
        host: str,
        port: int,
        title: str,
        *,
        order_provider: OrderProvider | None = None,
        logger: Callable[[str], None] | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.title = title
        self.order_provider = order_provider
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
        order_provider = self.order_provider
        mini_app_root = _mini_app_root_path().resolve()

        class Handler(BaseHTTPRequestHandler):
            def _write_response(
                self,
                status: HTTPStatus,
                body: bytes,
                *,
                content_type: str,
                cors: bool = False,
            ) -> None:
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                if cors:
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
                    self.send_header("Access-Control-Allow-Headers", "Content-Type")
                self.end_headers()
                self.wfile.write(body)

            def _write_json(
                self,
                status: HTTPStatus,
                payload: dict[str, object],
                *,
                cors: bool = False,
            ) -> None:
                body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self._write_response(status, body, content_type="application/json; charset=utf-8", cors=cors)

            def do_OPTIONS(self) -> None:  # noqa: N802
                self.send_response(HTTPStatus.NO_CONTENT)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type")
                self.send_header("Content-Length", "0")
                self.end_headers()

            def do_GET(self) -> None:  # noqa: N802
                parsed = urlparse(self.path)
                path = parsed.path or "/"

                if path in {"/", "/index.html"}:
                    content = build_mini_app_html(title).encode("utf-8")
                    self._write_response(
                        HTTPStatus.OK,
                        content,
                        content_type="text/html; charset=utf-8",
                    )
                    return

                if path in {"/health", "/api/health"}:
                    self._write_json(HTTPStatus.OK, {"ok": True}, cors=path.startswith("/api/"))
                    return

                if path in {"/styles.css", "/app.js"} or path.startswith("/mockups/"):
                    asset_path = self._resolve_static_asset(path, mini_app_root)
                    if asset_path is None or not asset_path.is_file():
                        self.send_error(HTTPStatus.NOT_FOUND, "Not Found")
                        return

                    content = asset_path.read_bytes()
                    content_type, _ = mimetypes.guess_type(asset_path.name)
                    self._write_response(
                        HTTPStatus.OK,
                        content,
                        content_type=content_type or "application/octet-stream",
                    )
                    return

                if path.startswith("/api/order"):
                    token = self._extract_order_token(path, parsed.query)
                    if not token:
                        self._write_json(
                            HTTPStatus.BAD_REQUEST,
                            {"ok": False, "error": "order token is required"},
                            cors=True,
                        )
                        return

                    if order_provider is None:
                        self._write_json(
                            HTTPStatus.NOT_IMPLEMENTED,
                            {"ok": False, "error": "order provider is not configured"},
                            cors=True,
                        )
                        return

                    payload = order_provider(token)
                    if payload is None:
                        self._write_json(
                            HTTPStatus.NOT_FOUND,
                            {"ok": False, "error": "order not found"},
                            cors=True,
                        )
                        return

                    self._write_json(HTTPStatus.OK, {"ok": True, "order": payload}, cors=True)
                    return

                self.send_error(HTTPStatus.NOT_FOUND, "Not Found")

            @staticmethod
            def _extract_order_token(path: str, query: str) -> str:
                suffix = path.removeprefix("/api/order").strip("/")
                if suffix:
                    return unquote(suffix)

                query_params = parse_qs(query, keep_blank_values=False)
                for key in ("token", "orderToken", "order_token"):
                    values = query_params.get(key)
                    if values:
                        value = values[0].strip()
                        if value:
                            return value
                return ""

            @staticmethod
            def _resolve_static_asset(request_path: str, root: Path) -> Path | None:
                relative_path = request_path.lstrip("/")
                candidate = (root / relative_path).resolve()
                try:
                    candidate.relative_to(root)
                except ValueError:
                    return None
                return candidate

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
