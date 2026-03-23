import json
import os
import re
import secrets
import shutil
import threading
import time
from datetime import datetime, timedelta, timezone
from html import escape as html_escape
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from zoneinfo import ZoneInfo

import requests
from dotenv import load_dotenv

from .webapp import MiniAppServer

load_dotenv()


def get_env_value(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    if value is None:
        return default

    cleaned = value.strip()
    return cleaned or default



def resolve_runtime_file(env_name: str, default_filename: str) -> Path:
    raw_value = get_env_value(env_name, default_filename)
    path = Path(raw_value)

    if path.exists() and path.is_dir():
        raise ValueError(
            f"вќЊ {env_name} РґРѕР»Р¶РµРЅ СѓРєР°Р·С‹РІР°С‚СЊ РЅР° JSON-С„Р°Р№Р», Р° РЅРµ РЅР° РїР°РїРєСѓ: {path}"
        )

    if path.name in {"", ".", ".."}:
        raise ValueError(
            f"вќЊ {env_name} РґРѕР»Р¶РµРЅ СѓРєР°Р·С‹РІР°С‚СЊ РЅР° С„Р°Р№Р», РЅР°РїСЂРёРјРµСЂ {default_filename}"
        )

    return path


TELEGRAM_TOKEN = get_env_value("TOKEN")
TELEGRAM_ADMIN_CHAT_ID = get_env_value("ADMIN_CHAT_ID")
MAX_TOKEN = get_env_value("MAX_TOKEN")
MAX_ADMIN_CHAT_ID = get_env_value("MAX_ADMIN_CHAT_ID")
PROXY = get_env_value("PROXY")
TELEGRAM_PROXY = get_env_value("TELEGRAM_PROXY", PROXY)
MAX_PROXY = get_env_value("MAX_PROXY")
TIMEZONE_NAME = get_env_value("TIMEZONE", "UTC")
ORDERS_FILE = resolve_runtime_file("ORDERS_FILE", "orders.json")
STATE_FILE = resolve_runtime_file("STATE_FILE", "bot_state.json")
CATALOG_FILE = resolve_runtime_file("CATALOG_FILE", "catalog.json")
ARCHIVE_DIR = Path(get_env_value("ARCHIVE_DIR", "archive"))
ALLOWED_PROXY_SCHEMES = {"http", "https", "socks5", "socks5h"}
POLL_TIMEOUT_SECONDS = 10
MAX_POLL_TIMEOUT_SECONDS = 30
REQUEST_TIMEOUT_SECONDS = 20
LOOP_INTERVAL_SECONDS = 2
MAX_TITLE_LENGTH = 200
MAX_PRICE_LENGTH = 60
MAX_NOTES_LENGTH = 1000
MENU_LABEL = "РњРµРЅСЋ"
CONTACT_URL = "https://t.me/cultmebel?direct"
VK_URL = "https://vk.com/cultmebel"
TG_URL = "https://t.me/cultmebel"
MINI_APP_TITLE = get_env_value("MINI_APP_TITLE", "CULT Mini App")
MINI_APP_BUTTON_TEXT = get_env_value("MINI_APP_BUTTON_TEXT", "РћС‚РєСЂС‹С‚СЊ РїСЂРёР»РѕР¶РµРЅРёРµ")
MINI_APP_HOST = get_env_value("MINI_APP_HOST", "127.0.0.1")
MINI_APP_PORT_RAW = get_env_value("MINI_APP_PORT", "8080")
MINI_APP_PUBLIC_URL = get_env_value("MINI_APP_PUBLIC_URL")
MINI_APP_CACHE_BUSTER = get_env_value("MINI_APP_CACHE_BUSTER")
TELEGRAM_MENU_BUTTON_MODE = get_env_value("TELEGRAM_MENU_BUTTON_MODE", "web_app").strip().lower()
PAYMENT_OPTIONS = {
    "0": 0,
    "50": 50,
    "100": 100,
}

STATUS_LABELS = {
    "awaiting": "Р’ РѕР¶РёРґР°РЅРёРё",
    "accepted": "РџСЂРёРЅСЏС‚Рѕ РІ СЂР°Р±РѕС‚Сѓ",
    "production": "РР·РіРѕС‚РѕРІР»РµРЅРёРµ",
    "painting": "РџРѕРєСЂР°СЃРєР°",
    "assembly": "РЎР±РѕСЂРєР°",
    "ready": "Р—Р°РєР°Р· РіРѕС‚РѕРІ",
    "awaiting_delivery": "РћР¶РёРґР°РЅРёРµ РґРѕСЃС‚Р°РІРєРё",
    "in_transit": "Р’ РїСѓС‚Рё",
    "completed": "Р—Р°РІРµСЂС€С‘РЅ",
}
BASE_STATUS_KEYS = [
    "awaiting",
    "accepted",
    "production",
    "painting",
    "assembly",
    "ready",
]
DELIVERY_EXTRA_STATUS_KEYS = ["awaiting_delivery", "in_transit"]
RUSSIAN_MONTHS = {
    "СЏРЅРІР°СЂСЏ": 1,
    "С„РµРІСЂР°Р»СЏ": 2,
    "РјР°СЂС‚Р°": 3,
    "Р°РїСЂРµР»СЏ": 4,
    "РјР°СЏ": 5,
    "РёСЋРЅСЏ": 6,
    "РёСЋР»СЏ": 7,
    "Р°РІРіСѓСЃС‚Р°": 8,
    "СЃРµРЅС‚СЏР±СЂСЏ": 9,
    "РѕРєС‚СЏР±СЂСЏ": 10,
    "РЅРѕСЏР±СЂСЏ": 11,
    "РґРµРєР°Р±СЂСЏ": 12,
}
PLATFORM_LABELS = {
    "telegram": "Telegram",
    "max": "MAX",
}
MAX_UPDATE_TYPES = ["message_created", "message_callback", "bot_started"]

if not TELEGRAM_TOKEN and not MAX_TOKEN:
    raise ValueError("вќЊ РЈРєР°Р¶Рё С…РѕС‚СЏ Р±С‹ РѕРґРёРЅ С‚РѕРєРµРЅ: TOKEN РґР»СЏ Telegram РёР»Рё MAX_TOKEN РґР»СЏ MAX.")

if TELEGRAM_TOKEN and not TELEGRAM_ADMIN_CHAT_ID:
    raise ValueError("вќЊ РќРµ РЅР°Р№РґРµРЅ ADMIN_CHAT_ID РІ .env")

if MAX_TOKEN and not MAX_ADMIN_CHAT_ID:
    raise ValueError("вќЊ РќРµ РЅР°Р№РґРµРЅ MAX_ADMIN_CHAT_ID РІ .env")

for proxy_name, proxy_value in (
    ("PROXY", PROXY),
    ("TELEGRAM_PROXY", TELEGRAM_PROXY),
    ("MAX_PROXY", MAX_PROXY),
):
    if not proxy_value:
        continue
    parsed_proxy = urlparse(proxy_value)
    if parsed_proxy.scheme.lower() not in ALLOWED_PROXY_SCHEMES:
        raise ValueError(
            f"вќЊ РќРµРєРѕСЂСЂРµРєС‚РЅР°СЏ СЃС…РµРјР° {proxy_name}. РСЃРїРѕР»СЊР·СѓР№ http://, https://, socks5:// РёР»Рё socks5h://"
        )

try:
    MINI_APP_PORT = int(MINI_APP_PORT_RAW or "8080")
except ValueError as exc:
    raise ValueError("вќЊ MINI_APP_PORT РґРѕР»Р¶РµРЅ Р±С‹С‚СЊ С†РµР»С‹Рј С‡РёСЃР»РѕРј.") from exc

if not 1 <= MINI_APP_PORT <= 65535:
    raise ValueError("вќЊ MINI_APP_PORT РґРѕР»Р¶РµРЅ Р±С‹С‚СЊ РІ РґРёР°РїР°Р·РѕРЅРµ 1..65535.")

if MINI_APP_PUBLIC_URL:
    parsed_mini_app_url = urlparse(MINI_APP_PUBLIC_URL)
    if parsed_mini_app_url.scheme.lower() != "https" or not parsed_mini_app_url.netloc:
        raise ValueError("вќЊ MINI_APP_PUBLIC_URL РґРѕР»Р¶РµРЅ Р±С‹С‚СЊ РєРѕСЂСЂРµРєС‚РЅС‹Рј HTTPS URL.")

if TELEGRAM_MENU_BUTTON_MODE not in {"web_app", "commands"}:
    raise ValueError("вќЊ TELEGRAM_MENU_BUTTON_MODE РґРѕР»Р¶РµРЅ Р±С‹С‚СЊ web_app РёР»Рё commands.")

try:
    LOCAL_TZ = ZoneInfo(TIMEZONE_NAME)
except Exception as exc:
    raise ValueError(
        "вќЊ РќРµРєРѕСЂСЂРµРєС‚РЅР°СЏ TIMEZONE. РСЃРїРѕР»СЊР·СѓР№ IANA-РёРјСЏ, РЅР°РїСЂРёРјРµСЂ Europe/Moscow РёР»Рё UTC"
    ) from exc

thread_local = threading.local()
state_lock = threading.RLock()


def get_http_session(channel: str = "telegram") -> requests.Session:
    if channel not in {"telegram", "max"}:
        raise ValueError(f"Unknown HTTP channel: {channel}")

    session_attr = f"session_{channel}"
    existing_session = getattr(thread_local, session_attr, None)
    if existing_session is not None:
        return existing_session

    created_session = requests.Session()
    created_session.trust_env = False
    proxy = TELEGRAM_PROXY if channel == "telegram" else MAX_PROXY
    if proxy:
        created_session.proxies.update({"http": proxy, "https": proxy})
    setattr(thread_local, session_attr, created_session)
    return created_session

TELEGRAM_API_BASE_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}" if TELEGRAM_TOKEN else None
MAX_API_BASE_URL = "https://platform-api.max.ru" if MAX_TOKEN else None
conversation_state: dict[str, dict[str, Any]] = {}
ui_state: dict[str, dict[str, str]] = {}
bot_profiles: dict[str, dict[str, Any]] = {
    "telegram": {"enabled": bool(TELEGRAM_TOKEN), "username": None, "name": None},
    "max": {"enabled": bool(MAX_TOKEN), "username": None, "name": None},
}
max_chat_link_cache: dict[str, str | None] = {}
logged_max_admin_candidates: set[tuple[str, ...]] = set()



def platform_enabled(platform: str) -> bool:
    return bool(bot_profiles.get(platform, {}).get("enabled"))



def actor_key(platform: str, chat_id: str | int) -> str:
    return f"{platform}:{chat_id}"



def get_platform_label(platform: str) -> str:
    return PLATFORM_LABELS.get(platform, platform)



def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()



def get_timezone_label() -> str:
    now_local = datetime.now(LOCAL_TZ)
    offset = now_local.utcoffset() or timedelta(0)
    total_minutes = int(offset.total_seconds() // 60)
    sign = "+" if total_minutes >= 0 else "-"
    total_minutes = abs(total_minutes)
    hours, minutes = divmod(total_minutes, 60)
    return f"UTC{sign}{hours:02d}:{minutes:02d}"



def format_local_time(iso_timestamp: str | None) -> str:
    if not iso_timestamp:
        return "вЂ”"
    dt_utc = datetime.fromisoformat(iso_timestamp)
    dt_local = dt_utc.astimezone(LOCAL_TZ)
    return f"{dt_local.strftime('%Y-%m-%d %H:%M')} {get_timezone_label()}"



def ensure_parent_dir(path: Path) -> None:
    parent = path.parent
    if parent != Path("") and not parent.exists():
        parent.mkdir(parents=True, exist_ok=True)



def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)



def atomic_write_text(path: Path, content: str, *, encoding: str = "utf-8") -> None:
    ensure_parent_dir(path)
    temp_path = path.with_name(f"{path.name}.tmp")
    temp_path.write_text(content, encoding=encoding)
    os.replace(temp_path, path)



def quarantine_corrupted_file(path: Path) -> Path | None:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    backup_path = path.with_name(f"{path.name}.corrupted.{timestamp}")
    try:
        shutil.copy2(path, backup_path)
    except OSError:
        return None
    return backup_path



def console_print(message: str) -> None:
    try:
        print(message)
    except UnicodeEncodeError:
        fallback = message.encode("unicode_escape", errors="backslashreplace").decode("ascii")
        print(fallback)



def load_json(path: Path, fallback: Any) -> Any:
    if not path.exists():
        return fallback

    try:
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)
    except (OSError, json.JSONDecodeError):
        backup_path = quarantine_corrupted_file(path)
        if backup_path is not None:
            console_print(f"вљ пёЏ РќРµ СѓРґР°Р»РѕСЃСЊ РїСЂРѕС‡РёС‚Р°С‚СЊ {path}. РЎРѕР·РґР°РЅР° СЂРµР·РµСЂРІРЅР°СЏ РєРѕРїРёСЏ: {backup_path}")
        else:
            console_print(f"вљ пёЏ РќРµ СѓРґР°Р»РѕСЃСЊ РїСЂРѕС‡РёС‚Р°С‚СЊ {path}. РСЃРїРѕР»СЊР·СѓСЋ СЂРµР·РµСЂРІРЅРѕРµ Р·РЅР°С‡РµРЅРёРµ РІ РїР°РјСЏС‚Рё.")
        return fallback


state = load_json(STATE_FILE, {"telegram_last_update_id": None, "max_marker": None})
orders: list[dict[str, Any]] = load_json(ORDERS_FILE, [])
catalog_items: list[dict[str, Any]] = load_json(CATALOG_FILE, [])



def save_state() -> None:
    with state_lock:
        atomic_write_text(
            STATE_FILE,
            json.dumps(state, ensure_ascii=False, indent=2),
        )



def save_orders() -> None:
    with state_lock:
        atomic_write_text(
            ORDERS_FILE,
            json.dumps(orders, ensure_ascii=False, indent=2),
        )



def save_catalog() -> None:
    with state_lock:
        atomic_write_text(
            CATALOG_FILE,
            json.dumps(catalog_items, ensure_ascii=False, indent=2),
        )



def parse_rubles(raw_value: str | int) -> int:
    if isinstance(raw_value, int):
        return max(raw_value, 0)
    cleaned = re.sub(r"(СЂСѓР±\.?|СЂ\.?|в‚Ѕ|\s|[.,])", "", str(raw_value).lower())
    if not cleaned.isdigit():
        raise ValueError("РЈРєР°Р¶Рё СЃСѓРјРјСѓ РІ СЂСѓР±Р»СЏС… С‡РёСЃР»РѕРј, РЅР°РїСЂРёРјРµСЂ 21000.")
    return int(cleaned)



def safe_parse_rubles(raw_value: Any, default: int = 0) -> int:
    try:
        return parse_rubles(raw_value)
    except ValueError:
        return default



def normalize_iso_timestamp(raw_value: Any, *, default_to_now: bool) -> str | None:
    if raw_value in {None, ""}:
        return now_utc_iso() if default_to_now else None
    try:
        return datetime.fromisoformat(str(raw_value)).isoformat()
    except ValueError:
        return now_utc_iso() if default_to_now else None



def normalize_customer_bindings(order: dict[str, Any]) -> list[dict[str, str]]:
    raw_bindings = order.get("customer_bindings")
    normalized: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    if isinstance(raw_bindings, list):
        for item in raw_bindings:
            if not isinstance(item, dict):
                continue
            platform = str(item.get("platform") or "").strip().lower()
            chat_id = str(item.get("chat_id") or "").strip()
            if platform not in PLATFORM_LABELS or not chat_id:
                continue
            key = (platform, chat_id)
            if key in seen:
                continue
            normalized.append(
                {
                    "platform": platform,
                    "chat_id": chat_id,
                    "linked_at": normalize_iso_timestamp(item.get("linked_at"), default_to_now=True) or now_utc_iso(),
                }
            )
            seen.add(key)

    legacy_chat_id = order.get("customer_chat_id")
    if legacy_chat_id not in {None, ""}:
        key = ("telegram", str(legacy_chat_id).strip())
        if key[1] and key not in seen:
            normalized.append({"platform": "telegram", "chat_id": key[1], "linked_at": now_utc_iso()})

    return normalized



def migrate_order(order: dict[str, Any]) -> dict[str, Any]:
    migrated = dict(order)
    if migrated.get("status") == "ready_waiting_delivery":
        migrated["status"] = "awaiting_delivery"

    total_price = migrated.get("total_price")
    if total_price is None:
        raw_price = migrated.get("price", "0")
        total_price = safe_parse_rubles(raw_price, default=0)
    migrated["total_price"] = total_price
    migrated["price"] = f"{total_price:,}".replace(",", ".") + " в‚Ѕ"

    paid_amount = migrated.get("paid_amount")
    if paid_amount is None:
        payment_percent = int(migrated.get("payment_percent", 0) or 0)
        paid_amount = round(total_price * payment_percent / 100)
    migrated["paid_amount"] = max(0, min(safe_parse_rubles(paid_amount, default=0), total_price))

    migrated["title"] = str(
        migrated.get("title") or migrated.get("caption") or f"Р›РµРіР°СЃРё Р·Р°РєР°Р· #{migrated.get('id', '?')}"
    ).strip()[:MAX_TITLE_LENGTH] or f"Р›РµРіР°СЃРё Р·Р°РєР°Р· #{migrated.get('id', '?')}"
    migrated["status"] = migrated.get("status") if migrated.get("status") in STATUS_LABELS else "awaiting"
    migrated["has_delivery"] = bool(migrated.get("has_delivery", False))
    migrated["created_at"] = normalize_iso_timestamp(migrated.get("created_at"), default_to_now=True)
    migrated.setdefault("notes", migrated.get("caption", ""))
    migrated["completed_at"] = normalize_iso_timestamp(migrated.get("completed_at"), default_to_now=False)
    migrated["updated_at"] = normalize_iso_timestamp(
        migrated.get("updated_at") or migrated.get("created_at"),
        default_to_now=True,
    )
    migrated.setdefault("delivery_planned_for", None)
    migrated["history"] = migrated.get("history") if isinstance(migrated.get("history"), list) else []
    migrated["customer_bindings"] = normalize_customer_bindings(migrated)
    migrated["customer_chat_id"] = next(
        (item["chat_id"] for item in migrated["customer_bindings"] if item["platform"] == "telegram"),
        None,
    )
    created_via = str(migrated.get("created_via") or migrated.get("origin_platform") or "telegram").lower()
    migrated["created_via"] = created_via if created_via in PLATFORM_LABELS else "telegram"
    return migrated



def migrate_loaded_orders(raw_orders: list[Any]) -> list[dict[str, Any]]:
    existing_ids = {
        int(item["id"])
        for item in raw_orders
        if isinstance(item, dict) and str(item.get("id", "")).isdigit() and int(item["id"]) > 0
    }
    next_generated_id = max(existing_ids, default=0) + 1
    used_ids: set[int] = set()
    used_tokens: set[str] = set()
    migrated_orders: list[dict[str, Any]] = []

    for raw_order in raw_orders:
        if not isinstance(raw_order, dict):
            continue

        migrated = migrate_order(raw_order)

        raw_id = migrated.get("id")
        order_id = int(raw_id) if str(raw_id).isdigit() and int(raw_id) > 0 else None
        if order_id is None or order_id in used_ids:
            order_id = next_generated_id
            next_generated_id += 1
        migrated["id"] = order_id
        used_ids.add(order_id)

        raw_token = str(migrated.get("token") or "").strip()
        if not raw_token or raw_token in used_tokens:
            raw_token = secrets.token_urlsafe(8)
        migrated["token"] = raw_token
        used_tokens.add(raw_token)

        migrated_orders.append(migrated)

    return migrated_orders



def migrate_catalog_item(item: dict[str, Any]) -> dict[str, Any]:
    migrated = dict(item)
    title = str(migrated.get("title") or migrated.get("name") or "").strip()
    if not title:
        title = f"РўРѕРІР°СЂ #{migrated.get('id', '?')}"
    migrated["title"] = title[:MAX_TITLE_LENGTH] or f"РўРѕРІР°СЂ #{migrated.get('id', '?')}"
    migrated["total_price"] = safe_parse_rubles(migrated.get("total_price") or migrated.get("price"), default=0)
    migrated["created_at"] = normalize_iso_timestamp(migrated.get("created_at"), default_to_now=True)
    return migrated



def migrate_catalog_items(raw_items: list[Any]) -> list[dict[str, Any]]:
    used_ids: set[int] = set()
    next_generated_id = 1
    migrated_items: list[dict[str, Any]] = []

    for raw_item in raw_items:
        if not isinstance(raw_item, dict):
            continue

        migrated = migrate_catalog_item(raw_item)
        raw_id = migrated.get("id")
        item_id = int(raw_id) if str(raw_id).isdigit() and int(raw_id) > 0 else None
        if item_id is None or item_id in used_ids:
            item_id = next_generated_id
            next_generated_id += 1
        migrated["id"] = item_id
        used_ids.add(item_id)
        next_generated_id = max(next_generated_id, item_id + 1)
        migrated_items.append(migrated)

    return migrated_items


orders = migrate_loaded_orders(orders)
catalog_items = migrate_catalog_items(catalog_items)
state.setdefault("telegram_last_update_id", state.get("last_update_id"))
state.setdefault("max_marker", None)
state.setdefault("next_order_id", max((item["id"] for item in orders), default=0) + 1)
state.setdefault("next_catalog_item_id", max((item["id"] for item in catalog_items), default=0) + 1)



def next_order_id() -> int:
    with state_lock:
        order_id = int(state.get("next_order_id", max((item["id"] for item in orders), default=0) + 1))
        state["next_order_id"] = order_id + 1
        save_state()
        return order_id



def next_catalog_item_id() -> int:
    with state_lock:
        item_id = int(state.get("next_catalog_item_id", max((item["id"] for item in catalog_items), default=0) + 1))
        state["next_catalog_item_id"] = item_id + 1
        save_state()
        return item_id



def generate_order_token() -> str:
    existing_tokens = {item["token"] for item in orders}
    while True:
        token = secrets.token_urlsafe(8)
        if token not in existing_tokens:
            return token



def set_conversation(actor: str, step: str, **extra: Any) -> None:
    conversation_state[actor] = {"step": step, **extra}



def clear_conversation(actor: str) -> None:
    conversation_state.pop(actor, None)



def set_ui_message(actor: str, message_id: str) -> None:
    ui_state[actor] = {"message_id": str(message_id)}



def get_ui_message_id(actor: str) -> str | None:
    return ui_state.get(actor, {}).get("message_id")



def json_dumps(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False)


def split_env_ids(raw_value: str | None) -> set[str]:
    if raw_value is None:
        return set()
    return {item.strip() for item in raw_value.split(",") if item.strip()}



def telegram_api_request(method: str, *, data: dict[str, Any] | None = None) -> dict[str, Any]:
    if not TELEGRAM_API_BASE_URL:
        raise RuntimeError("Telegram РЅРµ РЅР°СЃС‚СЂРѕРµРЅ")
    response = get_http_session("telegram").post(
        f"{TELEGRAM_API_BASE_URL}/{method}",
        data=data or {},
        timeout=REQUEST_TIMEOUT_SECONDS,
        allow_redirects=False,
    )
    response.raise_for_status()
    payload = response.json()
    if not payload.get("ok"):
        description = payload.get("description", "РќРµРёР·РІРµСЃС‚РЅР°СЏ РѕС€РёР±РєР° Telegram API")
        raise RuntimeError(f"Telegram API error in {method}: {description}")
    return payload



def get_local_mini_app_url() -> str:
    return f"http://{MINI_APP_HOST}:{MINI_APP_PORT}/"


def get_mini_app_public_url() -> str | None:
    if not MINI_APP_PUBLIC_URL:
        return None
    if not MINI_APP_CACHE_BUSTER:
        return MINI_APP_PUBLIC_URL

    parsed = urlparse(MINI_APP_PUBLIC_URL)
    query_items = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True) if k != "v"]
    query_items.append(("v", MINI_APP_CACHE_BUSTER))
    return urlunparse(parsed._replace(query=urlencode(query_items)))


def build_telegram_mini_app_button() -> dict[str, Any] | None:
    public_url = get_mini_app_public_url()
    if not public_url:
        return None
    return {"text": MINI_APP_BUTTON_TEXT, "web_app": {"url": public_url}}


def build_telegram_mini_app_inline_keyboard() -> dict[str, Any] | None:
    button = build_telegram_mini_app_button()
    if button is None:
        return None
    return {"inline_keyboard": [[button]]}


def build_order_mini_app_button(platform: str, order_token: str) -> dict[str, Any] | None:
    public_url = get_mini_app_public_url()
    if not public_url:
        return None

    parsed = urlparse(public_url)
    query_items = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True) if k != "order_token"]
    query_items.append(("order_token", order_token))
    order_url = urlunparse(parsed._replace(query=urlencode(query_items)))

    if platform == "telegram":
        return {"text": MINI_APP_BUTTON_TEXT, "web_app": {"url": order_url}}
    return {"text": MINI_APP_BUTTON_TEXT, "url": order_url}


def register_telegram_mini_app_menu_button() -> None:
    if not platform_enabled("telegram"):
        return
    if TELEGRAM_MENU_BUTTON_MODE == "commands":
        telegram_api_request(
            "setChatMenuButton",
            data={"menu_button": json_dumps({"type": "commands"})},
        )
        return
    public_url = get_mini_app_public_url()
    if not public_url:
        return
    telegram_api_request(
        "setChatMenuButton",
        data={
            "menu_button": json_dumps(
                {
                    "type": "web_app",
                    "text": MINI_APP_BUTTON_TEXT,
                    "web_app": {"url": public_url},
                }
            )
        },
    )


def register_telegram_commands() -> None:
    if not platform_enabled("telegram"):
        return

    public_commands = [
        {"command": "start", "description": "РћС‚РєСЂС‹С‚СЊ РјРµРЅСЋ"},
        {"command": "miniapp", "description": "РћС‚РєСЂС‹С‚СЊ РїСЂРёР»РѕР¶РµРЅРёРµ"},
    ]
    telegram_api_request("setMyCommands", data={"commands": json_dumps(public_commands)})

    if TELEGRAM_ADMIN_CHAT_ID:
        admin_commands = [
            {"command": "start", "description": "РћС‚РєСЂС‹С‚СЊ РјРµРЅСЋ"},
            {"command": "neworder", "description": "РЎРѕР·РґР°С‚СЊ Р·Р°РєР°Р·"},
            {"command": "orders", "description": "РЎРїРёСЃРѕРє Р·Р°РєР°Р·РѕРІ"},
            {"command": "catalog", "description": "РљР°С‚Р°Р»РѕРі С‚РѕРІР°СЂРѕРІ"},
            {"command": "report", "description": "РћС‚С‡С‘С‚ Р·Р° РїРµСЂРёРѕРґ"},
            {"command": "cancel", "description": "РћС‚РјРµРЅРёС‚СЊ РґРµР№СЃС‚РІРёРµ"},
            {"command": "miniapp", "description": "РћС‚РєСЂС‹С‚СЊ РїСЂРёР»РѕР¶РµРЅРёРµ"},
        ]
        telegram_api_request(
            "setMyCommands",
            data={
                "scope": json_dumps({"type": "chat", "chat_id": int(TELEGRAM_ADMIN_CHAT_ID)}),
                "commands": json_dumps(admin_commands),
            },
        )


def max_api_request(
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not MAX_API_BASE_URL or not MAX_TOKEN:
        raise RuntimeError("MAX РЅРµ РЅР°СЃС‚СЂРѕРµРЅ")
    response = get_http_session("max").request(
        method,
        f"{MAX_API_BASE_URL}{path}",
        params=params or None,
        json=json_body,
        headers={"Authorization": MAX_TOKEN},
        timeout=REQUEST_TIMEOUT_SECONDS + MAX_POLL_TIMEOUT_SECONDS,
        allow_redirects=False,
    )
    response.raise_for_status()
    if not response.content:
        return {}
    return response.json()



def convert_inline_keyboard_for_max(reply_markup: dict[str, Any]) -> list[dict[str, Any]]:
    buttons = reply_markup.get("inline_keyboard") if isinstance(reply_markup, dict) else None
    if not buttons:
        return []

    normalized_rows: list[list[dict[str, Any]]] = []
    for row in buttons:
        normalized_row: list[dict[str, Any]] = []
        for button in row:
            text = str(button.get("text") or "").strip()
            if not text:
                continue
            if button.get("url"):
                normalized_row.append({"type": "link", "text": text, "url": button["url"]})
            elif button.get("callback_data"):
                normalized_row.append(
                    {"type": "callback", "text": text, "payload": str(button["callback_data"])}
                )
        if normalized_row:
            normalized_rows.append(normalized_row)

    if not normalized_rows:
        return []

    return [{"type": "inline_keyboard", "payload": {"buttons": normalized_rows}}]



def get_max_recipient_candidates(chat_id: str) -> list[dict[str, Any]]:
    raw_chat_id = str(chat_id).strip()
    if not raw_chat_id:
        return []
    if raw_chat_id.startswith("chat:"):
        return [{"chat_id": raw_chat_id.split(":", maxsplit=1)[1]}]
    if raw_chat_id.startswith("user:"):
        return [{"user_id": raw_chat_id.split(":", maxsplit=1)[1]}]
    return [{"chat_id": raw_chat_id}, {"user_id": raw_chat_id}]



def send_message(
    platform: str,
    chat_id: str,
    text: str,
    *,
    reply_markup: dict[str, Any] | None = None,
    disable_web_page_preview: bool = True,
    parse_mode: str | None = None,
) -> dict[str, Any]:
    if platform == "telegram":
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": disable_web_page_preview,
        }
        if reply_markup:
            payload["reply_markup"] = json_dumps(reply_markup)
        if parse_mode:
            payload["parse_mode"] = parse_mode
        return telegram_api_request("sendMessage", data=payload).get("result", {})

    if platform == "max":
        body: dict[str, Any] = {"text": text}
        attachments = convert_inline_keyboard_for_max(reply_markup) if reply_markup else []
        if attachments:
            body["attachments"] = attachments
        if parse_mode:
            body["format"] = parse_mode.lower()
        last_http_error: requests.exceptions.HTTPError | None = None
        for params in get_max_recipient_candidates(chat_id):
            try:
                result = max_api_request("POST", "/messages", params=params, json_body=body)
                return result.get("message", result)
            except requests.exceptions.HTTPError as exc:
                if exc.response is not None and exc.response.status_code == 404:
                    last_http_error = exc
                    continue
                raise
        if last_http_error is not None:
            raise last_http_error
        raise RuntimeError("РќРµ СѓРґР°Р»РѕСЃСЊ РѕРїСЂРµРґРµР»РёС‚СЊ РїРѕР»СѓС‡Р°С‚РµР»СЏ РґР»СЏ MAX.")

    raise ValueError(f"РќРµРёР·РІРµСЃС‚РЅР°СЏ РїР»Р°С‚С„РѕСЂРјР°: {platform}")



def edit_message(
    platform: str,
    chat_id: str,
    message_id: str,
    text: str,
    *,
    reply_markup: dict[str, Any] | None = None,
    disable_web_page_preview: bool = True,
    parse_mode: str | None = None,
) -> dict[str, Any]:
    del disable_web_page_preview
    if platform == "telegram":
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "message_id": str(message_id),
            "text": text,
            "disable_web_page_preview": True,
        }
        if reply_markup:
            payload["reply_markup"] = json_dumps(reply_markup)
        if parse_mode:
            payload["parse_mode"] = parse_mode
        return telegram_api_request("editMessageText", data=payload).get("result", {})

    if platform == "max":
        body: dict[str, Any] = {"text": text}
        attachments = convert_inline_keyboard_for_max(reply_markup) if reply_markup else []
        body["attachments"] = attachments
        if parse_mode:
            body["format"] = parse_mode.lower()
        return max_api_request("PUT", "/messages", params={"message_id": message_id}, json_body=body)

    raise ValueError(f"РќРµРёР·РІРµСЃС‚РЅР°СЏ РїР»Р°С‚С„РѕСЂРјР°: {platform}")



def delete_message(platform: str, chat_id: str, message_id: str) -> None:
    if platform == "telegram":
        telegram_api_request(
            "deleteMessage",
            data={
                "chat_id": chat_id,
                "message_id": str(message_id),
            },
        )
        return

    if platform == "max":
        max_api_request("DELETE", "/messages", params={"message_id": message_id})
        return

    raise ValueError(f"РќРµРёР·РІРµСЃС‚РЅР°СЏ РїР»Р°С‚С„РѕСЂРјР°: {platform}")



def answer_callback_query(
    platform: str,
    callback_query_id: str,
    text: str = "",
    *,
    message_text: str | None = None,
    reply_markup: dict[str, Any] | None = None,
) -> None:
    if platform == "telegram":
        payload: dict[str, Any] = {"callback_query_id": callback_query_id}
        if text:
            payload["text"] = text
        telegram_api_request("answerCallbackQuery", data=payload)
        return

    if platform == "max":
        body: dict[str, Any] = {}
        if text:
            body["notification"] = text
        if message_text is not None:
            message_body: dict[str, Any] = {"text": message_text}
            attachments = convert_inline_keyboard_for_max(reply_markup) if reply_markup else []
            if attachments:
                message_body["attachments"] = attachments
            body["message"] = message_body
        max_api_request("POST", "/answers", params={"callback_id": callback_query_id}, json_body=body)
        return

    raise ValueError(f"РќРµРёР·РІРµСЃС‚РЅР°СЏ РїР»Р°С‚С„РѕСЂРјР°: {platform}")



def build_admin_reply_keyboard() -> dict[str, Any]:
    return {
        "keyboard": [[{"text": MENU_LABEL}]],
        "resize_keyboard": True,
        "is_persistent": True,
    }



def safe_delete_message(platform: str, chat_id: str, message_id: str | None) -> None:
    if message_id is None:
        return
    try:
        delete_message(platform, chat_id, message_id)
    except (RuntimeError, requests.exceptions.RequestException):
        return



def send_admin_message(
    platform: str,
    chat_id: str,
    text: str,
    *,
    inline_keyboard: dict[str, Any] | None = None,
    parse_mode: str | None = None,
    force_new: bool = False,
) -> str:
    actor = actor_key(platform, chat_id)
    message_id = None if force_new else get_ui_message_id(actor)
    if message_id is not None:
        try:
            edit_message(platform, chat_id, message_id, text, reply_markup=inline_keyboard, parse_mode=parse_mode)
            return message_id
        except RuntimeError as exc:
            if platform == "telegram" and "message is not modified" in str(exc).lower():
                return message_id
        except requests.exceptions.RequestException:
            pass

    result = send_message(platform, chat_id, text, reply_markup=inline_keyboard, parse_mode=parse_mode)
    new_message_id = extract_message_id(platform, result)
    if new_message_id is not None:
        set_ui_message(actor, new_message_id)

    return new_message_id or ""


def resend_admin_message_at_bottom(
    platform: str,
    chat_id: str,
    text: str,
    *,
    inline_keyboard: dict[str, Any] | None = None,
    parse_mode: str | None = None,
) -> str:
    actor = actor_key(platform, chat_id)
    safe_delete_message(platform, chat_id, get_ui_message_id(actor))
    return send_admin_message(
        platform,
        chat_id,
        text,
        inline_keyboard=inline_keyboard,
        parse_mode=parse_mode,
        force_new=True,
    )



def is_admin(platform: str, chat_id: str | int) -> bool:
    if platform == "telegram":
        return TELEGRAM_ADMIN_CHAT_ID is not None and str(chat_id) == str(TELEGRAM_ADMIN_CHAT_ID)
    if platform == "max":
        return is_max_admin_identity(chat_id)
    return False


def is_max_admin_identity(raw_value: str | int | None) -> bool:
    if MAX_ADMIN_CHAT_ID is None or raw_value in {None, ""}:
        return False
    value = str(raw_value).strip()
    configured_ids = split_env_ids(MAX_ADMIN_CHAT_ID)
    if not configured_ids:
        return False
    candidates = {value}
    normalized_value = value.split(":", maxsplit=1)[1] if ":" in value else value
    candidates.add(normalized_value)
    candidates.add(f"user:{normalized_value}")
    candidates.add(f"chat:{normalized_value}")
    return any(candidate in configured_ids for candidate in candidates)


def build_max_id_variants(raw_value: str | int | None) -> set[str]:
    if raw_value in {None, ""}:
        return set()
    value = str(raw_value).strip()
    if not value:
        return set()
    candidates = {value}
    normalized_value = value.split(":", maxsplit=1)[1] if ":" in value else value
    if normalized_value:
        candidates.add(normalized_value)
        candidates.add(f"user:{normalized_value}")
        candidates.add(f"chat:{normalized_value}")
    return candidates



def find_catalog_item_by_id(item_id: int) -> dict[str, Any] | None:
    for item in catalog_items:
        if item["id"] == item_id:
            return item
    return None



def get_order_bindings(order: dict[str, Any]) -> list[dict[str, str]]:
    bindings = normalize_customer_bindings(order)
    order["customer_bindings"] = bindings
    order["customer_chat_id"] = next(
        (item["chat_id"] for item in bindings if item["platform"] == "telegram"),
        None,
    )
    return bindings



def find_binding(order: dict[str, Any], platform: str, chat_id: str) -> dict[str, str] | None:
    for item in get_order_bindings(order):
        if item["platform"] != platform:
            continue
        if platform == "max":
            if build_max_id_variants(item["chat_id"]) & build_max_id_variants(chat_id):
                return item
            continue
        if item["chat_id"] == chat_id:
            return item
    return None


def link_customer_to_order(order: dict[str, Any], platform: str, chat_id: str) -> bool:
    if find_binding(order, platform, chat_id):
        return False
    bindings = get_order_bindings(order)
    bindings.append({"platform": platform, "chat_id": chat_id, "linked_at": now_utc_iso()})
    order["updated_at"] = now_utc_iso()
    order["customer_chat_id"] = next(
        (item["chat_id"] for item in bindings if item["platform"] == "telegram"),
        None,
    )
    return True



def find_orders_for_customer(platform: str, chat_id: str) -> list[dict[str, Any]]:
    return sorted(
        [order for order in orders if find_binding(order, platform, chat_id)],
        key=lambda item: item["id"],
        reverse=True,
    )



def has_customer_orders(platform: str, chat_id: str) -> bool:
    return bool(find_orders_for_customer(platform, chat_id))



def get_status_keys(has_delivery: bool) -> list[str]:
    keys = list(BASE_STATUS_KEYS)
    if has_delivery:
        keys.extend(DELIVERY_EXTRA_STATUS_KEYS)
    return keys



def get_status_progress(order: dict[str, Any]) -> tuple[int, int]:
    ordered_statuses = get_status_keys(order["has_delivery"]) + ["completed"]
    status_key = order["status"] if order["status"] in ordered_statuses else "awaiting"
    return ordered_statuses.index(status_key) + 1, len(ordered_statuses)



def get_status_label(status_key: str) -> str:
    return STATUS_LABELS.get(status_key, status_key)


CUSTOMER_STATUS_LABELS = {
    "awaiting": "Р’ РѕС‡РµСЂРµРґРё",
    "accepted": "Р’ СЂР°Р±РѕС‚Рµ",
    "production": "Р’ СЂР°Р±РѕС‚Рµ",
    "painting": "Р’ СЂР°Р±РѕС‚Рµ",
    "assembly": "РќР° СЃРѕРіР»Р°СЃРѕРІР°РЅРёРё",
    "ready": "Р“РѕС‚РѕРІ Рє РІС‹РґР°С‡Рµ / РѕС‚РїСЂР°РІРєРµ",
    "awaiting_delivery": "Р“РѕС‚РѕРІ Рє РІС‹РґР°С‡Рµ / РѕС‚РїСЂР°РІРєРµ",
    "in_transit": "Р’ РїСѓС‚Рё",
    "completed": "Р—Р°РІРµСЂС€С‘РЅРЅС‹Р№ Р·Р°РєР°Р·",
}

CUSTOMER_STATUS_DESCRIPTIONS = {
    "awaiting": "Р—Р°РєР°Р· СЃРѕР·РґР°РЅ Рё РѕР¶РёРґР°РµС‚ РїРѕРґС‚РІРµСЂР¶РґРµРЅРёСЏ.",
    "accepted": "Р—Р°РєР°Р· РїРѕРґС‚РІРµСЂР¶РґРµРЅ Рё РїРѕСЃС‚Р°РІР»РµРЅ РІ СЂР°Р±РѕС‚Сѓ.",
    "production": "РР·РіРѕС‚РѕРІР»РµРЅРёРµ СѓР¶Рµ РЅР°С‡Р°Р»РѕСЃСЊ.",
    "painting": "РРґРµС‚ СЌС‚Р°Рї РїРѕРєСЂР°СЃРєРё.",
    "assembly": "РЎР±РѕСЂРєР° Р·Р°РІРµСЂС€РёС‚СЃСЏ РїРѕСЃР»Рµ РІР°С€РµРіРѕ СЃРѕРіР»Р°СЃРѕРІР°РЅРёСЏ.",
    "ready": "Р—Р°РєР°Р· РіРѕС‚РѕРІ Рє РІС‹РґР°С‡Рµ РёР»Рё РѕС‚РїСЂР°РІРєРµ.",
    "awaiting_delivery": "Р—Р°РєР°Р· РіРѕС‚РѕРІ Рє РІС‹РґР°С‡Рµ РёР»Рё РѕС‚РїСЂР°РІРєРµ.",
    "in_transit": "Р—Р°РєР°Р· РІ РїСѓС‚Рё.",
    "completed": "Р—Р°РєР°Р· Р·Р°РІРµСЂС€РµРЅ. РЎРїР°СЃРёР±Рѕ Р·Р° РїРѕРєСѓРїРєСѓ!",
}


def get_customer_status_label(status_key: str) -> str:
    return CUSTOMER_STATUS_LABELS.get(status_key, get_status_label(status_key))


def get_customer_status_description(status_key: str) -> str:
    return CUSTOMER_STATUS_DESCRIPTIONS.get(status_key, "")


def build_customer_status_timeline(has_delivery: bool) -> list[dict[str, Any]]:
    steps = [
        {"key": "awaiting", "label": "Р’ РѕС‡РµСЂРµРґРё"},
        {"key": "accepted", "label": "Р’ СЂР°Р±РѕС‚Рµ"},
        {"key": "assembly", "label": "РќР° СЃРѕРіР»Р°СЃРѕРІР°РЅРёРё"},
        {"key": "ready", "label": "Р“РѕС‚РѕРІ Рє РІС‹РґР°С‡Рµ / РѕС‚РїСЂР°РІРєРµ"},
    ]
    if has_delivery:
        steps.append({"key": "in_transit", "label": "Р’ РїСѓС‚Рё"})
    steps.append({"key": "completed", "label": "Р—Р°РІРµСЂС€С‘РЅРЅС‹Р№ Р·Р°РєР°Р·"})
    return steps


def get_customer_status_step(order: dict[str, Any]) -> tuple[int, int]:
    timeline = build_customer_status_timeline(bool(order.get("has_delivery")))
    status_key = order.get("status", "awaiting")
    key_to_index = {item["key"]: index for index, item in enumerate(timeline, start=1)}
    if status_key in {"production", "painting"}:
        status_key = "accepted"
    if status_key == "awaiting_delivery":
        status_key = "ready"
    step = key_to_index.get(status_key, 1)
    return step, len(timeline)



def format_price(value: int) -> str:
    return f"{value:,}".replace(",", ".") + " в‚Ѕ"



def calculate_payment_percent(order: dict[str, Any]) -> int:
    total_price = max(order["total_price"], 1)
    return round(order["paid_amount"] * 100 / total_price)



def get_paid_text(order: dict[str, Any]) -> str:
    return (
        f"{calculate_payment_percent(order)}% "
        f"({format_price(order['paid_amount'])} РёР· {format_price(order['total_price'])})"
    )



def format_order_link(platform: str, token: str) -> str:
    username = bot_profiles.get(platform, {}).get("username")
    if not username:
        return f"РўРѕРєРµРЅ Р·Р°РєР°Р·Р°: {token}"
    if platform == "telegram":
        return f"https://t.me/{username}?start=order_{token}"
    if platform == "max":
        return f"https://max.ru/{username}?start=order_{token}"
    return token


def normalize_max_numeric_id(chat_id: str) -> str | None:
    raw_value = str(chat_id).strip()
    if not raw_value:
        return None
    if ":" in raw_value:
        raw_value = raw_value.split(":", maxsplit=1)[1].strip()
    return raw_value if re.fullmatch(r"-?\d+", raw_value) else None


def get_max_dialog_link(chat_id: str) -> str | None:
    normalized_chat_id = normalize_max_numeric_id(chat_id)
    if not normalized_chat_id:
        return None
    if normalized_chat_id in max_chat_link_cache:
        return max_chat_link_cache[normalized_chat_id]
    if not platform_enabled("max"):
        max_chat_link_cache[normalized_chat_id] = None
        return None
    try:
        chat_payload = max_api_request("GET", f"/chats/{normalized_chat_id}")
    except (RuntimeError, requests.exceptions.RequestException):
        max_chat_link_cache[normalized_chat_id] = None
        return None

    link = chat_payload.get("link")
    if isinstance(link, str) and link.strip():
        max_chat_link_cache[normalized_chat_id] = link.strip()
        return link.strip()

    dialog_with_user = chat_payload.get("dialog_with_user")
    username = dialog_with_user.get("username") if isinstance(dialog_with_user, dict) else None
    if isinstance(username, str) and username.strip():
        resolved_link = f"https://max.ru/{username.strip()}"
        max_chat_link_cache[normalized_chat_id] = resolved_link
        return resolved_link

    max_chat_link_cache[normalized_chat_id] = None
    return None


def build_customer_contact_links(order: dict[str, Any]) -> list[tuple[str, str]]:
    links: list[tuple[str, str]] = []
    for binding in get_order_bindings(order):
        chat_id = str(binding["chat_id"])
        if binding["platform"] == "telegram":
            normalized_chat_id = normalize_max_numeric_id(chat_id)
            if normalized_chat_id:
                links.append(("Telegram РєР»РёРµРЅС‚", f"tg://user?id={normalized_chat_id}"))
        elif binding["platform"] == "max":
            dialog_link = get_max_dialog_link(chat_id)
            if dialog_link:
                links.append(("MAX РєР»РёРµРЅС‚", dialog_link))
    return links


def build_client_share_text(order: dict[str, Any]) -> str:
    lines = [
        "Р’РѕС‚ СЃСЃС‹Р»РєРё, РіРґРµ РјРѕР¶РЅРѕ РїСЂРѕРІРµСЂРёС‚СЊ Рё РѕС‚СЃР»РµР¶РёРІР°С‚СЊ РІР°С€ Р·Р°РєР°Р·:",
        build_order_links_text(order),
        "",
        "Р•СЃР»Рё С‡С‚Рѕ-С‚Рѕ РЅРµ РѕС‚РєСЂС‹РІР°РµС‚СЃСЏ РёР»Рё РЅСѓР¶РЅРѕ СѓС‚РѕС‡РЅРµРЅРёРµ вЂ” РїСЂРѕСЃС‚Рѕ РЅР°РїРёС€РёС‚Рµ РЅР°Рј.",
    ]
    return "\n".join(lines)


def render_client_share_html(order: dict[str, Any]) -> str:
    quick_links = build_customer_contact_links(order)
    lines = [
        "вњ… Р—Р°РєР°Р· СЃРѕР·РґР°РЅ.",
        "",
        "Р“РѕС‚РѕРІС‹Р№ С‚РµРєСЃС‚ РґР»СЏ РѕС‚РїСЂР°РІРєРё РєР»РёРµРЅС‚Сѓ:",
        f"<pre>{html_escape(build_client_share_text(order))}</pre>",
    ]
    if quick_links:
        quick_lines = ["Р‘С‹СЃС‚СЂС‹Р№ РїРµСЂРµС…РѕРґ Рє РєР»РёРµРЅС‚Сѓ:"]
        quick_lines.extend(
            f'вЂў <a href="{html_escape(url)}">{html_escape(label)}</a>'
            for label, url in quick_links
        )
        lines.extend(["", "\n".join(quick_lines)])
    return "\n".join(lines)


def build_cancel_keyboard() -> dict[str, Any]:
    return {"inline_keyboard": [[{"text": "рџ›‘ РћС‚РјРµРЅР°", "callback_data": "flow:cancel"}]]}


def build_prompt_keyboard() -> dict[str, Any]:
    return {
        "inline_keyboard": [
            [{"text": "рџ›‘ РћС‚РјРµРЅР°", "callback_data": "flow:cancel"}],
            [{"text": "в¬…пёЏ Р’ РјРµРЅСЋ", "callback_data": "adminmenu:home"}],
        ]
    }



def build_order_links_text(order: dict[str, Any]) -> str:
    lines: list[str] = []
    for platform in ("telegram", "max"):
        if platform_enabled(platform):
            lines.append(f"{get_platform_label(platform)}: {format_order_link(platform, order['token'])}")
    return "\n".join(lines) if lines else f"РўРѕРєРµРЅ Р·Р°РєР°Р·Р°: {order['token']}"



def build_status_text(order: dict[str, Any]) -> str:
    current_step, total_steps = get_status_progress(order)
    return f"{get_status_label(order['status'])} ({current_step}/{total_steps})"


def serialize_order_for_mini_app(order: dict[str, Any]) -> dict[str, Any]:
    current_step, total_steps = get_status_progress(order)
    customer_step, customer_total_steps = get_customer_status_step(order)
    customer_timeline_raw = build_customer_status_timeline(order["has_delivery"])
    customer_timeline: list[dict[str, Any]] = []
    for index, item in enumerate(customer_timeline_raw, start=1):
        customer_timeline.append(
            {
                "key": item["key"],
                "label": item["label"],
                "index": index,
                "done": index < customer_step,
                "active": index == customer_step,
            }
        )
    status_keys = get_status_keys(order["has_delivery"]) + ["completed"]
    timeline: list[dict[str, Any]] = []
    for index, status_key in enumerate(status_keys, start=1):
        timeline.append(
            {
                "key": status_key,
                "label": get_status_label(status_key),
                "index": index,
                "done": index < current_step,
                "active": index == current_step,
            }
        )

    bindings = get_order_bindings(order)
    history_items = [
        {
            "timestamp": item.get("timestamp"),
            "timestamp_label": format_local_time(item.get("timestamp")),
            "text": item.get("text", ""),
        }
        for item in order.get("history", [])
        if isinstance(item, dict)
    ]

    return {
        "id": order["id"],
        "token": order["token"],
        "title": order["title"],
        "status": order["status"],
        "status_label": get_status_label(order["status"]),
        "status_text": build_status_text(order),
        "status_step": current_step,
        "status_total_steps": total_steps,
        "progress_percent": round(current_step * 100 / max(total_steps, 1)),
        "status_timeline": timeline,
        "customer_status_label": get_customer_status_label(order["status"]),
        "customer_status_description": get_customer_status_description(order["status"]),
        "customer_status_step": customer_step,
        "customer_status_total_steps": customer_total_steps,
        "customer_status_timeline": customer_timeline,
        "notes": order.get("notes") or "",
        "has_delivery": bool(order.get("has_delivery")),
        "delivery_mode_label": "Р”РѕСЃС‚Р°РІРєР°" if order.get("has_delivery") else "РЎР°РјРѕРІС‹РІРѕР·",
        "delivery_planned_for": order.get("delivery_planned_for"),
        "delivery_planned_for_label": order.get("delivery_planned_for") or "",
        "total_price": order["total_price"],
        "total_price_label": format_price(order["total_price"]),
        "paid_amount": order.get("paid_amount", 0),
        "paid_amount_label": format_price(order.get("paid_amount", 0)),
        "paid_percent": calculate_payment_percent(order),
        "paid_text": get_paid_text(order),
        "created_at": order.get("created_at"),
        "created_at_label": format_local_time(order.get("created_at")),
        "updated_at": order.get("updated_at"),
        "updated_at_label": format_local_time(order.get("updated_at")),
        "completed_at": order.get("completed_at"),
        "completed_at_label": format_local_time(order.get("completed_at")),
        "created_via": order.get("created_via", "telegram"),
        "created_via_label": get_platform_label(order.get("created_via", "telegram")),
        "customer_platforms": [binding["platform"] for binding in bindings],
        "customer_sources_text": get_order_sources_text(order),
        "history": history_items,
        "support_links": {
            "contact": CONTACT_URL,
            "vk": VK_URL,
            "telegram": TG_URL,
        },
    }


def get_public_order_payload(token: str) -> dict[str, Any] | None:
    with state_lock:
        order = find_order_by_token(token)
        if order is None:
            return None
        if str(order.get("lifecycle_state") or "").strip().lower() == "deleted":
            return None
        return serialize_order_for_mini_app(order)



def archive_file_path(order_id: int) -> Path:
    return ARCHIVE_DIR / f"order_{order_id:05d}.txt"



def append_history(order: dict[str, Any], text: str) -> None:
    order.setdefault("history", []).append({"timestamp": now_utc_iso(), "text": text})



def get_order_sources_text(order: dict[str, Any]) -> str:
    sources = [get_platform_label(item["platform"]) for item in get_order_bindings(order)]
    return ", ".join(sources) if sources else "РџРѕРєР° РЅРё РІ РѕРґРЅРѕРј РјРµСЃСЃРµРЅРґР¶РµСЂРµ"



def get_order_binding_details(order: dict[str, Any]) -> str:
    bindings = get_order_bindings(order)
    if not bindings:
        return "вЂ”"
    return "\n".join(
        f"вЂў {get_platform_label(item['platform'])}: {item['chat_id']}"
        for item in bindings
    )



def write_order_archive(order: dict[str, Any], lifecycle_state: str) -> None:
    ensure_dir(ARCHIVE_DIR)
    history_lines = order.get("history", [])
    lines = [
        f"Р—Р°РєР°Р· #{order['id']}",
        f"РЎРѕСЃС‚РѕСЏРЅРёРµ: {lifecycle_state}",
        f"РќР°РёРјРµРЅРѕРІР°РЅРёРµ: {order['title']}",
        f"РЎРѕР·РґР°РЅ С‡РµСЂРµР·: {get_platform_label(order.get('created_via', 'telegram'))}",
        f"РљР°РЅР°Р»С‹ РєР»РёРµРЅС‚Р°: {get_order_sources_text(order)}",
        f"Р¦РµРЅР°: {format_price(order['total_price'])}",
        f"РћРїР»Р°С‡РµРЅРѕ: {get_paid_text(order)}",
        f"РЎС‚Р°С‚СѓСЃ: {build_status_text(order)}",
        f"Р”РѕСЃС‚Р°РІРєР°: {'Р”Р°' if order['has_delivery'] else 'РќРµС‚'}",
        f"РЎРѕР·РґР°РЅ: {format_local_time(order['created_at'])}",
        f"РћР±РЅРѕРІР»С‘РЅ: {format_local_time(order.get('updated_at'))}",
        f"Р—Р°РІРµСЂС€С‘РЅ: {format_local_time(order.get('completed_at'))}",
        f"РџР»Р°РЅ РґРѕСЃС‚Р°РІРєРё: {order.get('delivery_planned_for') or 'вЂ”'}",
        f"РџСЂРёРјРµС‡Р°РЅРёРµ: {order.get('notes') or 'вЂ”'}",
        "",
        "РСЃС‚РѕСЂРёСЏ:",
    ]
    if history_lines:
        for item in history_lines:
            lines.append(f"- {format_local_time(item['timestamp'])}: {item['text']}")
    else:
        lines.append("- РСЃС‚РѕСЂРёСЏ РїРѕРєР° РїСѓСЃС‚Р°СЏ.")
    lines.append("")
    lines.append("DATA_JSON:")
    lines.append(
        json.dumps(
            {
                "id": order["id"],
                "created_at": order["created_at"],
                "updated_at": order.get("updated_at"),
                "completed_at": order.get("completed_at"),
                "status": order["status"],
                "lifecycle_state": lifecycle_state,
                "title": order["title"],
                "total_price": order["total_price"],
                "paid_amount": order["paid_amount"],
                "has_delivery": order["has_delivery"],
                "delivery_planned_for": order.get("delivery_planned_for"),
                "notes": order.get("notes", ""),
                "customer_bindings": get_order_bindings(order),
                "customer_chat_id": order.get("customer_chat_id"),
                "created_via": order.get("created_via", "telegram"),
                "history": history_lines,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    atomic_write_text(archive_file_path(order["id"]), "\n".join(lines))



def persist_order(order: dict[str, Any], lifecycle_state: str = "active") -> None:
    order["price"] = format_price(order["total_price"])
    order["customer_bindings"] = get_order_bindings(order)
    order["customer_chat_id"] = next(
        (item["chat_id"] for item in order["customer_bindings"] if item["platform"] == "telegram"),
        None,
    )
    save_orders()
    write_order_archive(order, lifecycle_state)



def load_archived_orders() -> list[dict[str, Any]]:
    ensure_dir(ARCHIVE_DIR)
    archived_orders: list[dict[str, Any]] = []
    for file in sorted(ARCHIVE_DIR.glob("order_*.txt")):
        try:
            content = file.read_text(encoding="utf-8")
        except OSError:
            continue
        marker = "\nDATA_JSON:\n"
        if marker not in content:
            continue
        payload = content.split(marker, maxsplit=1)[1]
        try:
            archived_orders.append(json.loads(payload))
        except json.JSONDecodeError:
            continue
    return archived_orders



def sync_archives() -> None:
    ensure_dir(ARCHIVE_DIR)
    for order in orders:
        lifecycle_state = "completed" if order["status"] == "completed" else "active"
        write_order_archive(order, lifecycle_state)



def find_order_by_id(order_id: int) -> dict[str, Any] | None:
    for order in orders:
        if order["id"] == order_id:
            return order
    return None



def find_order_by_token(token: str) -> dict[str, Any] | None:
    for order in orders:
        if order["token"] == token:
            return order
    return None



def create_order(
    *,
    title: str,
    total_price: int,
    paid_amount: int,
    has_delivery: bool,
    notes: str,
    created_via: str,
) -> dict[str, Any]:
    timestamp = now_utc_iso()
    order = {
        "id": next_order_id(),
        "token": generate_order_token(),
        "title": title,
        "price": format_price(total_price),
        "total_price": total_price,
        "paid_amount": max(0, min(paid_amount, total_price)),
        "status": "awaiting",
        "has_delivery": has_delivery,
        "notes": notes,
        "created_at": timestamp,
        "updated_at": timestamp,
        "completed_at": None,
        "customer_chat_id": None,
        "customer_bindings": [],
        "delivery_planned_for": None,
        "history": [],
        "created_via": created_via if created_via in PLATFORM_LABELS else "telegram",
    }
    append_history(order, f"Р—Р°РєР°Р· СЃРѕР·РґР°РЅ С‡РµСЂРµР· {get_platform_label(order['created_via'])}.")
    orders.append(order)
    persist_order(order)
    return order



def create_catalog_item(title: str, total_price: int) -> dict[str, Any]:
    item = {
        "id": next_catalog_item_id(),
        "title": title,
        "total_price": total_price,
        "created_at": now_utc_iso(),
    }
    catalog_items.append(item)
    save_catalog()
    return item



def delete_catalog_item(item_id: int) -> bool:
    for index, item in enumerate(catalog_items):
        if item["id"] == item_id:
            catalog_items.pop(index)
            save_catalog()
            return True
    return False



def update_order_status(order: dict[str, Any], status_key: str) -> None:
    order["status"] = status_key
    order["updated_at"] = now_utc_iso()
    if status_key != "awaiting_delivery":
        order["delivery_planned_for"] = None
    append_history(order, f"РЎС‚Р°С‚СѓСЃ РёР·РјРµРЅС‘РЅ РЅР° В«{get_status_label(status_key)}В».")
    persist_order(order, "completed" if order["status"] == "completed" else "active")



def set_delivery_schedule(order: dict[str, Any], schedule_text: str) -> None:
    order["status"] = "awaiting_delivery"
    order["delivery_planned_for"] = schedule_text.strip()
    order["updated_at"] = now_utc_iso()
    append_history(order, f"Р”РѕСЃС‚Р°РІРєР° Р·Р°РїР»Р°РЅРёСЂРѕРІР°РЅР° РЅР° {order['delivery_planned_for']}.")
    persist_order(order)



def update_delivery_flag(order: dict[str, Any], has_delivery: bool) -> None:
    order["has_delivery"] = has_delivery
    if not has_delivery and order["status"] in DELIVERY_EXTRA_STATUS_KEYS:
        order["status"] = "ready"
        order["delivery_planned_for"] = None
    order["updated_at"] = now_utc_iso()
    append_history(order, f"РР·РјРµРЅС‘РЅ СЃРїРѕСЃРѕР± РїРѕР»СѓС‡РµРЅРёСЏ: {'РґРѕСЃС‚Р°РІРєР°' if has_delivery else 'СЃР°РјРѕРІС‹РІРѕР·'}.")
    persist_order(order)



def add_payment(order: dict[str, Any], amount: int) -> None:
    order["paid_amount"] = min(order["total_price"], order["paid_amount"] + amount)
    order["updated_at"] = now_utc_iso()
    append_history(order, f"Р”РѕР±Р°РІР»РµРЅР° РѕРїР»Р°С‚Р° {format_price(amount)}.")
    persist_order(order, "completed" if order["status"] == "completed" else "active")



def mark_fully_paid(order: dict[str, Any]) -> None:
    order["paid_amount"] = order["total_price"]
    order["updated_at"] = now_utc_iso()
    append_history(order, "Р—Р°РєР°Р· РѕС‚РјРµС‡РµРЅ РєР°Рє РїРѕР»РЅРѕСЃС‚СЊСЋ РѕРїР»Р°С‡РµРЅРЅС‹Р№.")
    persist_order(order, "completed" if order["status"] == "completed" else "active")



def delete_order(order_id: int) -> bool:
    for index, order in enumerate(orders):
        if order["id"] != order_id:
            continue
        removed_order = orders.pop(index)
        save_orders()
        write_order_archive(removed_order, "deleted")
        return True
    return False



def complete_order(order: dict[str, Any]) -> None:
    order["status"] = "completed"
    order["completed_at"] = now_utc_iso()
    order["updated_at"] = now_utc_iso()
    append_history(order, "Р—Р°РєР°Р· Р·Р°РІРµСЂС€С‘РЅ.")
    persist_order(order, "completed")



def build_public_keyboard(platform: str, chat_id: str | None = None, include_refresh_token: str | None = None) -> dict[str, Any]:
    keyboard: list[list[dict[str, Any]]] = []
    if include_refresh_token:
        order_mini_app_button = build_order_mini_app_button(platform, include_refresh_token)
        if order_mini_app_button is not None:
            keyboard.append([order_mini_app_button])
        keyboard.append([{"text": "РћР±РЅРѕРІРёС‚СЊ СЃС‚Р°С‚СѓСЃ", "callback_data": f"client:refresh:{include_refresh_token}"}])
    if chat_id and has_customer_orders(platform, chat_id):
        keyboard.append([{"text": "РњРѕРё Р·Р°РєР°Р·С‹", "callback_data": "client:list"}])
    keyboard.extend(
        [
            [{"text": "РЎРІСЏР·Р°С‚СЊСЃСЏ", "url": CONTACT_URL}],
            [{"text": "РЎРѕС†.СЃРµС‚Рё РљСѓР»СЊС‚ РњРµР±РµР»СЊ", "callback_data": "public:socials"}],
        ]
    )
    return {"inline_keyboard": keyboard}



def build_customer_orders_text(platform: str, chat_id: str) -> str:
    customer_orders = find_orders_for_customer(platform, chat_id)
    if not customer_orders:
        return "РЈ РІР°СЃ РїРѕРєР° РЅРµС‚ РїСЂРёРІСЏР·Р°РЅРЅС‹С… Р·Р°РєР°Р·РѕРІ. РћС‚РєСЂРѕР№С‚Рµ РїРµСЂСЃРѕРЅР°Р»СЊРЅСѓСЋ СЃСЃС‹Р»РєСѓ, РєРѕС‚РѕСЂСѓСЋ РІР°Рј РѕС‚РїСЂР°РІРёР» РјРµРЅРµРґР¶РµСЂ."

    total_sum = sum(order["total_price"] for order in customer_orders)
    total_paid = sum(order["paid_amount"] for order in customer_orders)
    lines = [
        "рџ“¦ Р’Р°С€Рё Р·Р°РєР°Р·С‹:",
        f"Р’СЃРµРіРѕ Р·Р°РєР°Р·РѕРІ: {len(customer_orders)}",
        f"РћР±С‰Р°СЏ СЃСѓРјРјР°: {format_price(total_sum)}",
        f"РћРїР»Р°С‡РµРЅРѕ СЃСѓРјРјР°СЂРЅРѕ: {format_price(total_paid)}",
    ]
    for order in customer_orders:
        lines.append(
            "\n".join(
                [
                    f"рџ“¦ Р—Р°РєР°Р· #{order['id']}",
                    order["title"],
                    f"РЎС‚Р°С‚СѓСЃ: {build_status_text(order)}",
                    f"Р¦РµРЅР°: {format_price(order['total_price'])}",
                    f"РћРїР»Р°С‡РµРЅРѕ: {get_paid_text(order)}",
                    f"РЎРѕР·РґР°РЅ: {format_local_time(order['created_at'])}",
                    f"РћС‚РєСЂС‹С‚ РІ: {get_order_sources_text(order)}",
                ]
            )
        )
    return "\n\n".join(lines)



def build_customer_orders_keyboard(platform: str, chat_id: str) -> dict[str, Any]:
    rows: list[list[dict[str, Any]]] = []
    for order in find_orders_for_customer(platform, chat_id):
        rows.append(
            [
                {
                    "text": f"РћС‚РєСЂС‹С‚СЊ #{order['id']} вЂ” {order['title'][:28]}",
                    "callback_data": f"client:view:{order['token']}",
                }
            ]
        )
    rows.append([{"text": "РЎРІСЏР·Р°С‚СЊСЃСЏ", "url": CONTACT_URL}])
    rows.append([{"text": "РЎРѕС†.СЃРµС‚Рё РљСѓР»СЊС‚ РњРµР±РµР»СЊ", "callback_data": "public:socials"}])
    return {"inline_keyboard": rows}



def build_socials_keyboard() -> dict[str, Any]:
    return {
        "inline_keyboard": [
            [
                {"text": "VK", "url": VK_URL},
                {"text": "Telegram", "url": TG_URL},
            ]
        ]
    }



def format_admin_order_text(order: dict[str, Any]) -> str:
    base_text = render_order_text(order, for_admin=True)
    quick_links = build_customer_contact_links(order)
    if not quick_links:
        return base_text
    lines = ["Р‘С‹СЃС‚СЂС‹Р№ РїРµСЂРµС…РѕРґ Рє РєР»РёРµРЅС‚Сѓ:"]
    lines.extend(f"вЂў {label}: {url}" for label, url in quick_links)
    return f"{base_text}\n\n" + "\n".join(lines)



def build_admin_home_keyboard() -> dict[str, Any]:
    return {
        "inline_keyboard": [
            [
                {"text": "рџ†• РќРѕРІС‹Р№ Р·Р°РєР°Р·", "callback_data": "adminmenu:neworder"},
                {"text": "рџ—‚ Р—Р°РєР°Р·С‹", "callback_data": "admin:list"},
            ],
            [
                {"text": "рџ“љ РљР°С‚Р°Р»РѕРі", "callback_data": "catalog:list"},
                {"text": "рџ“Љ РћС‚С‡С‘С‚", "callback_data": "adminmenu:report"},
            ],
        ]
    }



def build_catalog_list_text() -> str:
    if not catalog_items:
        return (
            "рџ“љ РљР°С‚Р°Р»РѕРі РїРѕРєР° РїСѓСЃС‚.\n\n"
            "РќР°Р¶РјРё В«Р”РѕР±Р°РІРёС‚СЊ С‚РѕРІР°СЂВ», Р·Р°С‚РµРј РѕС‚РїСЂР°РІСЊ РЅР°Р·РІР°РЅРёРµ Рё С†РµРЅСѓ вЂ” РїРѕСЃР»Рµ СЌС‚РѕРіРѕ С‚РѕРІР°СЂ РјРѕР¶РЅРѕ Р±СѓРґРµС‚ РІС‹Р±РёСЂР°С‚СЊ РїСЂРё СЃРѕР·РґР°РЅРёРё Р·Р°РєР°Р·Р°."
        )

    lines = ["рџ“љ РљР°С‚Р°Р»РѕРі С‚РѕРІР°СЂРѕРІ:"]
    for item in sorted(catalog_items, key=lambda value: value["id"]):
        lines.append(f"#{item['id']} вЂў {item['title']}\nР¦РµРЅР°: {format_price(item['total_price'])}")
    return "\n\n".join(lines)



def build_catalog_list_keyboard() -> dict[str, Any]:
    rows: list[list[dict[str, Any]]] = []
    for item in sorted(catalog_items, key=lambda value: value["id"]):
        rows.append(
            [
                {
                    "text": f"{item['title'][:28]} вЂ” {format_price(item['total_price'])}",
                    "callback_data": f"catalog:view:{item['id']}",
                }
            ]
        )
    rows.append([{"text": "вћ• Р”РѕР±Р°РІРёС‚СЊ С‚РѕРІР°СЂ", "callback_data": "catalog:add"}])
    rows.append([{"text": "в¬…пёЏ Р’ РјРµРЅСЋ", "callback_data": "adminmenu:home"}])
    return {"inline_keyboard": rows}



def build_catalog_item_keyboard(item_id: int) -> dict[str, Any]:
    return {
        "inline_keyboard": [
            [{"text": "рџ—‘ РЈРґР°Р»РёС‚СЊ С‚РѕРІР°СЂ", "callback_data": f"catalog:delete:{item_id}"}],
            [{"text": "в¬…пёЏ Рљ РєР°С‚Р°Р»РѕРіСѓ", "callback_data": "catalog:list"}],
        ]
    }



def build_catalog_pick_keyboard() -> dict[str, Any]:
    rows: list[list[dict[str, Any]]] = []
    for item in sorted(catalog_items, key=lambda value: value["id"]):
        rows.append(
            [
                {
                    "text": f"{item['title'][:24]} вЂ” {format_price(item['total_price'])}",
                    "callback_data": f"create:item:{item['id']}",
                }
            ]
        )
    rows.append([{"text": "рџ“љ РљР°С‚Р°Р»РѕРі", "callback_data": "catalog:list"}])
    rows.append([{"text": "в¬…пёЏ Р’ РјРµРЅСЋ", "callback_data": "adminmenu:home"}])
    return {"inline_keyboard": rows}



def build_payment_choice_keyboard() -> dict[str, Any]:
    return {
        "inline_keyboard": [
            [
                {"text": "0%", "callback_data": "create:payment:0"},
                {"text": "50%", "callback_data": "create:payment:50"},
                {"text": "100%", "callback_data": "create:payment:100"},
            ]
        ]
    }



def build_delivery_choice_keyboard() -> dict[str, Any]:
    return {
        "inline_keyboard": [
            [
                {"text": "Р”Р°", "callback_data": "create:delivery:yes"},
                {"text": "РќРµС‚", "callback_data": "create:delivery:no"},
            ]
        ]
    }



def chunk_buttons(buttons: list[dict[str, Any]], chunk_size: int) -> list[list[dict[str, Any]]]:
    return [buttons[index : index + chunk_size] for index in range(0, len(buttons), chunk_size)]



def build_admin_order_keyboard(order: dict[str, Any]) -> dict[str, Any]:
    status_buttons = [
        {
            "text": f"{'вњ… ' if order['status'] == status_key else ''}{get_status_label(status_key)}",
            "callback_data": f"admin:status:{order['id']}:{status_key}",
        }
        for status_key in get_status_keys(order["has_delivery"])
    ]
    inline_keyboard = chunk_buttons(status_buttons, 2)
    inline_keyboard.append(
        [
            {
                "text": f"{'рџљљ' if order['has_delivery'] else 'рџ›»'} {'Р”РѕСЃС‚Р°РІРєР°' if order['has_delivery'] else 'РЎР°РјРѕРІС‹РІРѕР·'}",
                "callback_data": f"admin:delivery_toggle:{order['id']}",
            }
        ]
    )
    if order["paid_amount"] < order["total_price"]:
        inline_keyboard.append(
            [
                {"text": "рџ’Ї РљР»РёРµРЅС‚ РѕРїР»Р°С‚РёР» РІСЃС‘", "callback_data": f"admin:payment_full:{order['id']}"},
                {"text": "рџ’µ Р”РѕР±Р°РІРёС‚СЊ РѕРїР»Р°С‚Сѓ", "callback_data": f"admin:payment_add:{order['id']}"},
            ]
        )
    inline_keyboard.append(
        [
            {"text": "Р—Р°РІРµСЂС€РёС‚СЊ Р·Р°РєР°Р·", "callback_data": f"admin:finish:{order['id']}"},
            {"text": "РЈРґР°Р»РёС‚СЊ Р·Р°РєР°Р·", "callback_data": f"admin:delete:{order['id']}"},
        ]
    )
    inline_keyboard.append([{"text": "Рљ СЃРїРёСЃРєСѓ Р·Р°РєР°Р·РѕРІ", "callback_data": "admin:list"}])
    return {"inline_keyboard": inline_keyboard}



def build_finish_confirmation_keyboard(order_id: int) -> dict[str, Any]:
    return {
        "inline_keyboard": [
            [
                {"text": "Р”Р°, Р·Р°РІРµСЂС€РёС‚СЊ", "callback_data": f"admin:finish_yes:{order_id}"},
                {"text": "РќРµС‚", "callback_data": f"admin:finish_no:{order_id}"},
            ]
        ]
    }



def build_delete_confirmation_keyboard(order_id: int) -> dict[str, Any]:
    return {
        "inline_keyboard": [
            [
                {"text": "Р”Р°, СѓРґР°Р»РёС‚СЊ", "callback_data": f"admin:delete_yes:{order_id}"},
                {"text": "РќРµС‚", "callback_data": f"admin:delete_no:{order_id}"},
            ]
        ]
    }



def build_active_orders() -> list[dict[str, Any]]:
    return sorted(
        [order for order in orders if order["status"] != "completed"],
        key=lambda item: item["created_at"],
    )



def build_orders_list_text() -> str:
    active_orders = build_active_orders()
    if not active_orders:
        return "рџ“­ РЎРµР№С‡Р°СЃ Р°РєС‚РёРІРЅС‹С… Р·Р°РєР°Р·РѕРІ РЅРµС‚. РСЃРїРѕР»СЊР·СѓР№ /neworder, С‡С‚РѕР±С‹ СЃРѕР·РґР°С‚СЊ РЅРѕРІС‹Р№ Р·Р°РєР°Р·."

    lines = ["рџ—‚ РўРµРєСѓС‰РёРµ Р·Р°РєР°Р·С‹:"]
    for order in active_orders:
        lines.append(
            "\n".join(
                [
                    f"рџ“¦ Р—Р°РєР°Р· #{order['id']}",
                    order["title"],
                    f"РЎРѕР·РґР°РЅ С‡РµСЂРµР·: {get_platform_label(order.get('created_via', 'telegram'))}",
                    f"РљР°РЅР°Р»С‹ РєР»РёРµРЅС‚Р°: {get_order_sources_text(order)}",
                    f"РЎС‚Р°С‚СѓСЃ: {build_status_text(order)}",
                    f"РћРїР»Р°С‡РµРЅРѕ: {get_paid_text(order)}",
                    f"РЎРѕР·РґР°РЅ: {format_local_time(order['created_at'])}",
                ]
            )
        )
    return "\n\n".join(lines)



def build_orders_list_keyboard() -> dict[str, Any] | None:
    active_orders = build_active_orders()
    if not active_orders:
        return {"inline_keyboard": [[{"text": "в¬…пёЏ Р’ РјРµРЅСЋ", "callback_data": "adminmenu:home"}]]}

    rows: list[list[dict[str, Any]]] = []
    for order in active_orders:
        rows.append(
            [
                {
                    "text": f"РћС‚РєСЂС‹С‚СЊ #{order['id']} вЂ” {order['title'][:30]}",
                    "callback_data": f"admin:view:{order['id']}",
                }
            ]
        )
    rows.append([{"text": "в¬…пёЏ Р’ РјРµРЅСЋ", "callback_data": "adminmenu:home"}])
    return {"inline_keyboard": rows}



def render_order_text(order: dict[str, Any], *, for_admin: bool) -> str:
    blocks = [
        "\n".join(
            [
                f"рџ“¦ Р—Р°РєР°Р· #{order['id']}",
                order["title"],
                f"РЎС‚Р°С‚СѓСЃ: {build_status_text(order)}",
                f"РџСЂРёРјРµС‡Р°РЅРёРµ: {order.get('notes') or 'вЂ”'}",
            ]
        ),
        "\n".join(
            [
                f"Р¦РµРЅР°: {format_price(order['total_price'])}",
                f"РћРїР»Р°С‡РµРЅРѕ: {get_paid_text(order)}",
            ]
        ),
        "\n".join(
            [
                f"Р”РѕСЃС‚Р°РІРєР°: {'Р”Р°' if order['has_delivery'] else 'РќРµС‚'}",
                f"РЎРѕР·РґР°РЅ: {format_local_time(order['created_at'])}",
                f"РЎРѕР·РґР°РЅ С‡РµСЂРµР·: {get_platform_label(order.get('created_via', 'telegram'))}",
            ]
        ),
    ]

    if for_admin:
        admin_lines = [
            "РЎСЃС‹Р»РєРё РґР»СЏ РєР»РёРµРЅС‚Р°:",
            build_order_links_text(order),
            f"РљР»РёРµРЅС‚ РїРѕРґРєР»СЋС‡С‘РЅ РІ: {get_order_sources_text(order)}",
            f"ID РєР»РёРµРЅС‚РѕРІ:\n{get_order_binding_details(order)}",
        ]
        if order.get("completed_at"):
            admin_lines.append(f"Р—Р°РІРµСЂС€С‘РЅ: {format_local_time(order['completed_at'])}")
        blocks.append("\n".join(admin_lines))
    else:
        customer_lines = ["РЎСЂРѕРє РёР·РіРѕС‚РѕРІР»РµРЅРёСЏ СѓРєР°Р·Р°РЅ РІ РѕС„РµСЂС‚Рµ."]
        if order.get("paid_amount", 0) < order.get("total_price", 0):
            customer_lines.append("Р•СЃР»Рё РІР°Рј РЅРµРѕР±С…РѕРґРёРјРѕ РґРѕРїР»Р°С‚РёС‚СЊ, РЅР°Р¶РјРёС‚Рµ РєРЅРѕРїРєСѓ В«РЎРІСЏР·Р°С‚СЊСЃСЏВ».")
        if order["status"] == "ready":
            if order["has_delivery"]:
                customer_lines.append(
                    "Р’ Р±Р»РёР¶Р°Р№С€РµРµ РІСЂРµРјСЏ РјС‹ РЅР°РїРёС€РµРј РІР°Рј РґР»СЏ СѓС‚РѕС‡РЅРµРЅРёСЏ РІРѕРїСЂРѕСЃР° РґРѕСЃС‚Р°РІРєРё. Р•СЃР»Рё РЅСѓР¶РЅРѕ Р±С‹СЃС‚СЂРµРµ вЂ” РЅР°Р¶РјРёС‚Рµ В«РЎРІСЏР·Р°С‚СЊСЃСЏВ»."
                )
            else:
                customer_lines.append(
                    "Р’ Р±Р»РёР¶Р°Р№С€РµРµ РІСЂРµРјСЏ РјС‹ РЅР°РїРёС€РµРј РІР°Рј РґР»СЏ СѓС‚РѕС‡РЅРµРЅРёСЏ РІРѕРїСЂРѕСЃР° СЃР°РјРѕРІС‹РІРѕР·Р°. Р•СЃР»Рё РЅСѓР¶РЅРѕ Р±С‹СЃС‚СЂРµРµ вЂ” РЅР°Р¶РјРёС‚Рµ В«РЎРІСЏР·Р°С‚СЊСЃСЏВ»."
                )
        if order["status"] == "awaiting_delivery" and order.get("delivery_planned_for"):
            customer_lines.append(f"Р”РѕСЃС‚Р°РІРєР° Р·Р°РїР»Р°РЅРёСЂРѕРІР°РЅР° РЅР° {order['delivery_planned_for']}.")
        if order["status"] == "completed":
            customer_lines.append("РЎРїР°СЃРёР±Рѕ Р·Р° Р·Р°РєР°Р·! Р•СЃР»Рё РїРѕРЅР°РґРѕР±РёС‚СЃСЏ РµС‰С‘ РјРµР±РµР»СЊ вЂ” РјС‹ РЅР° СЃРІСЏР·Рё.")
        blocks.append("\n".join(customer_lines))

    return "\n\n".join(blocks)



def send_order_snapshot(platform: str, chat_id: str, order: dict[str, Any]) -> None:
    send_message(
        platform,
        chat_id,
        render_order_text(order, for_admin=False),
        reply_markup=build_public_keyboard(platform, chat_id, order["token"]),
    )



def send_customer_orders(platform: str, chat_id: str) -> None:
    send_message(
        platform,
        chat_id,
        build_customer_orders_text(platform, chat_id),
        reply_markup=build_customer_orders_keyboard(platform, chat_id),
    )



def notify_customer_order_update(order: dict[str, Any], intro_text: str) -> None:
    for binding in get_order_bindings(order):
        send_message(
            binding["platform"],
            binding["chat_id"],
            f"{intro_text}\n\n{render_order_text(order, for_admin=False)}",
            reply_markup=build_public_keyboard(binding["platform"], binding["chat_id"], order["token"]),
        )



def send_public_welcome(platform: str, chat_id: str) -> None:
    reply_markup = build_public_keyboard(platform, chat_id)
    mini_app_keyboard = build_telegram_mini_app_inline_keyboard() if platform == "telegram" else None
    if mini_app_keyboard:
        reply_markup = {
            "inline_keyboard": mini_app_keyboard["inline_keyboard"] + reply_markup["inline_keyboard"]
        }
    send_message(
        platform,
        chat_id,
        (
            "РџСЂРёРІРµС‚! Р­С‚Рѕ Р±РѕС‚ РљСѓР»СЊС‚ РњРµР±РµР»СЊ РґР»СЏ РѕС‚СЃР»РµР¶РёРІР°РЅРёСЏ Р·Р°РєР°Р·РѕРІ.\n\n"
            "Р•СЃР»Рё РјРµРЅРµРґР¶РµСЂ СѓР¶Рµ РѕС‚РїСЂР°РІРёР» РІР°Рј РїРµСЂСЃРѕРЅР°Р»СЊРЅСѓСЋ СЃСЃС‹Р»РєСѓ вЂ” РѕС‚РєСЂРѕР№С‚Рµ РµС‘, Рё Р±РѕС‚ РїРѕРєР°Р¶РµС‚ СЃС‚Р°С‚СѓСЃ Р·Р°РєР°Р·Р°.\n"
            "Р•СЃР»Рё СЃСЃС‹Р»РєРё РµС‰С‘ РЅРµС‚, РЅР°РїРёС€РёС‚Рµ РЅР°Рј вЂ” РїРѕРјРѕР¶РµРј РѕС„РѕСЂРјРёС‚СЊ Р·Р°РєР°Р· Рё РѕС‚РІРµС‚РёРј РЅР° РІРѕРїСЂРѕСЃС‹."
        ),
        reply_markup=reply_markup,
    )



def send_admin_help(platform: str, chat_id: str) -> None:
    channels = []
    if platform_enabled("telegram"):
        channels.append("Telegram")
    if platform_enabled("max"):
        channels.append("MAX")
    send_admin_message(
        platform,
        chat_id,
        (
            "Р”РѕР±СЂРѕ РїРѕР¶Р°Р»РѕРІР°С‚СЊ РІ РїР°РЅРµР»СЊ Р·Р°РєР°Р·РѕРІ РљСѓР»СЊС‚ РњРµР±РµР»СЊ.\n\n"
            "Р’СЃСЏ СЂР°Р±РѕС‚Р° РІРµРґС‘С‚СЃСЏ РІ РѕРґРЅРѕРј СЃРѕРѕР±С‰РµРЅРёРё: РѕС‚РєСЂС‹РІР°Р№ СЂР°Р·РґРµР»С‹ РєРЅРѕРїРєР°РјРё РЅРёР¶Рµ.\n\n"
            "Р”РѕСЃС‚СѓРїРЅРѕ:\n"
            "вЂў /neworder вЂ” СЃРѕР·РґР°С‚СЊ Р·Р°РєР°Р·\n"
            "вЂў /orders вЂ” РѕС‚РєСЂС‹С‚СЊ С‚РµРєСѓС‰РёРµ Р·Р°РєР°Р·С‹\n"
            "вЂў /catalog вЂ” РєР°С‚Р°Р»РѕРі С‚РѕРІР°СЂРѕРІ\n"
            "вЂў /report вЂ” РѕС‚С‡С‘С‚ РїРѕ РїРµСЂРёРѕРґСѓ\n"
            "вЂў /cancel вЂ” РѕС‚РјРµРЅРёС‚СЊ С‚РµРєСѓС‰РµРµ РґРµР№СЃС‚РІРёРµ\n\n"
            f"РђРєС‚РёРІРЅС‹Рµ РєР°РЅР°Р»С‹ Р±РѕС‚Р°: {', '.join(channels)}. Р—Р°РєР°Р·С‹ СЃРёРЅС…СЂРѕРЅРёР·РёСЂСѓСЋС‚СЃСЏ РјРµР¶РґСѓ РјРµСЃСЃРµРЅРґР¶РµСЂР°РјРё."
        ),
        inline_keyboard=build_admin_home_keyboard(),
    )



def parse_paid_amount(raw_value: str) -> int:
    amount = parse_rubles(raw_value)
    if amount <= 0:
        raise ValueError("РЎСѓРјРјР° РґРѕРїР»Р°С‚С‹ РґРѕР»Р¶РЅР° Р±С‹С‚СЊ Р±РѕР»СЊС€Рµ РЅСѓР»СЏ.")
    return amount



def parse_russian_period(raw_value: str) -> tuple[datetime, datetime]:
    parts = [part.strip().lower() for part in raw_value.split("_", maxsplit=1)]
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise ValueError("РџРµСЂРёРѕРґ РЅСѓР¶РЅРѕ РІРІРµСЃС‚Рё РІ С„РѕСЂРјР°С‚Рµ: 22 СЏРЅРІР°СЂСЏ 2025_1 СЃРµРЅС‚СЏР±СЂСЏ 2025")

    def parse_part(part: str) -> datetime:
        match = re.fullmatch(r"(\d{1,2})\s+([Р°-СЏС‘]+)\s+(\d{4})", part)
        if not match:
            raise ValueError("РџРµСЂРёРѕРґ РЅСѓР¶РЅРѕ РІРІРµСЃС‚Рё РІ С„РѕСЂРјР°С‚Рµ: 22 СЏРЅРІР°СЂСЏ 2025_1 СЃРµРЅС‚СЏР±СЂСЏ 2025")
        day = int(match.group(1))
        month_label = match.group(2)
        year = int(match.group(3))
        month = RUSSIAN_MONTHS.get(month_label)
        if month is None:
            raise ValueError(f"РќРµ СѓРґР°Р»РѕСЃСЊ СЂР°СЃРїРѕР·РЅР°С‚СЊ РјРµСЃСЏС† В«{month_label}В».")
        try:
            return datetime(year, month, day, tzinfo=LOCAL_TZ)
        except ValueError as exc:
            raise ValueError("РџСЂРѕРІРµСЂСЊ РєРѕСЂСЂРµРєС‚РЅРѕСЃС‚СЊ РґР°С‚ РІ РїРµСЂРёРѕРґРµ.") from exc

    start_dt = parse_part(parts[0]).replace(hour=0, minute=0, second=0, microsecond=0)
    end_dt = parse_part(parts[1]).replace(hour=23, minute=59, second=59, microsecond=999999)
    if end_dt < start_dt:
        raise ValueError("РљРѕРЅРµС‡РЅР°СЏ РґР°С‚Р° РїРµСЂРёРѕРґР° РЅРµ РјРѕР¶РµС‚ Р±С‹С‚СЊ СЂР°РЅСЊС€Рµ РЅР°С‡Р°Р»СЊРЅРѕР№.")
    return start_dt, end_dt



def build_report_text(start_dt: datetime, end_dt: datetime) -> str:
    archived_orders = load_archived_orders()
    matched_orders: list[dict[str, Any]] = []
    for item in archived_orders:
        created_at = item.get("created_at")
        if not created_at:
            continue
        created_dt = datetime.fromisoformat(created_at).astimezone(LOCAL_TZ)
        if start_dt <= created_dt <= end_dt:
            matched_orders.append(item)

    total_count = len(matched_orders)
    completed_count = sum(1 for item in matched_orders if item.get("lifecycle_state") == "completed")
    deleted_count = sum(1 for item in matched_orders if item.get("lifecycle_state") == "deleted")
    active_count = total_count - completed_count - deleted_count
    total_sum = sum(safe_parse_rubles(item.get("total_price"), default=0) for item in matched_orders)
    total_paid = sum(safe_parse_rubles(item.get("paid_amount"), default=0) for item in matched_orders)
    total_due = max(total_sum - total_paid, 0)
    platform_summary = {platform: 0 for platform in PLATFORM_LABELS}
    for item in matched_orders:
        platform = str(item.get("created_via") or "telegram").lower()
        if platform in platform_summary:
            platform_summary[platform] += 1

    lines = [
        "рџ“Љ РћС‚С‡С‘С‚ РїРѕ Р°СЂС…РёРІСѓ Р·Р°РєР°Р·РѕРІ",
        f"РџРµСЂРёРѕРґ: {start_dt.strftime('%Y-%m-%d')} вЂ” {end_dt.strftime('%Y-%m-%d')}",
        "",
        f"Р’СЃРµРіРѕ Р·Р°РєР°Р·РѕРІ: {total_count}",
        f"РђРєС‚РёРІРЅС‹С…: {active_count}",
        f"Р—Р°РІРµСЂС€С‘РЅРЅС‹С…: {completed_count}",
        f"РЈРґР°Р»С‘РЅРЅС‹С…: {deleted_count}",
        f"РЎСѓРјРјР° Р·Р°РєР°Р·РѕРІ: {format_price(total_sum)}",
        f"РџРѕР»СѓС‡РµРЅРѕ РѕРїР»Р°С‚: {format_price(total_paid)}",
        f"РћСЃС‚Р°Р»РѕСЃСЊ РїРѕР»СѓС‡РёС‚СЊ: {format_price(total_due)}",
        "",
        "РџРѕ РєР°РЅР°Р»Р°Рј СЃРѕР·РґР°РЅРёСЏ:",
        f"вЂў Telegram: {platform_summary['telegram']}",
        f"вЂў MAX: {platform_summary['max']}",
    ]
    return "\n".join(lines)



def start_new_order_flow(platform: str, chat_id: str) -> None:
    clear_conversation(actor_key(platform, chat_id))
    if not catalog_items:
        send_admin_message(
            platform,
            chat_id,
            "рџ“љ РљР°С‚Р°Р»РѕРі РїСѓСЃС‚. РЎРЅР°С‡Р°Р»Р° РґРѕР±Р°РІСЊ С…РѕС‚СЏ Р±С‹ РѕРґРёРЅ С‚РѕРІР°СЂ, Р·Р°С‚РµРј РјРѕР¶РЅРѕ Р±СѓРґРµС‚ СЃРѕР·РґР°С‚СЊ Р·Р°РєР°Р·.",
            inline_keyboard=build_catalog_list_keyboard(),
        )
        return

    set_conversation(actor_key(platform, chat_id), "awaiting_catalog_pick", draft={})
    send_admin_message(
        platform,
        chat_id,
        "Р’С‹Р±РµСЂРё С‚РѕРІР°СЂ РёР· РєР°С‚Р°Р»РѕРіР° РґР»СЏ РЅРѕРІРѕРіРѕ Р·Р°РєР°Р·Р°:",
        inline_keyboard=build_catalog_pick_keyboard(),
    )



def open_catalog(platform: str, chat_id: str) -> None:
    clear_conversation(actor_key(platform, chat_id))
    send_admin_message(
        platform,
        chat_id,
        build_catalog_list_text(),
        inline_keyboard=build_catalog_list_keyboard(),
    )



def handle_command(platform: str, chat_id: str, text: str) -> None:
    stripped = text.strip()
    if not is_admin(platform, chat_id):
        if stripped == "/miniapp":
            if platform == "telegram" and MINI_APP_PUBLIC_URL:
                send_message(
                    platform,
                    chat_id,
                    "Mini App РіРѕС‚РѕРІ. РќР°Р¶РјРёС‚Рµ РєРЅРѕРїРєСѓ РЅРёР¶Рµ, С‡С‚РѕР±С‹ РѕС‚РєСЂС‹С‚СЊ РїСЂРёР»РѕР¶РµРЅРёРµ РІРЅСѓС‚СЂРё Telegram.",
                    reply_markup=build_telegram_mini_app_inline_keyboard(),
                )
                return
            send_message(
                platform,
                chat_id,
                (
                    f"Р›РѕРєР°Р»СЊРЅС‹Р№ Р°РґСЂРµСЃ Mini App: {get_local_mini_app_url()}\n"
                    "Р§С‚РѕР±С‹ Mini App РѕС‚РєСЂС‹РІР°Р»СЃСЏ РїСЂСЏРјРѕ РІРЅСѓС‚СЂРё Telegram, СѓРєР°Р¶РёС‚Рµ РїСѓР±Р»РёС‡РЅС‹Р№ HTTPS URL РІ MINI_APP_PUBLIC_URL."
                ),
            )
            return
        if stripped.startswith("/start"):
            parts = stripped.split(maxsplit=1)
            payload = parts[1].strip() if len(parts) > 1 else ""
            handle_public_start(platform, chat_id, payload)
            return
        send_public_welcome(platform, chat_id)
        return

    if stripped == MENU_LABEL or stripped.startswith("/start"):
        clear_conversation(actor_key(platform, chat_id))
        send_admin_help(platform, chat_id)
        return

    if stripped == "/miniapp":
        if platform == "telegram" and MINI_APP_PUBLIC_URL:
            send_message(
                platform,
                chat_id,
                "Mini App РіРѕС‚РѕРІ. РќР°Р¶РјРёС‚Рµ РєРЅРѕРїРєСѓ РЅРёР¶Рµ, С‡С‚РѕР±С‹ РѕС‚РєСЂС‹С‚СЊ РїСЂРёР»РѕР¶РµРЅРёРµ РІРЅСѓС‚СЂРё Telegram.",
                reply_markup=build_telegram_mini_app_inline_keyboard(),
            )
            return
        send_admin_message(
            platform,
            chat_id,
            (
                f"Р›РѕРєР°Р»СЊРЅС‹Р№ Р°РґСЂРµСЃ Mini App: {get_local_mini_app_url()}\n"
                "Р”Р»СЏ Р·Р°РїСѓСЃРєР° РІРЅСѓС‚СЂРё Telegram РЅСѓР¶РµРЅ РїСѓР±Р»РёС‡РЅС‹Р№ HTTPS URL РІ MINI_APP_PUBLIC_URL."
            ),
            force_new=True,
        )
        return

    if stripped == "/neworder":
        start_new_order_flow(platform, chat_id)
        return

    if stripped == "/orders":
        clear_conversation(actor_key(platform, chat_id))
        send_admin_message(
            platform,
            chat_id,
            build_orders_list_text(),
            inline_keyboard=build_orders_list_keyboard(),
        )
        return

    if stripped == "/catalog":
        open_catalog(platform, chat_id)
        return

    if stripped == "/report":
        set_conversation(actor_key(platform, chat_id), "awaiting_report_period")
        send_admin_message(
            platform,
            chat_id,
            "Р’РІРµРґРё РїРµСЂРёРѕРґ РІ С„РѕСЂРјР°С‚Рµ: 22 СЏРЅРІР°СЂСЏ 2025_1 СЃРµРЅС‚СЏР±СЂСЏ 2025",
            inline_keyboard=build_prompt_keyboard(),
        )
        return

    if stripped == "/cancel":
        clear_conversation(actor_key(platform, chat_id))
        send_admin_message(
            platform,
            chat_id,
            "рџ›‘ РўРµРєСѓС‰РµРµ РґРµР№СЃС‚РІРёРµ РѕС‚РјРµРЅРµРЅРѕ.",
            inline_keyboard=build_admin_home_keyboard(),
        )
        return

    send_admin_message(
        platform,
        chat_id,
        "РќРµРёР·РІРµСЃС‚РЅР°СЏ РєРѕРјР°РЅРґР°. РСЃРїРѕР»СЊР·СѓР№ /neworder, /orders, /catalog, /report РёР»Рё /cancel.",
        inline_keyboard=build_admin_home_keyboard(),
    )



def handle_public_start(platform: str, chat_id: str, payload: str) -> None:
    if not payload.startswith("order_"):
        send_public_welcome(platform, chat_id)
        return

    token = payload.removeprefix("order_").strip()
    order = find_order_by_token(token)
    if not order:
        send_message(
            platform,
            chat_id,
            "Р—Р°РєР°Р· РїРѕ СЌС‚РѕР№ СЃСЃС‹Р»РєРµ РЅРµ РЅР°Р№РґРµРЅ РёР»Рё СѓР¶Рµ СѓРґР°Р»С‘РЅ. РќР°РїРёС€РёС‚Рµ РЅР°Рј, Рё РјС‹ РїРѕРјРѕР¶РµРј СѓС‚РѕС‡РЅРёС‚СЊ РёРЅС„РѕСЂРјР°С†РёСЋ.",
            reply_markup=build_public_keyboard(platform, chat_id),
        )
        return

    if link_customer_to_order(order, platform, chat_id):
        append_history(order, f"РљР»РёРµРЅС‚ РѕС‚РєСЂС‹Р» РїРµСЂСЃРѕРЅР°Р»СЊРЅСѓСЋ СЃСЃС‹Р»РєСѓ РІ {get_platform_label(platform)} РёР· С‡Р°С‚Р° {chat_id}.")
        persist_order(order, "completed" if order["status"] == "completed" else "active")

    send_order_snapshot(platform, chat_id, order)



def handle_text_message(platform: str, chat_id: str, text: str, message_id: str | None = None) -> None:
    if text.startswith("/"):
        handle_command(platform, chat_id, text)
        return

    if not is_admin(platform, chat_id):
        send_public_welcome(platform, chat_id)
        return

    state_for_chat = conversation_state.get(actor_key(platform, chat_id))
    if not state_for_chat:
        send_admin_message(
            platform,
            chat_id,
            "РСЃРїРѕР»СЊР·СѓР№ /neworder, С‡С‚РѕР±С‹ СЃРѕР·РґР°С‚СЊ Р·Р°РєР°Р·, /orders вЂ” С‡С‚РѕР±С‹ РїРѕСЃРјРѕС‚СЂРµС‚СЊ СЃРїРёСЃРѕРє, РёР»Рё /catalog вЂ” С‡С‚РѕР±С‹ РѕС‚РєСЂС‹С‚СЊ РєР°С‚Р°Р»РѕРі.",
            inline_keyboard=build_admin_home_keyboard(),
        )
        return

    step = state_for_chat.get("step")
    cleaned_text = text.strip()

    if step == "awaiting_catalog_title":
        if not cleaned_text:
            send_admin_message(platform, chat_id, "РќР°РёРјРµРЅРѕРІР°РЅРёРµ С‚РѕРІР°СЂР° РЅРµ РјРѕР¶РµС‚ Р±С‹С‚СЊ РїСѓСЃС‚С‹Рј.")
            return
        if len(cleaned_text) > MAX_TITLE_LENGTH:
            send_admin_message(platform, chat_id, f"РќР°РёРјРµРЅРѕРІР°РЅРёРµ СЃР»РёС€РєРѕРј РґР»РёРЅРЅРѕРµ. Р›РёРјРёС‚ вЂ” {MAX_TITLE_LENGTH} СЃРёРјРІРѕР»РѕРІ.")
            return
        set_conversation(actor_key(platform, chat_id), "awaiting_catalog_price", draft={"title": cleaned_text})
        send_admin_message(
            platform,
            chat_id,
            "РўРµРїРµСЂСЊ РІРІРµРґРё С†РµРЅСѓ С‚РѕРІР°СЂР°, РЅР°РїСЂРёРјРµСЂ: 42000",
            inline_keyboard=build_prompt_keyboard(),
        )
        return

    if step == "awaiting_catalog_price":
        if not cleaned_text:
            send_admin_message(platform, chat_id, "Р¦РµРЅР° РЅРµ РјРѕР¶РµС‚ Р±С‹С‚СЊ РїСѓСЃС‚РѕР№.")
            return
        if len(cleaned_text) > MAX_PRICE_LENGTH:
            send_admin_message(platform, chat_id, f"Р¦РµРЅР° СЃР»РёС€РєРѕРј РґР»РёРЅРЅР°СЏ. Р›РёРјРёС‚ вЂ” {MAX_PRICE_LENGTH} СЃРёРјРІРѕР»РѕРІ.")
            return
        try:
            total_price = parse_rubles(cleaned_text)
        except ValueError as exc:
            send_admin_message(platform, chat_id, f"вљ пёЏ {exc}")
            return
        draft = dict(state_for_chat["draft"])
        item = create_catalog_item(draft["title"], total_price)
        clear_conversation(actor_key(platform, chat_id))
        send_admin_message(
            platform,
            chat_id,
            f"вњ… РўРѕРІР°СЂ РґРѕР±Р°РІР»РµРЅ РІ РєР°С‚Р°Р»РѕРі.\n\n#{item['id']} вЂў {item['title']}\nР¦РµРЅР°: {format_price(item['total_price'])}",
            inline_keyboard=build_catalog_list_keyboard(),
        )
        return

    if step == "awaiting_notes":
        notes = "" if cleaned_text == "-" else cleaned_text
        if len(notes) > MAX_NOTES_LENGTH:
            send_admin_message(platform, chat_id, f"РџСЂРёРјРµС‡Р°РЅРёРµ СЃР»РёС€РєРѕРј РґР»РёРЅРЅРѕРµ. Р›РёРјРёС‚ вЂ” {MAX_NOTES_LENGTH} СЃРёРјРІРѕР»РѕРІ.")
            return
        draft = dict(state_for_chat["draft"])
        draft["notes"] = notes
        order = create_order(
            title=draft["title"],
            total_price=draft["total_price"],
            paid_amount=draft["paid_amount"],
            has_delivery=draft["has_delivery"],
            notes=draft["notes"],
            created_via=platform,
        )
        clear_conversation(actor_key(platform, chat_id))
        send_admin_message(
            platform,
            chat_id,
            format_admin_order_text(order),
            inline_keyboard=build_admin_order_keyboard(order),
        )
        send_message(
            platform,
            chat_id,
            render_client_share_html(order),
            parse_mode="HTML",
        )
        resend_admin_message_at_bottom(
            platform,
            chat_id,
            format_admin_order_text(order),
            inline_keyboard=build_admin_order_keyboard(order),
        )
        return

    if step == "awaiting_payment_add":
        order = find_order_by_id(int(state_for_chat["order_id"]))
        if not order:
            clear_conversation(actor_key(platform, chat_id))
            send_admin_message(platform, chat_id, "Р—Р°РєР°Р· РЅРµ РЅР°Р№РґРµРЅ.", inline_keyboard=build_orders_list_keyboard())
            return
        try:
            amount = parse_paid_amount(cleaned_text)
        except ValueError as exc:
            send_admin_message(platform, chat_id, f"вљ пёЏ {exc}")
            return
        add_payment(order, amount)
        clear_conversation(actor_key(platform, chat_id))
        notify_customer_order_update(order, f"РџРѕ Р·Р°РєР°Р·Сѓ #{order['id']} РѕС‚РјРµС‡РµРЅР° РЅРѕРІР°СЏ РѕРїР»Р°С‚Р°: {format_price(amount)}.")
        send_admin_message(
            platform,
            chat_id,
            f"вњ… РћРїР»Р°С‚Р° РѕР±РЅРѕРІР»РµРЅР°.\n\n{format_admin_order_text(order)}",
            inline_keyboard=build_admin_order_keyboard(order),
        )
        return

    if step == "awaiting_delivery_schedule":
        order = find_order_by_id(int(state_for_chat["order_id"]))
        if not order:
            clear_conversation(actor_key(platform, chat_id))
            send_admin_message(platform, chat_id, "Р—Р°РєР°Р· РЅРµ РЅР°Р№РґРµРЅ.", inline_keyboard=build_orders_list_keyboard())
            return
        if not cleaned_text:
            send_admin_message(
                platform,
                chat_id,
                "РЈРєР°Р¶Рё РґР°С‚Сѓ Рё РІСЂРµРјСЏ РґРѕСЃС‚Р°РІРєРё, РЅР°РїСЂРёРјРµСЂ: 20 СЏРЅРІР°СЂСЏ, 20:00",
                inline_keyboard=build_prompt_keyboard(),
            )
            return
        set_delivery_schedule(order, cleaned_text)
        clear_conversation(actor_key(platform, chat_id))
        notify_customer_order_update(order, f"РџРѕ Р·Р°РєР°Р·Сѓ #{order['id']} РѕР±РЅРѕРІР»С‘РЅ СЃС‚Р°С‚СѓСЃ: РћР¶РёРґР°РЅРёРµ РґРѕСЃС‚Р°РІРєРё.")
        send_admin_message(
            platform,
            chat_id,
            f"вњ… Р”РѕСЃС‚Р°РІРєР° Р·Р°РїР»Р°РЅРёСЂРѕРІР°РЅР°.\n\n{format_admin_order_text(order)}",
            inline_keyboard=build_admin_order_keyboard(order),
        )
        return

    if step == "awaiting_report_period":
        try:
            start_dt, end_dt = parse_russian_period(cleaned_text)
        except ValueError as exc:
            send_admin_message(platform, chat_id, f"вљ пёЏ {exc}")
            return
        clear_conversation(actor_key(platform, chat_id))
        send_admin_message(
            platform,
            chat_id,
            build_report_text(start_dt, end_dt),
            inline_keyboard=build_admin_home_keyboard(),
        )
        return

    send_admin_message(
        platform,
        chat_id,
        "РСЃРїРѕР»СЊР·СѓР№ /cancel Рё РЅР°С‡РЅРё Р·Р°РЅРѕРІРѕ С‡РµСЂРµР· /neworder.",
        inline_keyboard=build_admin_home_keyboard(),
    )



def notify_customer_order_completed(order: dict[str, Any]) -> None:
    for binding in get_order_bindings(order):
        send_message(
            binding["platform"],
            binding["chat_id"],
            (
                "РЎРїР°СЃРёР±Рѕ Р·Р° РІР°С€ Р·Р°РєР°Р· РІ РљСѓР»СЊС‚ РњРµР±РµР»СЊ! вќ¤пёЏ\n\n"
                f"{order['title']} РѕС‚РјРµС‡РµРЅ РєР°Рє Р·Р°РІРµСЂС€С‘РЅРЅС‹Р№. Р•СЃР»Рё РїРѕРЅР°РґРѕР±РёС‚СЃСЏ РїРѕРјРѕС‰СЊ, РјС‹ РІСЃРµРіРґР° РЅР° СЃРІСЏР·Рё."
            ),
            reply_markup=build_public_keyboard(binding["platform"], binding["chat_id"], order["token"]),
        )



def safe_edit_or_send(platform: str, chat_id: str, message_id: str, text: str, reply_markup: dict[str, Any] | None = None) -> None:
    try:
        edit_message(platform, chat_id, message_id, text, reply_markup=reply_markup)
        set_ui_message(actor_key(platform, chat_id), message_id)
    except RuntimeError as exc:
        if platform == "telegram" and "message is not modified" in str(exc).lower():
            set_ui_message(actor_key(platform, chat_id), message_id)
            return
        result = send_message(platform, chat_id, text, reply_markup=reply_markup)
        new_message_id = extract_message_id(platform, result)
        if new_message_id is not None:
            set_ui_message(actor_key(platform, chat_id), new_message_id)
    except requests.exceptions.RequestException:
        result = send_message(platform, chat_id, text, reply_markup=reply_markup)
        new_message_id = extract_message_id(platform, result)
        if new_message_id is not None:
            set_ui_message(actor_key(platform, chat_id), new_message_id)



def safe_answer_callback_query(platform: str, callback_query_id: str) -> None:
    try:
        answer_callback_query(platform, callback_query_id)
    except (RuntimeError, requests.exceptions.RequestException):
        return



def handle_callback_action(platform: str, chat_id: str, message_id: str, data: str, callback_id: str | None = None) -> None:
    chat_id_str = str(chat_id)
    if callback_id:
        safe_answer_callback_query(platform, callback_id)

    if data == "public:socials":
        safe_edit_or_send(platform, chat_id_str, message_id, "РЎРѕС†СЃРµС‚Рё РљСѓР»СЊС‚ РњРµР±РµР»СЊ:", build_socials_keyboard())
        return

    if data == "client:list":
        safe_edit_or_send(
            platform,
            chat_id_str,
            message_id,
            build_customer_orders_text(platform, chat_id_str),
            build_customer_orders_keyboard(platform, chat_id_str),
        )
        return

    if data.startswith("client:view:"):
        token = data.split(":", maxsplit=2)[2]
        order = find_order_by_token(token)
        if not order or not find_binding(order, platform, chat_id_str):
            safe_edit_or_send(
                platform,
                chat_id_str,
                message_id,
                "РќРµ СѓРґР°Р»РѕСЃСЊ РѕС‚РєСЂС‹С‚СЊ Р·Р°РєР°Р·. Р•СЃР»Рё РЅСѓР¶РЅР° РїРѕРјРѕС‰СЊ вЂ” РЅР°РїРёС€РёС‚Рµ РЅР°Рј.",
                build_public_keyboard(platform, chat_id_str),
            )
            return
        safe_edit_or_send(
            platform,
            chat_id_str,
            message_id,
            render_order_text(order, for_admin=False),
            build_public_keyboard(platform, chat_id_str, order["token"]),
        )
        return

    if data.startswith("client:refresh:"):
        token = data.split(":", maxsplit=2)[2]
        order = find_order_by_token(token)
        if not order or not find_binding(order, platform, chat_id_str):
            safe_edit_or_send(
                platform,
                chat_id_str,
                message_id,
                "Р—Р°РєР°Р· Р±РѕР»СЊС€Рµ РЅРµРґРѕСЃС‚СѓРїРµРЅ. РќР°РїРёС€РёС‚Рµ РЅР°Рј, Рё РјС‹ РїРѕРјРѕР¶РµРј СѓС‚РѕС‡РЅРёС‚СЊ РёРЅС„РѕСЂРјР°С†РёСЋ.",
                build_public_keyboard(platform, chat_id_str),
            )
            return
        safe_edit_or_send(
            platform,
            chat_id_str,
            message_id,
            render_order_text(order, for_admin=False),
            build_public_keyboard(platform, chat_id_str, order["token"]),
        )
        return

    if not is_admin(platform, chat_id_str):
        send_public_welcome(platform, chat_id_str)
        return

    set_ui_message(actor_key(platform, chat_id_str), message_id)

    if data == "adminmenu:home":
        clear_conversation(actor_key(platform, chat_id_str))
        send_admin_help(platform, chat_id_str)
        return

    if data == "adminmenu:neworder":
        start_new_order_flow(platform, chat_id_str)
        return

    if data == "adminmenu:report":
        set_conversation(actor_key(platform, chat_id_str), "awaiting_report_period")
        send_admin_message(
            platform,
            chat_id_str,
            "Р’РІРµРґРё РїРµСЂРёРѕРґ РІ С„РѕСЂРјР°С‚Рµ: 22 СЏРЅРІР°СЂСЏ 2025_1 СЃРµРЅС‚СЏР±СЂСЏ 2025",
            inline_keyboard=build_prompt_keyboard(),
        )
        return

    if data == "flow:cancel":
        clear_conversation(actor_key(platform, chat_id_str))
        send_admin_message(
            platform,
            chat_id_str,
            "рџ›‘ РўРµРєСѓС‰РµРµ РґРµР№СЃС‚РІРёРµ РѕС‚РјРµРЅРµРЅРѕ.",
            inline_keyboard=build_admin_home_keyboard(),
        )
        return

    if data == "catalog:list":
        open_catalog(platform, chat_id_str)
        return

    if data == "catalog:add":
        set_conversation(actor_key(platform, chat_id_str), "awaiting_catalog_title")
        send_admin_message(
            platform,
            chat_id_str,
            "Р’РІРµРґРё РЅР°Р·РІР°РЅРёРµ С‚РѕРІР°СЂР° РґР»СЏ РєР°С‚Р°Р»РѕРіР°, РЅР°РїСЂРёРјРµСЂ: РљСЂРѕРІР°С‚СЊ 160С…200",
            inline_keyboard=build_prompt_keyboard(),
        )
        return

    if data.startswith("catalog:view:"):
        item_id = int(data.split(":", maxsplit=2)[2])
        item = find_catalog_item_by_id(item_id)
        if not item:
            send_admin_message(platform, chat_id_str, "РўРѕРІР°СЂ РЅРµ РЅР°Р№РґРµРЅ.", inline_keyboard=build_catalog_list_keyboard())
            return
        send_admin_message(
            platform,
            chat_id_str,
            f"рџ“¦ РўРѕРІР°СЂ #{item['id']}\n{item['title']}\n\nР¦РµРЅР°: {format_price(item['total_price'])}",
            inline_keyboard=build_catalog_item_keyboard(item_id),
        )
        return

    if data.startswith("catalog:delete:"):
        item_id = int(data.split(":", maxsplit=2)[2])
        deleted = delete_catalog_item(item_id)
        if not deleted:
            send_admin_message(platform, chat_id_str, "РўРѕРІР°СЂ РЅРµ РЅР°Р№РґРµРЅ.", inline_keyboard=build_catalog_list_keyboard())
            return
        send_admin_message(
            platform,
            chat_id_str,
            "рџ—‘ РўРѕРІР°СЂ СѓРґР°Р»С‘РЅ РёР· РєР°С‚Р°Р»РѕРіР°.",
            inline_keyboard=build_catalog_list_keyboard(),
        )
        return

    if data.startswith("create:item:"):
        item_id = int(data.split(":", maxsplit=2)[2])
        item = find_catalog_item_by_id(item_id)
        if not item:
            send_admin_message(platform, chat_id_str, "РўРѕРІР°СЂ РЅРµ РЅР°Р№РґРµРЅ.", inline_keyboard=build_catalog_pick_keyboard())
            return
        draft = {
            "catalog_item_id": item["id"],
            "title": item["title"],
            "total_price": item["total_price"],
        }
        set_conversation(actor_key(platform, chat_id_str), "awaiting_payment_choice", draft=draft)
        send_admin_message(
            platform,
            chat_id_str,
            f"РўРѕРІР°СЂ РІС‹Р±СЂР°РЅ:\n{item['title']}\nР¦РµРЅР°: {format_price(item['total_price'])}\n\nР’С‹Р±РµСЂРё, СЃРєРѕР»СЊРєРѕ СѓР¶Рµ РѕРїР»Р°С‡РµРЅРѕ:",
            inline_keyboard={
                "inline_keyboard": build_payment_choice_keyboard()["inline_keyboard"] + build_cancel_keyboard()["inline_keyboard"]
            },
        )
        return

    if data.startswith("create:payment:"):
        percent_key = data.split(":", maxsplit=2)[2]
        percent = PAYMENT_OPTIONS.get(percent_key)
        state_for_chat = conversation_state.get(actor_key(platform, chat_id_str))
        if percent is None or not state_for_chat:
            send_admin_message(platform, chat_id_str, "РќРµ СѓРґР°Р»РѕСЃСЊ РІС‹Р±СЂР°С‚СЊ РѕРїР»Р°С‚Сѓ. РќР°С‡РЅРё СЃРѕР·РґР°РЅРёРµ Р·Р°РєР°Р·Р° Р·Р°РЅРѕРІРѕ.")
            return
        draft = dict(state_for_chat.get("draft", {}))
        draft["paid_amount"] = round(draft["total_price"] * percent / 100)
        set_conversation(actor_key(platform, chat_id_str), "awaiting_delivery_choice", draft=draft)
        send_admin_message(
            platform,
            chat_id_str,
            (
                f"{draft['title']}\n"
                f"Р¦РµРЅР°: {format_price(draft['total_price'])}\n"
                f"РћРїР»Р°С‡РµРЅРѕ: {percent}% ({format_price(draft['paid_amount'])} РёР· {format_price(draft['total_price'])})\n\n"
                "РќСѓР¶РЅР° РґРѕСЃС‚Р°РІРєР°?"
            ),
            inline_keyboard={
                "inline_keyboard": build_delivery_choice_keyboard()["inline_keyboard"] + build_cancel_keyboard()["inline_keyboard"]
            },
        )
        return

    if data.startswith("create:delivery:"):
        state_for_chat = conversation_state.get(actor_key(platform, chat_id_str))
        if not state_for_chat:
            send_admin_message(platform, chat_id_str, "РќРµ СѓРґР°Р»РѕСЃСЊ РІС‹Р±СЂР°С‚СЊ РґРѕСЃС‚Р°РІРєСѓ. РќР°С‡РЅРё СЃРѕР·РґР°РЅРёРµ Р·Р°РєР°Р·Р° Р·Р°РЅРѕРІРѕ.")
            return
        draft = dict(state_for_chat.get("draft", {}))
        draft["has_delivery"] = data.endswith(":yes")
        set_conversation(actor_key(platform, chat_id_str), "awaiting_notes", draft=draft)
        send_admin_message(
            platform,
            chat_id_str,
            (
                f"{draft['title']}\n"
                f"Р¦РµРЅР°: {format_price(draft['total_price'])}\n"
                f"РћРїР»Р°С‡РµРЅРѕ: {get_paid_text({'paid_amount': draft['paid_amount'], 'total_price': draft['total_price']})}\n"
                f"Р”РѕСЃС‚Р°РІРєР°: {'Р”Р°' if draft['has_delivery'] else 'РќРµС‚'}\n\n"
                "РўРµРїРµСЂСЊ РѕС‚РїСЂР°РІСЊ РїСЂРёРјРµС‡Р°РЅРёРµ. Р•СЃР»Рё РїСЂРёРјРµС‡Р°РЅРёСЏ РЅРµС‚ вЂ” РѕС‚РїСЂР°РІСЊ РѕРґРёРЅРѕС‡РЅС‹Р№ СЃРёРјРІРѕР» -"
            ),
            inline_keyboard=build_prompt_keyboard(),
        )
        return

    if data == "admin:list":
        send_admin_message(platform, chat_id_str, build_orders_list_text(), inline_keyboard=build_orders_list_keyboard())
        return

    if data.startswith("admin:view:"):
        order_id = int(data.split(":", maxsplit=2)[2])
        order = find_order_by_id(order_id)
        if not order:
            send_admin_message(platform, chat_id_str, "Р—Р°РєР°Р· РЅРµ РЅР°Р№РґРµРЅ РёР»Рё СѓР¶Рµ СѓРґР°Р»С‘РЅ.", inline_keyboard=build_orders_list_keyboard())
            return
        send_admin_message(
            platform,
            chat_id_str,
            format_admin_order_text(order),
            inline_keyboard=build_admin_order_keyboard(order),
        )
        return

    if data.startswith("admin:status:"):
        _, _, order_id_str, status_key = data.split(":", maxsplit=3)
        order = find_order_by_id(int(order_id_str))
        if not order:
            send_admin_message(platform, chat_id_str, "Р—Р°РєР°Р· РЅРµ РЅР°Р№РґРµРЅ РёР»Рё СѓР¶Рµ СѓРґР°Р»С‘РЅ.", inline_keyboard=build_orders_list_keyboard())
            return
        allowed_statuses = get_status_keys(order["has_delivery"])
        if status_key not in allowed_statuses:
            send_admin_message(platform, chat_id_str, "Р­С‚РѕС‚ СЃС‚Р°С‚СѓСЃ РЅРµРґРѕСЃС‚СѓРїРµРЅ РґР»СЏ РІС‹Р±СЂР°РЅРЅРѕРіРѕ Р·Р°РєР°Р·Р°.")
            return
        if status_key == "awaiting_delivery":
            set_conversation(actor_key(platform, chat_id_str), "awaiting_delivery_schedule", order_id=order["id"])
            send_admin_message(
                platform,
                chat_id_str,
                "РЈРєР°Р¶Рё РґР°С‚Сѓ Рё РІСЂРµРјСЏ РґРѕСЃС‚Р°РІРєРё, РЅР°РїСЂРёРјРµСЂ: 20 СЏРЅРІР°СЂСЏ, 20:00",
                inline_keyboard=build_prompt_keyboard(),
            )
            return
        update_order_status(order, status_key)
        notify_customer_order_update(order, f"РџРѕ Р·Р°РєР°Р·Сѓ #{order['id']} РѕР±РЅРѕРІР»С‘РЅ СЃС‚Р°С‚СѓСЃ: {get_status_label(status_key)}.")
        send_admin_message(
            platform,
            chat_id_str,
            format_admin_order_text(order),
            inline_keyboard=build_admin_order_keyboard(order),
        )
        return

    if data.startswith("admin:delivery_toggle:"):
        order_id = int(data.split(":", maxsplit=2)[2])
        order = find_order_by_id(order_id)
        if not order:
            send_admin_message(platform, chat_id_str, "Р—Р°РєР°Р· РЅРµ РЅР°Р№РґРµРЅ РёР»Рё СѓР¶Рµ СѓРґР°Р»С‘РЅ.", inline_keyboard=build_orders_list_keyboard())
            return
        update_delivery_flag(order, not order["has_delivery"])
        notify_customer_order_update(
            order,
            f"РџРѕ Р·Р°РєР°Р·Сѓ #{order['id']} РёР·РјРµРЅС‘РЅ СЃРїРѕСЃРѕР± РїРѕР»СѓС‡РµРЅРёСЏ: {'РґРѕСЃС‚Р°РІРєР°' if order['has_delivery'] else 'СЃР°РјРѕРІС‹РІРѕР·'}.",
        )
        send_admin_message(
            platform,
            chat_id_str,
            format_admin_order_text(order),
            inline_keyboard=build_admin_order_keyboard(order),
        )
        return

    if data.startswith("admin:payment_full:"):
        order_id = int(data.split(":", maxsplit=2)[2])
        order = find_order_by_id(order_id)
        if not order:
            send_admin_message(platform, chat_id_str, "Р—Р°РєР°Р· РЅРµ РЅР°Р№РґРµРЅ РёР»Рё СѓР¶Рµ СѓРґР°Р»С‘РЅ.", inline_keyboard=build_orders_list_keyboard())
            return
        mark_fully_paid(order)
        notify_customer_order_update(order, f"РџРѕ Р·Р°РєР°Р·Сѓ #{order['id']} РѕС‚РјРµС‡РµРЅР° РїРѕР»РЅР°СЏ РѕРїР»Р°С‚Р°.")
        send_admin_message(
            platform,
            chat_id_str,
            format_admin_order_text(order),
            inline_keyboard=build_admin_order_keyboard(order),
        )
        return

    if data.startswith("admin:payment_add:"):
        order_id = int(data.split(":", maxsplit=2)[2])
        order = find_order_by_id(order_id)
        if not order:
            send_admin_message(platform, chat_id_str, "Р—Р°РєР°Р· РЅРµ РЅР°Р№РґРµРЅ РёР»Рё СѓР¶Рµ СѓРґР°Р»С‘РЅ.", inline_keyboard=build_orders_list_keyboard())
            return
        set_conversation(actor_key(platform, chat_id_str), "awaiting_payment_add", order_id=order_id)
        send_admin_message(
            platform,
            chat_id_str,
            "Р’РІРµРґРё СЃСѓРјРјСѓ РґРѕРїР»Р°С‚С‹ РІ СЂСѓР±Р»СЏС…, РЅР°РїСЂРёРјРµСЂ: 5000",
            inline_keyboard=build_prompt_keyboard(),
        )
        return

    if data.startswith("admin:finish:"):
        order_id = int(data.split(":", maxsplit=2)[2])
        order = find_order_by_id(order_id)
        if not order:
            send_admin_message(platform, chat_id_str, "Р—Р°РєР°Р· РЅРµ РЅР°Р№РґРµРЅ РёР»Рё СѓР¶Рµ СѓРґР°Р»С‘РЅ.", inline_keyboard=build_orders_list_keyboard())
            return
        send_admin_message(
            platform,
            chat_id_str,
            f"Р—Р°РІРµСЂС€РёС‚СЊ Р·Р°РєР°Р· #{order['id']}?\nРџРѕСЃР»Рµ РїРѕРґС‚РІРµСЂР¶РґРµРЅРёСЏ РєР»РёРµРЅС‚ РїРѕР»СѓС‡РёС‚ СЃРѕРѕР±С‰РµРЅРёРµ СЃ Р±Р»Р°РіРѕРґР°СЂРЅРѕСЃС‚СЊСЋ.",
            inline_keyboard=build_finish_confirmation_keyboard(order_id),
        )
        return

    if data.startswith("admin:finish_yes:"):
        order_id = int(data.split(":", maxsplit=2)[2])
        order = find_order_by_id(order_id)
        if not order:
            send_admin_message(platform, chat_id_str, "Р—Р°РєР°Р· РЅРµ РЅР°Р№РґРµРЅ РёР»Рё СѓР¶Рµ СѓРґР°Р»С‘РЅ.", inline_keyboard=build_orders_list_keyboard())
            return
        complete_order(order)
        notify_customer_order_completed(order)
        send_admin_message(
            platform,
            chat_id_str,
            f"вњ… Р—Р°РєР°Р· #{order['id']} Р·Р°РІРµСЂС€С‘РЅ.",
            inline_keyboard={"inline_keyboard": [[{"text": "Рљ СЃРїРёСЃРєСѓ Р·Р°РєР°Р·РѕРІ", "callback_data": "admin:list"}]]},
        )
        return

    if data.startswith("admin:finish_no:"):
        order_id = int(data.split(":", maxsplit=2)[2])
        order = find_order_by_id(order_id)
        if not order:
            send_admin_message(platform, chat_id_str, "Р—Р°РєР°Р· РЅРµ РЅР°Р№РґРµРЅ РёР»Рё СѓР¶Рµ СѓРґР°Р»С‘РЅ.", inline_keyboard=build_orders_list_keyboard())
            return
        send_admin_message(
            platform,
            chat_id_str,
            format_admin_order_text(order),
            inline_keyboard=build_admin_order_keyboard(order),
        )
        return

    if data.startswith("admin:delete:"):
        order_id = int(data.split(":", maxsplit=2)[2])
        order = find_order_by_id(order_id)
        if not order:
            send_admin_message(platform, chat_id_str, "Р—Р°РєР°Р· РЅРµ РЅР°Р№РґРµРЅ РёР»Рё СѓР¶Рµ СѓРґР°Р»С‘РЅ.", inline_keyboard=build_orders_list_keyboard())
            return
        send_admin_message(
            platform,
            chat_id_str,
            f"РЈРґР°Р»РёС‚СЊ Р·Р°РєР°Р· #{order['id']} Р±РµР· РІРѕР·РјРѕР¶РЅРѕСЃС‚Рё РІРѕСЃСЃС‚Р°РЅРѕРІР»РµРЅРёСЏ?",
            inline_keyboard=build_delete_confirmation_keyboard(order_id),
        )
        return

    if data.startswith("admin:delete_yes:"):
        order_id = int(data.split(":", maxsplit=2)[2])
        order = find_order_by_id(order_id)
        if order:
            for binding in get_order_bindings(order):
                send_message(
                    binding["platform"],
                    binding["chat_id"],
                    (
                        f"Р—Р°РєР°Р· #{order['id']} СѓРґР°Р»С‘РЅ РёР· СЃРёСЃС‚РµРјС‹ РѕС‚СЃР»РµР¶РёРІР°РЅРёСЏ.\n"
                        "Р•СЃР»Рё РІС‹ СЃС‡РёС‚Р°РµС‚Рµ, С‡С‚Рѕ СЌС‚Рѕ РїСЂРѕРёР·РѕС€Р»Рѕ Р±РµР· РІР°С€РµРіРѕ СѓРІРµРґРѕРјР»РµРЅРёСЏ, РЅР°РїРёС€РёС‚Рµ РЅР°Рј РїРѕ РєРЅРѕРїРєРµ РЅРёР¶Рµ."
                    ),
                    reply_markup=build_public_keyboard(binding["platform"], binding["chat_id"]),
                )
        deleted = delete_order(order_id)
        if not deleted:
            send_admin_message(platform, chat_id_str, "Р—Р°РєР°Р· РЅРµ РЅР°Р№РґРµРЅ РёР»Рё СѓР¶Рµ СѓРґР°Р»С‘РЅ.", inline_keyboard=build_orders_list_keyboard())
            return
        send_admin_message(
            platform,
            chat_id_str,
            f"рџ—‘ Р—Р°РєР°Р· #{order_id} СѓРґР°Р»С‘РЅ.",
            inline_keyboard={"inline_keyboard": [[{"text": "Рљ СЃРїРёСЃРєСѓ Р·Р°РєР°Р·РѕРІ", "callback_data": "admin:list"}]]},
        )
        return

    if data.startswith("admin:delete_no:"):
        order_id = int(data.split(":", maxsplit=2)[2])
        order = find_order_by_id(order_id)
        if not order:
            send_admin_message(platform, chat_id_str, "Р—Р°РєР°Р· РЅРµ РЅР°Р№РґРµРЅ РёР»Рё СѓР¶Рµ СѓРґР°Р»С‘РЅ.", inline_keyboard=build_orders_list_keyboard())
            return
        send_admin_message(
            platform,
            chat_id_str,
            format_admin_order_text(order),
            inline_keyboard=build_admin_order_keyboard(order),
        )
        return



def extract_message_text(platform: str, payload: dict[str, Any]) -> str | None:
    if platform == "telegram":
        text = payload.get("text")
        return str(text) if isinstance(text, str) else None
    body = payload.get("body") if isinstance(payload, dict) else None
    text = body.get("text") if isinstance(body, dict) else None
    return str(text) if isinstance(text, str) else None



def extract_message_id(platform: str, payload: dict[str, Any]) -> str | None:
    if payload is None:
        return None
    if platform == "telegram":
        value = payload.get("message_id")
        return str(value) if value is not None else None
    body = payload.get("body") if isinstance(payload, dict) else None
    if isinstance(body, dict) and body.get("mid") is not None:
        return str(body.get("mid"))
    if payload.get("message_id") is not None:
        return str(payload.get("message_id"))
    return None



def extract_max_message_peer_id(message: dict[str, Any]) -> str | None:
    recipient = message.get("recipient") if isinstance(message, dict) else None
    if isinstance(recipient, dict):
        if recipient.get("chat_id") is not None:
            return f"chat:{recipient['chat_id']}"
        if recipient.get("user_id") is not None:
            return f"user:{recipient['user_id']}"
        chat = recipient.get("chat")
        if isinstance(chat, dict) and chat.get("chat_id") is not None:
            return f"chat:{chat['chat_id']}"
        user = recipient.get("user")
        if isinstance(user, dict) and user.get("user_id") is not None:
            return f"user:{user['user_id']}"
    sender = message.get("sender") if isinstance(message, dict) else None
    if isinstance(sender, dict) and sender.get("user_id") is not None:
        return f"user:{sender['user_id']}"
    return None


def extract_max_chat_id_from_message(message: dict[str, Any]) -> str | None:
    sender = message.get("sender") if isinstance(message, dict) else None
    if isinstance(sender, dict) and sender.get("user_id") is not None:
        return f"user:{sender['user_id']}"
    return extract_max_message_peer_id(message)


def extract_max_admin_identity_candidates(update: dict[str, Any]) -> set[str]:
    candidates: set[str] = set()
    raw_update_chat_id = update.get("chat_id")
    if raw_update_chat_id not in {None, ""}:
        raw_value = str(raw_update_chat_id).strip()
        candidates.add(raw_value)
        candidates.add(f"chat:{raw_value}")
        candidates.add(f"user:{raw_value}")

    message = update.get("message") if isinstance(update, dict) else None
    if isinstance(message, dict):
        sender = message.get("sender")
        if isinstance(sender, dict) and sender.get("user_id") is not None:
            candidates.add(str(sender["user_id"]))
            candidates.add(f"user:{sender['user_id']}")
        recipient = message.get("recipient")
        if isinstance(recipient, dict):
            if recipient.get("chat_id") is not None:
                candidates.add(str(recipient["chat_id"]))
                candidates.add(f"chat:{recipient['chat_id']}")
            if recipient.get("user_id") is not None:
                candidates.add(str(recipient["user_id"]))
                candidates.add(f"user:{recipient['user_id']}")
            chat = recipient.get("chat")
            if isinstance(chat, dict) and chat.get("chat_id") is not None:
                candidates.add(str(chat["chat_id"]))
                candidates.add(f"chat:{chat['chat_id']}")
            user = recipient.get("user")
            if isinstance(user, dict) and user.get("user_id") is not None:
                candidates.add(str(user["user_id"]))
                candidates.add(f"user:{user['user_id']}")
    return {item for item in candidates if item}


def log_max_admin_candidates(update: dict[str, Any]) -> None:
    candidates = sorted(extract_max_admin_identity_candidates(update))
    if not candidates:
        return
    cache_key = tuple(candidates)
    if cache_key in logged_max_admin_candidates:
        return
    logged_max_admin_candidates.add(cache_key)
    console_print("рџ†” MAX admin ID candidates detected:")
    console_print(f"   candidates: {', '.join(candidates)}")
    console_print(f"   current MAX_ADMIN_CHAT_ID: {MAX_ADMIN_CHAT_ID}")
    console_print("   в†‘ Р’РѕР·СЊРјРё РЅСѓР¶РЅС‹Р№ ID РёР· candidates Рё СѓРєР°Р¶Рё РµРіРѕ РІ .env РєР°Рє MAX_ADMIN_CHAT_ID")


def extract_matching_max_admin_actor_id(update: dict[str, Any]) -> str | None:
    matching_candidates = [
        candidate
        for candidate in sorted(extract_max_admin_identity_candidates(update))
        if is_max_admin_identity(candidate)
    ]
    if not matching_candidates:
        return None
    for prefix in ("user:", "chat:"):
        prefixed_match = next((item for item in matching_candidates if item.startswith(prefix)), None)
        if prefixed_match:
            return prefixed_match
    return matching_candidates[0]



def handle_telegram_update(update: dict[str, Any]) -> None:
    callback_query = update.get("callback_query")
    if callback_query:
        message = callback_query.get("message", {})
        chat = message.get("chat", {})
        chat_id = chat.get("id")
        message_id = message.get("message_id")
        if chat_id is None or message_id is None:
            return
        handle_callback_action(
            "telegram",
            str(chat_id),
            str(message_id),
            str(callback_query.get("data") or ""),
            str(callback_query.get("id") or "") or None,
        )
        return

    message = update.get("message")
    if not message:
        return

    chat = message.get("chat", {})
    chat_id = chat.get("id")
    if chat_id is None:
        return

    text = extract_message_text("telegram", message)
    if text:
        handle_text_message("telegram", str(chat_id), text, extract_message_id("telegram", message))
        if is_admin("telegram", chat_id):
            safe_delete_message("telegram", str(chat_id), extract_message_id("telegram", message))
        return

    if is_admin("telegram", chat_id):
        send_admin_message("telegram", str(chat_id), "РџРѕРґРґРµСЂР¶РёРІР°СЋС‚СЃСЏ С‚РµРєСЃС‚РѕРІС‹Рµ РєРѕРјР°РЅРґС‹ Рё СЃРѕРѕР±С‰РµРЅРёСЏ.")
    else:
        send_public_welcome("telegram", str(chat_id))

def handle_max_update(update: dict[str, Any]) -> None:
    update_type = str(update.get("update_type") or "")
    log_max_admin_candidates(update)
    admin_actor_id = extract_matching_max_admin_actor_id(update)
    if update_type == "bot_started":
        chat_id = update.get("chat_id")
        if chat_id is None:
            return
        if admin_actor_id:
            send_admin_help("max", admin_actor_id)
            return
        payload = str(update.get("payload") or "")
        handle_public_start("max", str(chat_id), payload)
        return

    if update_type == "message_callback":
        message = update.get("message") or {}
        callback = update.get("callback") or {}
        chat_id = admin_actor_id or extract_max_message_peer_id(message)
        message_id = extract_message_id("max", message)
        data = str(callback.get("payload") or callback.get("data") or "")
        callback_id = str(callback.get("callback_id") or "") or None
        if not chat_id or not message_id:
            return
        handle_callback_action("max", chat_id, message_id, data, callback_id)
        return

    if update_type != "message_created":
        return

    message = update.get("message") or {}
    text = extract_message_text("max", message)
    chat_id = extract_max_chat_id_from_message(message)
    if not chat_id:
        return
    if text:
        handle_text_message("max", chat_id, text, extract_message_id("max", message))
        if admin_actor_id:
            safe_delete_message("max", chat_id, extract_message_id("max", message))
        return

    if admin_actor_id:
        send_admin_message("max", admin_actor_id, "РџРѕРґРґРµСЂР¶РёРІР°СЋС‚СЃСЏ С‚РµРєСЃС‚РѕРІС‹Рµ РєРѕРјР°РЅРґС‹ Рё СЃРѕРѕР±С‰РµРЅРёСЏ.")
    else:
        send_public_welcome("max", chat_id)



def fetch_telegram_updates() -> list[dict[str, Any]]:
    if not platform_enabled("telegram"):
        return []
    params: dict[str, Any] = {"timeout": POLL_TIMEOUT_SECONDS}
    last_update_id = state.get("telegram_last_update_id")
    if last_update_id is not None:
        params["offset"] = last_update_id + 1

    payload = telegram_api_request("getUpdates", data=params)
    return payload.get("result", [])



def fetch_max_updates() -> list[dict[str, Any]]:
    if not platform_enabled("max"):
        return []
    params: dict[str, Any] = {
        "timeout": MAX_POLL_TIMEOUT_SECONDS,
        "types": ",".join(MAX_UPDATE_TYPES),
    }
    marker = state.get("max_marker")
    if marker is not None:
        params["marker"] = marker
    payload = max_api_request("GET", "/updates", params=params)
    return payload.get("updates", [])



def fetch_max_updates_batch() -> tuple[list[dict[str, Any]], Any]:
    if not platform_enabled("max"):
        return [], None
    params: dict[str, Any] = {
        "timeout": MAX_POLL_TIMEOUT_SECONDS,
        "types": ",".join(MAX_UPDATE_TYPES),
    }
    marker = state.get("max_marker")
    if marker is not None:
        params["marker"] = marker
    payload = max_api_request("GET", "/updates", params=params)
    return payload.get("updates", []), payload.get("marker")



def initialize_telegram_profile() -> None:
    if not platform_enabled("telegram"):
        return
    payload = telegram_api_request("getMe")
    result = payload.get("result", {})
    bot_profiles["telegram"]["username"] = result.get("username")
    bot_profiles["telegram"]["name"] = result.get("first_name")
    if not bot_profiles["telegram"]["username"]:
        raise RuntimeError("РЈ Telegram-Р±РѕС‚Р° РЅРµ РЅР°Р№РґРµРЅ username. РЈРєР°Р¶Рё username С‡РµСЂРµР· @BotFather.")



def initialize_max_profile() -> None:
    if not platform_enabled("max"):
        return
    result = max_api_request("GET", "/me")
    bot_profiles["max"]["username"] = result.get("username")
    bot_profiles["max"]["name"] = result.get("first_name") or result.get("name")
    if not bot_profiles["max"]["username"]:
        raise RuntimeError("РЈ MAX-Р±РѕС‚Р° РЅРµ РЅР°Р№РґРµРЅ username. РџСЂРѕРІРµСЂСЊ РЅР°СЃС‚СЂРѕР№РєРё Р±РѕС‚Р° РІ MAX.")



def run_telegram_polling(stop_event: threading.Event) -> None:
    while not stop_event.is_set():
        try:
            telegram_updates = fetch_telegram_updates()
            for update in telegram_updates:
                try:
                    with state_lock:
                        handle_telegram_update(update)
                        state["telegram_last_update_id"] = update.get("update_id")
                        save_state()
                except requests.exceptions.RequestException as exc:
                    console_print(f"вќЊ РћС€РёР±РєР° requests РїСЂРё РѕР±СЂР°Р±РѕС‚РєРµ Telegram update {update.get('update_id')}: {exc}")
                    break
                except RuntimeError as exc:
                    console_print(f"вљ пёЏ РћС€РёР±РєР° Telegram API РїСЂРё РѕР±СЂР°Р±РѕС‚РєРµ update {update.get('update_id')}: {exc}")
                    break
                except Exception as exc:
                    console_print(f"вќЊ РќРµРѕР¶РёРґР°РЅРЅР°СЏ РѕС€РёР±РєР° РїСЂРё РѕР±СЂР°Р±РѕС‚РєРµ Telegram update {update.get('update_id')}: {exc}")
                    break
        except requests.exceptions.Timeout:
            console_print("вЏі РўР°Р№РјР°СѓС‚ Telegram long polling, РїСЂРѕРґРѕР»Р¶Р°СЋ СЂР°Р±РѕС‚Сѓ...")
        except requests.exceptions.ConnectionError:
            console_print("рџЊђ РћС€РёР±РєР° СЃРѕРµРґРёРЅРµРЅРёСЏ Telegram, РїРѕРІС‚РѕСЂ С‡РµСЂРµР· РЅРµСЃРєРѕР»СЊРєРѕ СЃРµРєСѓРЅРґ...")
            time.sleep(5)
        except requests.exceptions.RequestException as exc:
            console_print(f"вќЊ РћС€РёР±РєР° requests Telegram: {exc}")
            time.sleep(5)
        except RuntimeError as exc:
            console_print(f"вљ пёЏ РћС€РёР±РєР° MAX API: {exc}")
            time.sleep(5)



def run_max_polling(stop_event: threading.Event) -> None:
    while not stop_event.is_set():
        try:
            max_updates, next_marker = fetch_max_updates_batch()
            batch_processed = True
            for update in max_updates:
                try:
                    with state_lock:
                        handle_max_update(update)
                except requests.exceptions.RequestException as exc:
                    batch_processed = False
                    console_print(f"вќЊ РћС€РёР±РєР° requests РїСЂРё РѕР±СЂР°Р±РѕС‚РєРµ MAX update {update.get('timestamp')}: {exc}")
                    break
                except RuntimeError as exc:
                    batch_processed = False
                    console_print(f"вљ пёЏ РћС€РёР±РєР° MAX API РїСЂРё РѕР±СЂР°Р±РѕС‚РєРµ update {update.get('timestamp')}: {exc}")
                    break
                except Exception as exc:
                    batch_processed = False
                    console_print(f"вќЊ РќРµРѕР¶РёРґР°РЅРЅР°СЏ РѕС€РёР±РєР° РїСЂРё РѕР±СЂР°Р±РѕС‚РєРµ MAX update {update.get('timestamp')}: {exc}")
                    break
            if batch_processed and next_marker is not None:
                with state_lock:
                    state["max_marker"] = next_marker
                    save_state()
        except requests.exceptions.Timeout:
            console_print("вЏі РўР°Р№РјР°СѓС‚ MAX long polling, РїСЂРѕРґРѕР»Р¶Р°СЋ СЂР°Р±РѕС‚Сѓ...")
        except requests.exceptions.ConnectionError:
            console_print("рџЊђ РћС€РёР±РєР° СЃРѕРµРґРёРЅРµРЅРёСЏ MAX, РїРѕРІС‚РѕСЂ С‡РµСЂРµР· РЅРµСЃРєРѕР»СЊРєРѕ СЃРµРєСѓРЅРґ...")
            time.sleep(5)
        except requests.exceptions.RequestException as exc:
            console_print(f"вќЊ РћС€РёР±РєР° requests MAX: {exc}")
            time.sleep(5)
        except RuntimeError as exc:
            console_print(f"вљ пёЏ РћС€РёР±РєР° MAX API: {exc}")
            time.sleep(5)



def main() -> None:
    mini_app_server = MiniAppServer(
        MINI_APP_HOST,
        MINI_APP_PORT,
        MINI_APP_TITLE,
        asset_version=MINI_APP_CACHE_BUSTER or "",
        order_provider=get_public_order_payload,
        logger=console_print,
    )
    local_mini_app_url = mini_app_server.start()
    initialize_telegram_profile()
    initialize_max_profile()
    register_telegram_commands()
    register_telegram_mini_app_menu_button()
    with state_lock:
        sync_archives()
    console_print(f"Mini App local URL: {local_mini_app_url}")
    if MINI_APP_PUBLIC_URL:
        console_print(f"Mini App public URL: {get_mini_app_public_url()}")
    else:
        console_print("MINI_APP_PUBLIC_URL is not set. Mini App is available locally, but Telegram will not open it inside the app yet.")
    console_print("рџ¤– CULT_BOT Р·Р°РїСѓС‰РµРЅ")
    console_print(f"рџ•’ Р§Р°СЃРѕРІРѕР№ РїРѕСЏСЃ: {TIMEZONE_NAME}")
    console_print(f"рџ—ѓ РђСЂС…РёРІ Р·Р°РєР°Р·РѕРІ: {ARCHIVE_DIR}")
    if platform_enabled("telegram"):
        console_print(f"рџ“Ё Telegram admin chat_id={TELEGRAM_ADMIN_CHAT_ID}")
        console_print(f"рџ”— Telegram deep-link: @{bot_profiles['telegram']['username']}")
    if platform_enabled("max"):
        console_print(f"рџ“Ё MAX admin chat_id={MAX_ADMIN_CHAT_ID}")
        console_print(f"рџ”— MAX deep-link: @{bot_profiles['max']['username']}")
        console_print("вљ пёЏ MAX long polling РїРѕРґС…РѕРґРёС‚ РґР»СЏ СЂР°Р·СЂР°Р±РѕС‚РєРё; РґР»СЏ production РґРѕРєСѓРјРµРЅС‚Р°С†РёСЏ MAX СЂРµРєРѕРјРµРЅРґСѓРµС‚ Webhook.")

    stop_event = threading.Event()
    workers: list[threading.Thread] = []

    if platform_enabled("telegram"):
        workers.append(
            threading.Thread(
                target=run_telegram_polling,
                args=(stop_event,),
                name="telegram-polling",
                daemon=True,
            )
        )
    if platform_enabled("max"):
        workers.append(
            threading.Thread(
                target=run_max_polling,
                args=(stop_event,),
                name="max-polling",
                daemon=True,
            )
        )

    for worker in workers:
        worker.start()

    try:
        while True:
            time.sleep(LOOP_INTERVAL_SECONDS)
    except KeyboardInterrupt:
        console_print("\nрџ‘‹ Р’С‹С…РѕРґ...")
        stop_event.set()
        for worker in workers:
            worker.join(timeout=1)


    finally:
        mini_app_server.stop()


if __name__ == "__main__":
    main()
