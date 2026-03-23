from __future__ import annotations

import json
import mimetypes
import hashlib
import hmac
import os
from html import escape as html_escape
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from typing import Callable
from urllib.parse import parse_qs, parse_qsl, unquote, urlparse


OrderProvider = Callable[[str], dict[str, object] | None]


def _mini_app_template_path() -> Path:
    return Path(__file__).resolve().parent.parent / "miniapp" / "index.html"


def _mini_app_root_path() -> Path:
    return Path(__file__).resolve().parent.parent / "miniapp"


def build_mini_app_html(title: str, asset_version: str = "") -> str:
    template = _mini_app_template_path().read_text(encoding="utf-8")
    version_suffix = f"?v={asset_version}" if asset_version else ""
    html = template.replace("__CULT_MINI_APP_TITLE__", html_escape(title, quote=True))
    html = html.replace('href="./styles.css"', f'href="./styles.css{version_suffix}"')
    html = html.replace('src="./app.js"', f'src="./app.js{version_suffix}"')
    return html


def _extract_viewer_context(query: str) -> dict[str, str]:
    query_params = parse_qs(query, keep_blank_values=False)

    def first_value(*keys: str) -> str:
        for key in keys:
            values = query_params.get(key)
            if values:
                value = values[0].strip()
                if value:
                    return value
        return ""

    return {
        "platform": first_value("viewer_platform", "platform"),
        "chat_id": first_value("viewer_chat_id", "chat_id", "viewer_id", "user_id"),
        "telegram_init_data": first_value("tg_init_data", "telegram_init_data", "init_data"),
    }


def _extract_telegram_chat_id(telegram_init_data: str) -> str | None:
    telegram_token = (os.getenv("TOKEN") or "").strip()
    raw_init_data = str(telegram_init_data or "").strip()
    if not telegram_token or not raw_init_data:
        return None

    pairs = parse_qsl(raw_init_data, keep_blank_values=True)
    if not pairs:
        return None

    payload = {key: value for key, value in pairs}
    provided_hash = str(payload.pop("hash", "")).strip().lower()
    if not provided_hash:
        return None

    check_string = "\n".join(f"{key}={value}" for key, value in sorted(payload.items()))
    secret = hmac.new(b"WebAppData", telegram_token.encode("utf-8"), hashlib.sha256).digest()
    expected_hash = hmac.new(secret, check_string.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(provided_hash, expected_hash):
        return None

    try:
        user_payload = json.loads(payload.get("user", "{}"))
    except (TypeError, json.JSONDecodeError):
        return None
    if not isinstance(user_payload, dict):
        return None

    user_id = user_payload.get("id")
    if user_id is None:
        return None
    return str(user_id).strip() or None


def _is_order_access_allowed(token: str, viewer: dict[str, str]) -> bool:
    platform = str(viewer.get("platform") or "").strip().lower()
    chat_id = str(viewer.get("chat_id") or "").strip()
    if not platform:
        return False

    if platform == "telegram":
        verified_chat_id = _extract_telegram_chat_id(viewer.get("telegram_init_data", ""))
        if not verified_chat_id:
            return False
        if chat_id and chat_id != verified_chat_id:
            return False
        chat_id = verified_chat_id
    if not chat_id:
        return False

    try:
        from . import legacy
    except Exception:
        return False

    order = legacy.find_order_by_token(token)
    if order is None:
        return False
    if str(order.get("lifecycle_state") or "").strip().lower() == "deleted":
        return False
    return legacy.find_binding(order, platform, chat_id) is not None


class MiniAppServer:
    def __init__(
        self,
        host: str,
        port: int,
        title: str,
        *,
        asset_version: str = "",
        order_provider: OrderProvider | None = None,
        logger: Callable[[str], None] | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.title = title
        self.asset_version = asset_version
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
        asset_version = self.asset_version
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
                    content = build_mini_app_html(title, asset_version).encode("utf-8")
                    self._write_response(
                        HTTPStatus.OK,
                        content,
                        content_type="text/html; charset=utf-8",
                    )
                    return

                if path in {"/health", "/api/health"}:
                    self._write_json(HTTPStatus.OK, {"ok": True}, cors=path.startswith("/api/"))
                    return

                if (
                    path in {"/styles.css", "/app.js", "/header_logo.svg"}
                    or path.startswith("/mockups/")
                    or path.startswith("/fonts/")
                    or path.startswith("/vendor/")
                ):
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

                    viewer = _extract_viewer_context(parsed.query)
                    if not _is_order_access_allowed(token, viewer):
                        self._write_json(
                            HTTPStatus.NOT_FOUND,
                            {"ok": False, "error": "order not found"},
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
