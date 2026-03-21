from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from typing import Callable


def build_mini_app_html(title: str) -> str:
    safe_title = json.dumps(title)
    return f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <script src="https://telegram.org/js/telegram-web-app.js"></script>
  <script src="https://st.max.ru/js/max-web-app.js"></script>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f4efe7;
      --card: rgba(255, 252, 247, 0.9);
      --text: #1b1713;
      --muted: #6e6256;
      --accent: #a44a2f;
      --border: rgba(27, 23, 19, 0.08);
      --shadow: 0 20px 60px rgba(66, 40, 23, 0.16);
      --ok-bg: rgba(78, 111, 92, 0.12);
      --ok-text: #31513f;
      --warn-bg: rgba(164, 74, 47, 0.12);
      --warn-text: #8e442d;
    }}

    * {{
      box-sizing: border-box;
    }}

    body {{
      margin: 0;
      min-height: 100vh;
      font-family: "Segoe UI", sans-serif;
      color: var(--text);
      background:
        radial-gradient(circle at top left, rgba(164, 74, 47, 0.16), transparent 32%),
        radial-gradient(circle at bottom right, rgba(78, 111, 92, 0.18), transparent 28%),
        linear-gradient(180deg, #f8f4ed 0%, var(--bg) 100%);
      display: grid;
      place-items: center;
      padding: 24px;
    }}

    .card {{
      width: min(100%, 680px);
      padding: 28px;
      border-radius: 28px;
      background: var(--card);
      border: 1px solid var(--border);
      box-shadow: var(--shadow);
      backdrop-filter: blur(18px);
    }}

    .eyebrow {{
      margin: 0 0 12px;
      font-size: 12px;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      color: var(--accent);
    }}

    h1 {{
      margin: 0;
      font-size: clamp(28px, 7vw, 44px);
      line-height: 0.95;
    }}

    p {{
      margin: 16px 0 0;
      font-size: 16px;
      line-height: 1.55;
      color: var(--muted);
    }}

    .chips {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-top: 18px;
    }}

    .chip {{
      border-radius: 999px;
      padding: 8px 12px;
      font-size: 13px;
      font-weight: 600;
    }}

    .chip.ok {{
      background: var(--ok-bg);
      color: var(--ok-text);
    }}

    .chip.warn {{
      background: var(--warn-bg);
      color: var(--warn-text);
    }}

    .meta {{
      margin-top: 22px;
      display: grid;
      gap: 10px;
    }}

    .meta-item {{
      padding: 14px 16px;
      border-radius: 16px;
      background: rgba(255, 255, 255, 0.58);
      border: 1px solid rgba(27, 23, 19, 0.06);
    }}

    .meta-label {{
      display: block;
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: var(--muted);
      margin-bottom: 4px;
    }}

    .meta-value {{
      font-size: 15px;
      color: var(--text);
      word-break: break-word;
    }}

    pre {{
      margin: 0;
      white-space: pre-wrap;
      word-break: break-word;
      font-family: Consolas, monospace;
      font-size: 13px;
      color: #43372e;
    }}
  </style>
</head>
<body>
  <main class="card">
    <p class="eyebrow">Multi Platform Mini App</p>
    <h1>Платформенная основа подключена</h1>
    <p>
      Один и тот же Mini App теперь определяет, где он запущен: в браузере, Telegram или MAX.
      Это база для дальнейшего добавления заказов, каталога и авторизации без разделения на разные сайты.
    </p>

    <section class="chips">
      <span class="chip warn" id="version-chip">Build: 2026-03-22-01</span>
      <span class="chip ok" id="env-chip">Environment: loading</span>
      <span class="chip ok" id="telegram-chip">Telegram bridge: pending</span>
      <span class="chip ok" id="max-chip">MAX bridge: pending</span>
    </section>

    <section class="meta">
      <div class="meta-item">
        <span class="meta-label">Название</span>
        <span class="meta-value" id="app-title"></span>
      </div>
      <div class="meta-item">
        <span class="meta-label">Активная платформа</span>
        <span class="meta-value" id="platform">browser</span>
      </div>
      <div class="meta-item">
        <span class="meta-label">Версия Telegram WebApp</span>
        <span class="meta-value" id="telegram-version">not detected</span>
      </div>
      <div class="meta-item">
        <span class="meta-label">Диагностика</span>
        <pre id="debug">{{}}</pre>
      </div>
    </section>
  </main>
  <script>
    const appTitle = {safe_title};
    document.getElementById("app-title").textContent = appTitle;
    const state = {{
      environment: "browser",
      telegram: {{
        detected: false,
        version: null,
        platform: null
      }},
      max: {{
        detected: false,
        available: false
      }}
    }};

    const ui = {{
      platform: document.getElementById("platform"),
      telegramVersion: document.getElementById("telegram-version"),
      debug: document.getElementById("debug"),
      envChip: document.getElementById("env-chip"),
      telegramChip: document.getElementById("telegram-chip"),
      maxChip: document.getElementById("max-chip")
    }};

    function setChip(element, label, ok) {{
      element.textContent = label;
      element.className = "chip " + (ok ? "ok" : "warn");
    }}

    function detectEnvironment() {{
      const tg = window.Telegram && window.Telegram.WebApp ? window.Telegram.WebApp : null;
      const maxApp = window.WebApp || null;

      if (tg) {{
        state.environment = "telegram";
        state.telegram.detected = true;
        state.telegram.version = tg.version || null;
        state.telegram.platform = tg.platform || null;

        try {{
          tg.ready();
          tg.expand();
        }} catch (error) {{
          console.error("Telegram bridge init failed", error);
        }}
      }}

      if (maxApp) {{
        state.max.detected = true;
        state.max.available = true;
        if (state.environment === "browser") {{
          state.environment = "max";
        }}

        if (typeof maxApp.ready === "function") {{
          try {{
            maxApp.ready();
          }} catch (error) {{
            console.error("MAX bridge init failed", error);
          }}
        }}
      }}
    }}

    function render() {{
      ui.platform.textContent = state.environment;
      ui.telegramVersion.textContent = state.telegram.version || "not detected";

      setChip(ui.envChip, "Environment: " + state.environment, true);
      setChip(
        ui.telegramChip,
        "Telegram bridge: " + (state.telegram.detected ? "ready" : "not detected"),
        state.telegram.detected
      );
      setChip(
        ui.maxChip,
        "MAX bridge: " + (state.max.detected ? "ready" : "not detected"),
        state.max.detected
      );

      ui.debug.textContent = JSON.stringify(state, null, 2);
    }}

    detectEnvironment();
    render();
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
