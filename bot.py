import json
import os
import re
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import requests
from dotenv import load_dotenv

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
            f"❌ {env_name} должен указывать на JSON-файл, а не на папку: {path}"
        )

    if path.name in {"", ".", ".."}:
        raise ValueError(
            f"❌ {env_name} должен указывать на файл, например {default_filename}"
        )

    return path


TELEGRAM_TOKEN = get_env_value("TOKEN")
TELEGRAM_ADMIN_CHAT_ID = get_env_value("ADMIN_CHAT_ID")
MAX_TOKEN = get_env_value("MAX_TOKEN")
MAX_ADMIN_CHAT_ID = get_env_value("MAX_ADMIN_CHAT_ID")
PROXY = get_env_value("PROXY")
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
MENU_LABEL = "Меню"
CONTACT_URL = "https://t.me/cultmebel?direct"
VK_URL = "https://vk.com/cultmebel"
TG_URL = "https://t.me/cultmebel"
PAYMENT_OPTIONS = {
    "0": 0,
    "50": 50,
    "100": 100,
}

STATUS_LABELS = {
    "awaiting": "В ожидании",
    "accepted": "Принято в работу",
    "production": "Изготовление",
    "painting": "Покраска",
    "assembly": "Сборка",
    "ready": "Заказ готов",
    "awaiting_delivery": "Ожидание доставки",
    "in_transit": "В пути",
    "completed": "Завершён",
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
    "января": 1,
    "февраля": 2,
    "марта": 3,
    "апреля": 4,
    "мая": 5,
    "июня": 6,
    "июля": 7,
    "августа": 8,
    "сентября": 9,
    "октября": 10,
    "ноября": 11,
    "декабря": 12,
}
PLATFORM_LABELS = {
    "telegram": "Telegram",
    "max": "MAX",
}
MAX_UPDATE_TYPES = ["message_created", "message_callback", "bot_started"]

if not TELEGRAM_TOKEN and not MAX_TOKEN:
    raise ValueError("❌ Укажи хотя бы один токен: TOKEN для Telegram или MAX_TOKEN для MAX.")

if TELEGRAM_TOKEN and not TELEGRAM_ADMIN_CHAT_ID:
    raise ValueError("❌ Не найден ADMIN_CHAT_ID в .env")

if MAX_TOKEN and not MAX_ADMIN_CHAT_ID:
    raise ValueError("❌ Не найден MAX_ADMIN_CHAT_ID в .env")

if PROXY:
    parsed_proxy = urlparse(PROXY)
    if parsed_proxy.scheme.lower() not in ALLOWED_PROXY_SCHEMES:
        raise ValueError(
            "❌ Некорректная схема PROXY. Используй http://, https://, socks5:// или socks5h://"
        )

try:
    LOCAL_TZ = ZoneInfo(TIMEZONE_NAME)
except Exception as exc:
    raise ValueError(
        "❌ Некорректная TIMEZONE. Используй IANA-имя, например Europe/Moscow или UTC"
    ) from exc

thread_local = threading.local()
state_lock = threading.RLock()


def get_http_session() -> requests.Session:
    existing_session = getattr(thread_local, "session", None)
    if existing_session is not None:
        return existing_session

    created_session = requests.Session()
    created_session.trust_env = False
    if PROXY:
        created_session.proxies.update({"http": PROXY, "https": PROXY})
    thread_local.session = created_session
    return created_session

TELEGRAM_API_BASE_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}" if TELEGRAM_TOKEN else None
MAX_API_BASE_URL = "https://platform-api.max.ru" if MAX_TOKEN else None
conversation_state: dict[str, dict[str, Any]] = {}
ui_state: dict[str, dict[str, str]] = {}
bot_profiles: dict[str, dict[str, Any]] = {
    "telegram": {"enabled": bool(TELEGRAM_TOKEN), "username": None, "name": None},
    "max": {"enabled": bool(MAX_TOKEN), "username": None, "name": None},
}



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
        return "—"
    dt_utc = datetime.fromisoformat(iso_timestamp)
    dt_local = dt_utc.astimezone(LOCAL_TZ)
    return f"{dt_local.strftime('%Y-%m-%d %H:%M')} {get_timezone_label()}"



def ensure_parent_dir(path: Path) -> None:
    parent = path.parent
    if parent != Path("") and not parent.exists():
        parent.mkdir(parents=True, exist_ok=True)



def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)



def load_json(path: Path, fallback: Any) -> Any:
    if not path.exists():
        return fallback

    try:
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)
    except (OSError, json.JSONDecodeError):
        return fallback


state = load_json(STATE_FILE, {"telegram_last_update_id": None, "max_marker": None})
orders: list[dict[str, Any]] = load_json(ORDERS_FILE, [])
catalog_items: list[dict[str, Any]] = load_json(CATALOG_FILE, [])



def save_state() -> None:
    with state_lock:
        ensure_parent_dir(STATE_FILE)
        STATE_FILE.write_text(
            json.dumps(state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )



def save_orders() -> None:
    with state_lock:
        ensure_parent_dir(ORDERS_FILE)
        ORDERS_FILE.write_text(
            json.dumps(orders, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )



def save_catalog() -> None:
    with state_lock:
        ensure_parent_dir(CATALOG_FILE)
        CATALOG_FILE.write_text(
            json.dumps(catalog_items, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )



def parse_rubles(raw_value: str | int) -> int:
    if isinstance(raw_value, int):
        return max(raw_value, 0)
    cleaned = re.sub(r"(руб\.?|р\.?|₽|\s|[.,])", "", str(raw_value).lower())
    if not cleaned.isdigit():
        raise ValueError("Укажи сумму в рублях числом, например 21000.")
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
    migrated["price"] = f"{total_price:,}".replace(",", ".") + " ₽"

    paid_amount = migrated.get("paid_amount")
    if paid_amount is None:
        payment_percent = int(migrated.get("payment_percent", 0) or 0)
        paid_amount = round(total_price * payment_percent / 100)
    migrated["paid_amount"] = max(0, min(safe_parse_rubles(paid_amount, default=0), total_price))

    migrated["title"] = str(
        migrated.get("title") or migrated.get("caption") or f"Легаси заказ #{migrated.get('id', '?')}"
    ).strip()[:MAX_TITLE_LENGTH] or f"Легаси заказ #{migrated.get('id', '?')}"
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
        title = f"Товар #{migrated.get('id', '?')}"
    migrated["title"] = title[:MAX_TITLE_LENGTH] or f"Товар #{migrated.get('id', '?')}"
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



def telegram_api_request(method: str, *, data: dict[str, Any] | None = None) -> dict[str, Any]:
    if not TELEGRAM_API_BASE_URL:
        raise RuntimeError("Telegram не настроен")
    response = get_http_session().post(
        f"{TELEGRAM_API_BASE_URL}/{method}",
        data=data or {},
        timeout=REQUEST_TIMEOUT_SECONDS,
        allow_redirects=False,
    )
    response.raise_for_status()
    payload = response.json()
    if not payload.get("ok"):
        description = payload.get("description", "Неизвестная ошибка Telegram API")
        raise RuntimeError(f"Telegram API error in {method}: {description}")
    return payload



def max_api_request(
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not MAX_API_BASE_URL or not MAX_TOKEN:
        raise RuntimeError("MAX не настроен")
    response = get_http_session().request(
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
        result = max_api_request("POST", "/messages", params={"user_id": chat_id}, json_body=body)
        return result.get("message", result)

    raise ValueError(f"Неизвестная платформа: {platform}")



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

    raise ValueError(f"Неизвестная платформа: {platform}")



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

    raise ValueError(f"Неизвестная платформа: {platform}")



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

    raise ValueError(f"Неизвестная платформа: {platform}")



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

    reply_markup = build_admin_reply_keyboard() if platform == "telegram" else inline_keyboard
    result = send_message(platform, chat_id, text, reply_markup=reply_markup, parse_mode=parse_mode)
    new_message_id = extract_message_id(platform, result)
    if new_message_id is not None:
        set_ui_message(actor, new_message_id)

    if platform == "telegram" and inline_keyboard and new_message_id is not None:
        try:
            edit_message(platform, chat_id, new_message_id, text, reply_markup=inline_keyboard, parse_mode=parse_mode)
        except (RuntimeError, requests.exceptions.RequestException):
            inline_result = send_message(platform, chat_id, text, reply_markup=inline_keyboard, parse_mode=parse_mode)
            inline_message_id = extract_message_id(platform, inline_result)
            if inline_message_id is not None:
                set_ui_message(actor, inline_message_id)
                return inline_message_id

    return new_message_id or ""



def is_admin(platform: str, chat_id: str | int) -> bool:
    if platform == "telegram":
        return TELEGRAM_ADMIN_CHAT_ID is not None and str(chat_id) == str(TELEGRAM_ADMIN_CHAT_ID)
    if platform == "max":
        return MAX_ADMIN_CHAT_ID is not None and str(chat_id) == str(MAX_ADMIN_CHAT_ID)
    return False



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
        if item["platform"] == platform and item["chat_id"] == chat_id:
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



def format_price(value: int) -> str:
    return f"{value:,}".replace(",", ".") + " ₽"



def calculate_payment_percent(order: dict[str, Any]) -> int:
    total_price = max(order["total_price"], 1)
    return round(order["paid_amount"] * 100 / total_price)



def get_paid_text(order: dict[str, Any]) -> str:
    return (
        f"{calculate_payment_percent(order)}% "
        f"({format_price(order['paid_amount'])} из {format_price(order['total_price'])})"
    )



def format_order_link(platform: str, token: str) -> str:
    username = bot_profiles.get(platform, {}).get("username")
    if not username:
        return f"Токен заказа: {token}"
    if platform == "telegram":
        return f"https://t.me/{username}?start=order_{token}"
    if platform == "max":
        return f"https://max.ru/{username}?start=order_{token}"
    return token



def build_order_links_text(order: dict[str, Any]) -> str:
    lines: list[str] = []
    for platform in ("telegram", "max"):
        if platform_enabled(platform):
            lines.append(f"{get_platform_label(platform)}: {format_order_link(platform, order['token'])}")
    return "\n".join(lines) if lines else f"Токен заказа: {order['token']}"



def build_status_text(order: dict[str, Any]) -> str:
    current_step, total_steps = get_status_progress(order)
    return f"{get_status_label(order['status'])} ({current_step}/{total_steps})"



def archive_file_path(order_id: int) -> Path:
    return ARCHIVE_DIR / f"order_{order_id:05d}.txt"



def append_history(order: dict[str, Any], text: str) -> None:
    order.setdefault("history", []).append({"timestamp": now_utc_iso(), "text": text})



def get_order_sources_text(order: dict[str, Any]) -> str:
    sources = [get_platform_label(item["platform"]) for item in get_order_bindings(order)]
    return ", ".join(sources) if sources else "Пока ни в одном мессенджере"



def get_order_binding_details(order: dict[str, Any]) -> str:
    bindings = get_order_bindings(order)
    if not bindings:
        return "—"
    return "\n".join(
        f"• {get_platform_label(item['platform'])}: {item['chat_id']}"
        for item in bindings
    )



def write_order_archive(order: dict[str, Any], lifecycle_state: str) -> None:
    ensure_dir(ARCHIVE_DIR)
    history_lines = order.get("history", [])
    lines = [
        f"Заказ #{order['id']}",
        f"Состояние: {lifecycle_state}",
        f"Наименование: {order['title']}",
        f"Создан через: {get_platform_label(order.get('created_via', 'telegram'))}",
        f"Каналы клиента: {get_order_sources_text(order)}",
        f"Цена: {format_price(order['total_price'])}",
        f"Оплачено: {get_paid_text(order)}",
        f"Статус: {build_status_text(order)}",
        f"Доставка: {'Да' if order['has_delivery'] else 'Нет'}",
        f"Создан: {format_local_time(order['created_at'])}",
        f"Обновлён: {format_local_time(order.get('updated_at'))}",
        f"Завершён: {format_local_time(order.get('completed_at'))}",
        f"План доставки: {order.get('delivery_planned_for') or '—'}",
        f"Примечание: {order.get('notes') or '—'}",
        "",
        "История:",
    ]
    if history_lines:
        for item in history_lines:
            lines.append(f"- {format_local_time(item['timestamp'])}: {item['text']}")
    else:
        lines.append("- История пока пустая.")
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
    archive_file_path(order["id"]).write_text("\n".join(lines), encoding="utf-8")



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
    append_history(order, f"Заказ создан через {get_platform_label(order['created_via'])}.")
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
    append_history(order, f"Статус изменён на «{get_status_label(status_key)}».")
    persist_order(order, "completed" if order["status"] == "completed" else "active")



def set_delivery_schedule(order: dict[str, Any], schedule_text: str) -> None:
    order["status"] = "awaiting_delivery"
    order["delivery_planned_for"] = schedule_text.strip()
    order["updated_at"] = now_utc_iso()
    append_history(order, f"Доставка запланирована на {order['delivery_planned_for']}.")
    persist_order(order)



def update_delivery_flag(order: dict[str, Any], has_delivery: bool) -> None:
    order["has_delivery"] = has_delivery
    if not has_delivery and order["status"] in DELIVERY_EXTRA_STATUS_KEYS:
        order["status"] = "ready"
        order["delivery_planned_for"] = None
    order["updated_at"] = now_utc_iso()
    append_history(order, f"Изменён способ получения: {'доставка' if has_delivery else 'самовывоз'}.")
    persist_order(order)



def add_payment(order: dict[str, Any], amount: int) -> None:
    order["paid_amount"] = min(order["total_price"], order["paid_amount"] + amount)
    order["updated_at"] = now_utc_iso()
    append_history(order, f"Добавлена оплата {format_price(amount)}.")
    persist_order(order, "completed" if order["status"] == "completed" else "active")



def mark_fully_paid(order: dict[str, Any]) -> None:
    order["paid_amount"] = order["total_price"]
    order["updated_at"] = now_utc_iso()
    append_history(order, "Заказ отмечен как полностью оплаченный.")
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
    append_history(order, "Заказ завершён.")
    persist_order(order, "completed")



def build_public_keyboard(platform: str, chat_id: str | None = None, include_refresh_token: str | None = None) -> dict[str, Any]:
    keyboard: list[list[dict[str, Any]]] = []
    if include_refresh_token:
        keyboard.append([{"text": "Обновить статус", "callback_data": f"client:refresh:{include_refresh_token}"}])
    if chat_id and has_customer_orders(platform, chat_id):
        keyboard.append([{"text": "Мои заказы", "callback_data": "client:list"}])
    keyboard.extend(
        [
            [{"text": "Связаться", "url": CONTACT_URL}],
            [{"text": "Соц.сети Культ Мебель", "callback_data": "public:socials"}],
        ]
    )
    return {"inline_keyboard": keyboard}



def build_customer_orders_text(platform: str, chat_id: str) -> str:
    customer_orders = find_orders_for_customer(platform, chat_id)
    if not customer_orders:
        return "У вас пока нет привязанных заказов. Откройте персональную ссылку, которую вам отправил менеджер."

    total_sum = sum(order["total_price"] for order in customer_orders)
    total_paid = sum(order["paid_amount"] for order in customer_orders)
    lines = [
        "📦 Ваши заказы:",
        f"Всего заказов: {len(customer_orders)}",
        f"Общая сумма: {format_price(total_sum)}",
        f"Оплачено суммарно: {format_price(total_paid)}",
    ]
    for order in customer_orders:
        lines.append(
            "\n".join(
                [
                    f"📦 Заказ #{order['id']}",
                    order["title"],
                    f"Статус: {build_status_text(order)}",
                    f"Цена: {format_price(order['total_price'])}",
                    f"Оплачено: {get_paid_text(order)}",
                    f"Создан: {format_local_time(order['created_at'])}",
                    f"Открыт в: {get_order_sources_text(order)}",
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
                    "text": f"Открыть #{order['id']} — {order['title'][:28]}",
                    "callback_data": f"client:view:{order['token']}",
                }
            ]
        )
    rows.append([{"text": "Связаться", "url": CONTACT_URL}])
    rows.append([{"text": "Соц.сети Культ Мебель", "callback_data": "public:socials"}])
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



def build_admin_home_keyboard() -> dict[str, Any]:
    return {
        "inline_keyboard": [
            [
                {"text": "🆕 Новый заказ", "callback_data": "adminmenu:neworder"},
                {"text": "🗂 Заказы", "callback_data": "admin:list"},
            ],
            [
                {"text": "📚 Каталог", "callback_data": "catalog:list"},
                {"text": "📊 Отчёт", "callback_data": "adminmenu:report"},
            ],
        ]
    }



def build_catalog_list_text() -> str:
    if not catalog_items:
        return (
            "📚 Каталог пока пуст.\n\n"
            "Нажми «Добавить товар», затем отправь название и цену — после этого товар можно будет выбирать при создании заказа."
        )

    lines = ["📚 Каталог товаров:"]
    for item in sorted(catalog_items, key=lambda value: value["id"]):
        lines.append(f"#{item['id']} • {item['title']}\nЦена: {format_price(item['total_price'])}")
    return "\n\n".join(lines)



def build_catalog_list_keyboard() -> dict[str, Any]:
    rows: list[list[dict[str, Any]]] = []
    for item in sorted(catalog_items, key=lambda value: value["id"]):
        rows.append(
            [
                {
                    "text": f"{item['title'][:28]} — {format_price(item['total_price'])}",
                    "callback_data": f"catalog:view:{item['id']}",
                }
            ]
        )
    rows.append([{"text": "➕ Добавить товар", "callback_data": "catalog:add"}])
    rows.append([{"text": "⬅️ В меню", "callback_data": "adminmenu:home"}])
    return {"inline_keyboard": rows}



def build_catalog_item_keyboard(item_id: int) -> dict[str, Any]:
    return {
        "inline_keyboard": [
            [{"text": "🗑 Удалить товар", "callback_data": f"catalog:delete:{item_id}"}],
            [{"text": "⬅️ К каталогу", "callback_data": "catalog:list"}],
        ]
    }



def build_catalog_pick_keyboard() -> dict[str, Any]:
    rows: list[list[dict[str, Any]]] = []
    for item in sorted(catalog_items, key=lambda value: value["id"]):
        rows.append(
            [
                {
                    "text": f"{item['title'][:24]} — {format_price(item['total_price'])}",
                    "callback_data": f"create:item:{item['id']}",
                }
            ]
        )
    rows.append([{"text": "📚 Каталог", "callback_data": "catalog:list"}])
    rows.append([{"text": "⬅️ В меню", "callback_data": "adminmenu:home"}])
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
                {"text": "Да", "callback_data": "create:delivery:yes"},
                {"text": "Нет", "callback_data": "create:delivery:no"},
            ]
        ]
    }



def chunk_buttons(buttons: list[dict[str, Any]], chunk_size: int) -> list[list[dict[str, Any]]]:
    return [buttons[index : index + chunk_size] for index in range(0, len(buttons), chunk_size)]



def build_admin_order_keyboard(order: dict[str, Any]) -> dict[str, Any]:
    status_buttons = [
        {
            "text": f"{'✅ ' if order['status'] == status_key else ''}{get_status_label(status_key)}",
            "callback_data": f"admin:status:{order['id']}:{status_key}",
        }
        for status_key in get_status_keys(order["has_delivery"])
    ]
    inline_keyboard = chunk_buttons(status_buttons, 2)
    inline_keyboard.append(
        [
            {
                "text": f"{'🚚' if order['has_delivery'] else '🛻'} {'Доставка' if order['has_delivery'] else 'Самовывоз'}",
                "callback_data": f"admin:delivery_toggle:{order['id']}",
            }
        ]
    )
    if order["paid_amount"] < order["total_price"]:
        inline_keyboard.append(
            [
                {"text": "💯 Клиент оплатил всё", "callback_data": f"admin:payment_full:{order['id']}"},
                {"text": "💵 Добавить оплату", "callback_data": f"admin:payment_add:{order['id']}"},
            ]
        )
    inline_keyboard.append(
        [
            {"text": "Завершить заказ", "callback_data": f"admin:finish:{order['id']}"},
            {"text": "Удалить заказ", "callback_data": f"admin:delete:{order['id']}"},
        ]
    )
    inline_keyboard.append([{"text": "К списку заказов", "callback_data": "admin:list"}])
    return {"inline_keyboard": inline_keyboard}



def build_finish_confirmation_keyboard(order_id: int) -> dict[str, Any]:
    return {
        "inline_keyboard": [
            [
                {"text": "Да, завершить", "callback_data": f"admin:finish_yes:{order_id}"},
                {"text": "Нет", "callback_data": f"admin:finish_no:{order_id}"},
            ]
        ]
    }



def build_delete_confirmation_keyboard(order_id: int) -> dict[str, Any]:
    return {
        "inline_keyboard": [
            [
                {"text": "Да, удалить", "callback_data": f"admin:delete_yes:{order_id}"},
                {"text": "Нет", "callback_data": f"admin:delete_no:{order_id}"},
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
        return "📭 Сейчас активных заказов нет. Используй /neworder, чтобы создать новый заказ."

    lines = ["🗂 Текущие заказы:"]
    for order in active_orders:
        lines.append(
            "\n".join(
                [
                    f"📦 Заказ #{order['id']}",
                    order["title"],
                    f"Создан через: {get_platform_label(order.get('created_via', 'telegram'))}",
                    f"Каналы клиента: {get_order_sources_text(order)}",
                    f"Статус: {build_status_text(order)}",
                    f"Оплачено: {get_paid_text(order)}",
                    f"Создан: {format_local_time(order['created_at'])}",
                ]
            )
        )
    return "\n\n".join(lines)



def build_orders_list_keyboard() -> dict[str, Any] | None:
    active_orders = build_active_orders()
    if not active_orders:
        return {"inline_keyboard": [[{"text": "⬅️ В меню", "callback_data": "adminmenu:home"}]]}

    rows: list[list[dict[str, Any]]] = []
    for order in active_orders:
        rows.append(
            [
                {
                    "text": f"Открыть #{order['id']} — {order['title'][:30]}",
                    "callback_data": f"admin:view:{order['id']}",
                }
            ]
        )
    rows.append([{"text": "⬅️ В меню", "callback_data": "adminmenu:home"}])
    return {"inline_keyboard": rows}



def render_order_text(order: dict[str, Any], *, for_admin: bool) -> str:
    blocks = [
        "\n".join(
            [
                f"📦 Заказ #{order['id']}",
                order["title"],
                f"Статус: {build_status_text(order)}",
                f"Примечание: {order.get('notes') or '—'}",
            ]
        ),
        "\n".join(
            [
                f"Цена: {format_price(order['total_price'])}",
                f"Оплачено: {get_paid_text(order)}",
            ]
        ),
        "\n".join(
            [
                f"Доставка: {'Да' if order['has_delivery'] else 'Нет'}",
                f"Создан: {format_local_time(order['created_at'])}",
                f"Создан через: {get_platform_label(order.get('created_via', 'telegram'))}",
            ]
        ),
    ]

    if for_admin:
        admin_lines = [
            "Ссылки для клиента:",
            build_order_links_text(order),
            f"Клиент подключён в: {get_order_sources_text(order)}",
            f"ID клиентов:\n{get_order_binding_details(order)}",
        ]
        if order.get("completed_at"):
            admin_lines.append(f"Завершён: {format_local_time(order['completed_at'])}")
        blocks.append("\n".join(admin_lines))
    else:
        customer_lines = ["Срок изготовления указан в оферте."]
        if order.get("paid_amount", 0) < order.get("total_price", 0):
            customer_lines.append("Если вам необходимо доплатить, нажмите кнопку «Связаться».")
        if order["status"] == "ready":
            if order["has_delivery"]:
                customer_lines.append(
                    "В ближайшее время мы напишем вам для уточнения вопроса доставки. Если нужно быстрее — нажмите «Связаться»."
                )
            else:
                customer_lines.append(
                    "В ближайшее время мы напишем вам для уточнения вопроса самовывоза. Если нужно быстрее — нажмите «Связаться»."
                )
        if order["status"] == "awaiting_delivery" and order.get("delivery_planned_for"):
            customer_lines.append(f"Доставка запланирована на {order['delivery_planned_for']}.")
        if order["status"] == "completed":
            customer_lines.append("Спасибо за заказ! Если понадобится ещё мебель — мы на связи.")
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
    send_message(
        platform,
        chat_id,
        (
            "Привет! Это бот Культ Мебель для отслеживания заказов.\n\n"
            "Если менеджер уже отправил вам персональную ссылку — откройте её, и бот покажет статус заказа.\n"
            "Если ссылки ещё нет, напишите нам — поможем оформить заказ и ответим на вопросы."
        ),
        reply_markup=build_public_keyboard(platform, chat_id),
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
            "Добро пожаловать в панель заказов Культ Мебель.\n\n"
            "Доступно:\n"
            "• /neworder — создать заказ\n"
            "• /orders — открыть текущие заказы\n"
            "• /catalog — каталог товаров\n"
            "• /report — отчёт по периоду\n"
            "• /cancel — отменить текущее действие\n\n"
            f"Активные каналы бота: {', '.join(channels)}. Заказы синхронизируются между мессенджерами."
        ),
        inline_keyboard=build_admin_home_keyboard(),
    )



def parse_paid_amount(raw_value: str) -> int:
    amount = parse_rubles(raw_value)
    if amount <= 0:
        raise ValueError("Сумма доплаты должна быть больше нуля.")
    return amount



def parse_russian_period(raw_value: str) -> tuple[datetime, datetime]:
    parts = [part.strip().lower() for part in raw_value.split("_", maxsplit=1)]
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise ValueError("Период нужно ввести в формате: 22 января 2025_1 сентября 2025")

    def parse_part(part: str) -> datetime:
        match = re.fullmatch(r"(\d{1,2})\s+([а-яё]+)\s+(\d{4})", part)
        if not match:
            raise ValueError("Период нужно ввести в формате: 22 января 2025_1 сентября 2025")
        day = int(match.group(1))
        month_label = match.group(2)
        year = int(match.group(3))
        month = RUSSIAN_MONTHS.get(month_label)
        if month is None:
            raise ValueError(f"Не удалось распознать месяц «{month_label}».")
        try:
            return datetime(year, month, day, tzinfo=LOCAL_TZ)
        except ValueError as exc:
            raise ValueError("Проверь корректность дат в периоде.") from exc

    start_dt = parse_part(parts[0]).replace(hour=0, minute=0, second=0, microsecond=0)
    end_dt = parse_part(parts[1]).replace(hour=23, minute=59, second=59, microsecond=999999)
    if end_dt < start_dt:
        raise ValueError("Конечная дата периода не может быть раньше начальной.")
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
        "📊 Отчёт по архиву заказов",
        f"Период: {start_dt.strftime('%Y-%m-%d')} — {end_dt.strftime('%Y-%m-%d')}",
        "",
        f"Всего заказов: {total_count}",
        f"Активных: {active_count}",
        f"Завершённых: {completed_count}",
        f"Удалённых: {deleted_count}",
        f"Сумма заказов: {format_price(total_sum)}",
        f"Получено оплат: {format_price(total_paid)}",
        f"Осталось получить: {format_price(total_due)}",
        "",
        "По каналам создания:",
        f"• Telegram: {platform_summary['telegram']}",
        f"• MAX: {platform_summary['max']}",
    ]
    return "\n".join(lines)



def start_new_order_flow(platform: str, chat_id: str) -> None:
    clear_conversation(actor_key(platform, chat_id))
    if not catalog_items:
        send_admin_message(
            platform,
            chat_id,
            "📚 Каталог пуст. Сначала добавь хотя бы один товар, затем можно будет создать заказ.",
            inline_keyboard=build_catalog_list_keyboard(),
        )
        return

    set_conversation(actor_key(platform, chat_id), "awaiting_catalog_pick", draft={})
    send_admin_message(
        platform,
        chat_id,
        "Выбери товар из каталога для нового заказа:",
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
        send_admin_message(platform, chat_id, "Введи период в формате: 22 января 2025_1 сентября 2025")
        return

    if stripped == "/cancel":
        clear_conversation(actor_key(platform, chat_id))
        send_admin_message(
            platform,
            chat_id,
            "🛑 Текущее действие отменено.",
            inline_keyboard=build_admin_home_keyboard(),
        )
        return

    send_admin_message(
        platform,
        chat_id,
        "Неизвестная команда. Используй /neworder, /orders, /catalog, /report или /cancel.",
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
            "Заказ по этой ссылке не найден или уже удалён. Напишите нам, и мы поможем уточнить информацию.",
            reply_markup=build_public_keyboard(platform, chat_id),
        )
        return

    if link_customer_to_order(order, platform, chat_id):
        append_history(order, f"Клиент открыл персональную ссылку в {get_platform_label(platform)} из чата {chat_id}.")
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
            "Используй /neworder, чтобы создать заказ, /orders — чтобы посмотреть список, или /catalog — чтобы открыть каталог.",
            inline_keyboard=build_admin_home_keyboard(),
        )
        return

    step = state_for_chat.get("step")
    cleaned_text = text.strip()

    if step == "awaiting_catalog_title":
        if not cleaned_text:
            send_admin_message(platform, chat_id, "Наименование товара не может быть пустым.")
            return
        if len(cleaned_text) > MAX_TITLE_LENGTH:
            send_admin_message(platform, chat_id, f"Наименование слишком длинное. Лимит — {MAX_TITLE_LENGTH} символов.")
            return
        set_conversation(actor_key(platform, chat_id), "awaiting_catalog_price", draft={"title": cleaned_text})
        send_admin_message(platform, chat_id, "Теперь введи цену товара, например: 42000")
        return

    if step == "awaiting_catalog_price":
        if not cleaned_text:
            send_admin_message(platform, chat_id, "Цена не может быть пустой.")
            return
        if len(cleaned_text) > MAX_PRICE_LENGTH:
            send_admin_message(platform, chat_id, f"Цена слишком длинная. Лимит — {MAX_PRICE_LENGTH} символов.")
            return
        try:
            total_price = parse_rubles(cleaned_text)
        except ValueError as exc:
            send_admin_message(platform, chat_id, f"⚠️ {exc}")
            return
        draft = dict(state_for_chat["draft"])
        item = create_catalog_item(draft["title"], total_price)
        clear_conversation(actor_key(platform, chat_id))
        send_admin_message(
            platform,
            chat_id,
            f"✅ Товар добавлен в каталог.\n\n#{item['id']} • {item['title']}\nЦена: {format_price(item['total_price'])}",
            inline_keyboard=build_catalog_list_keyboard(),
        )
        return

    if step == "awaiting_notes":
        notes = "" if cleaned_text == "-" else cleaned_text
        if len(notes) > MAX_NOTES_LENGTH:
            send_admin_message(platform, chat_id, f"Примечание слишком длинное. Лимит — {MAX_NOTES_LENGTH} символов.")
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
            f"✅ Заказ создан.\n\n{render_order_text(order, for_admin=True)}",
            inline_keyboard=build_admin_order_keyboard(order),
        )
        return

    if step == "awaiting_payment_add":
        order = find_order_by_id(int(state_for_chat["order_id"]))
        if not order:
            clear_conversation(actor_key(platform, chat_id))
            send_admin_message(platform, chat_id, "Заказ не найден.", inline_keyboard=build_orders_list_keyboard())
            return
        try:
            amount = parse_paid_amount(cleaned_text)
        except ValueError as exc:
            send_admin_message(platform, chat_id, f"⚠️ {exc}")
            return
        add_payment(order, amount)
        clear_conversation(actor_key(platform, chat_id))
        notify_customer_order_update(order, f"По заказу #{order['id']} отмечена новая оплата: {format_price(amount)}.")
        send_admin_message(
            platform,
            chat_id,
            f"✅ Оплата обновлена.\n\n{render_order_text(order, for_admin=True)}",
            inline_keyboard=build_admin_order_keyboard(order),
        )
        return

    if step == "awaiting_delivery_schedule":
        order = find_order_by_id(int(state_for_chat["order_id"]))
        if not order:
            clear_conversation(actor_key(platform, chat_id))
            send_admin_message(platform, chat_id, "Заказ не найден.", inline_keyboard=build_orders_list_keyboard())
            return
        if not cleaned_text:
            send_admin_message(platform, chat_id, "Укажи дату и время доставки, например: 20 января, 20:00")
            return
        set_delivery_schedule(order, cleaned_text)
        clear_conversation(actor_key(platform, chat_id))
        notify_customer_order_update(order, f"По заказу #{order['id']} обновлён статус: Ожидание доставки.")
        send_admin_message(
            platform,
            chat_id,
            f"✅ Доставка запланирована.\n\n{render_order_text(order, for_admin=True)}",
            inline_keyboard=build_admin_order_keyboard(order),
        )
        return

    if step == "awaiting_report_period":
        try:
            start_dt, end_dt = parse_russian_period(cleaned_text)
        except ValueError as exc:
            send_admin_message(platform, chat_id, f"⚠️ {exc}")
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
        "Используй /cancel и начни заново через /neworder.",
        inline_keyboard=build_admin_home_keyboard(),
    )



def notify_customer_order_completed(order: dict[str, Any]) -> None:
    for binding in get_order_bindings(order):
        send_message(
            binding["platform"],
            binding["chat_id"],
            (
                "Спасибо за ваш заказ в Культ Мебель! ❤️\n\n"
                f"{order['title']} отмечен как завершённый. Если понадобится помощь, мы всегда на связи."
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
        safe_edit_or_send(platform, chat_id_str, message_id, "Соцсети Культ Мебель:", build_socials_keyboard())
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
                "Не удалось открыть заказ. Если нужна помощь — напишите нам.",
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
                "Заказ больше недоступен. Напишите нам, и мы поможем уточнить информацию.",
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
        send_admin_message(platform, chat_id_str, "Введи период в формате: 22 января 2025_1 сентября 2025")
        return

    if data == "catalog:list":
        open_catalog(platform, chat_id_str)
        return

    if data == "catalog:add":
        set_conversation(actor_key(platform, chat_id_str), "awaiting_catalog_title")
        send_admin_message(platform, chat_id_str, "Введи название товара для каталога, например: Кровать 160х200")
        return

    if data.startswith("catalog:view:"):
        item_id = int(data.split(":", maxsplit=2)[2])
        item = find_catalog_item_by_id(item_id)
        if not item:
            send_admin_message(platform, chat_id_str, "Товар не найден.", inline_keyboard=build_catalog_list_keyboard())
            return
        send_admin_message(
            platform,
            chat_id_str,
            f"📦 Товар #{item['id']}\n{item['title']}\n\nЦена: {format_price(item['total_price'])}",
            inline_keyboard=build_catalog_item_keyboard(item_id),
        )
        return

    if data.startswith("catalog:delete:"):
        item_id = int(data.split(":", maxsplit=2)[2])
        deleted = delete_catalog_item(item_id)
        if not deleted:
            send_admin_message(platform, chat_id_str, "Товар не найден.", inline_keyboard=build_catalog_list_keyboard())
            return
        send_admin_message(
            platform,
            chat_id_str,
            "🗑 Товар удалён из каталога.",
            inline_keyboard=build_catalog_list_keyboard(),
        )
        return

    if data.startswith("create:item:"):
        item_id = int(data.split(":", maxsplit=2)[2])
        item = find_catalog_item_by_id(item_id)
        if not item:
            send_admin_message(platform, chat_id_str, "Товар не найден.", inline_keyboard=build_catalog_pick_keyboard())
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
            f"Товар выбран:\n{item['title']}\nЦена: {format_price(item['total_price'])}\n\nВыбери, сколько уже оплачено:",
            inline_keyboard=build_payment_choice_keyboard(),
        )
        return

    if data.startswith("create:payment:"):
        percent_key = data.split(":", maxsplit=2)[2]
        percent = PAYMENT_OPTIONS.get(percent_key)
        state_for_chat = conversation_state.get(actor_key(platform, chat_id_str))
        if percent is None or not state_for_chat:
            send_admin_message(platform, chat_id_str, "Не удалось выбрать оплату. Начни создание заказа заново.")
            return
        draft = dict(state_for_chat.get("draft", {}))
        draft["paid_amount"] = round(draft["total_price"] * percent / 100)
        set_conversation(actor_key(platform, chat_id_str), "awaiting_delivery_choice", draft=draft)
        send_admin_message(
            platform,
            chat_id_str,
            (
                f"{draft['title']}\n"
                f"Цена: {format_price(draft['total_price'])}\n"
                f"Оплачено: {percent}% ({format_price(draft['paid_amount'])} из {format_price(draft['total_price'])})\n\n"
                "Нужна доставка?"
            ),
            inline_keyboard=build_delivery_choice_keyboard(),
        )
        return

    if data.startswith("create:delivery:"):
        state_for_chat = conversation_state.get(actor_key(platform, chat_id_str))
        if not state_for_chat:
            send_admin_message(platform, chat_id_str, "Не удалось выбрать доставку. Начни создание заказа заново.")
            return
        draft = dict(state_for_chat.get("draft", {}))
        draft["has_delivery"] = data.endswith(":yes")
        set_conversation(actor_key(platform, chat_id_str), "awaiting_notes", draft=draft)
        send_admin_message(
            platform,
            chat_id_str,
            (
                f"{draft['title']}\n"
                f"Цена: {format_price(draft['total_price'])}\n"
                f"Оплачено: {get_paid_text({'paid_amount': draft['paid_amount'], 'total_price': draft['total_price']})}\n"
                f"Доставка: {'Да' if draft['has_delivery'] else 'Нет'}\n\n"
                "Теперь отправь примечание. Если примечания нет — отправь одиночный символ -"
            ),
        )
        return

    if data == "admin:list":
        send_admin_message(platform, chat_id_str, build_orders_list_text(), inline_keyboard=build_orders_list_keyboard())
        return

    if data.startswith("admin:view:"):
        order_id = int(data.split(":", maxsplit=2)[2])
        order = find_order_by_id(order_id)
        if not order:
            send_admin_message(platform, chat_id_str, "Заказ не найден или уже удалён.", inline_keyboard=build_orders_list_keyboard())
            return
        send_admin_message(
            platform,
            chat_id_str,
            render_order_text(order, for_admin=True),
            inline_keyboard=build_admin_order_keyboard(order),
        )
        return

    if data.startswith("admin:status:"):
        _, _, order_id_str, status_key = data.split(":", maxsplit=3)
        order = find_order_by_id(int(order_id_str))
        if not order:
            send_admin_message(platform, chat_id_str, "Заказ не найден или уже удалён.", inline_keyboard=build_orders_list_keyboard())
            return
        allowed_statuses = get_status_keys(order["has_delivery"])
        if status_key not in allowed_statuses:
            send_admin_message(platform, chat_id_str, "Этот статус недоступен для выбранного заказа.")
            return
        if status_key == "awaiting_delivery":
            set_conversation(actor_key(platform, chat_id_str), "awaiting_delivery_schedule", order_id=order["id"])
            send_admin_message(platform, chat_id_str, "Укажи дату и время доставки, например: 20 января, 20:00")
            return
        update_order_status(order, status_key)
        notify_customer_order_update(order, f"По заказу #{order['id']} обновлён статус: {get_status_label(status_key)}.")
        send_admin_message(
            platform,
            chat_id_str,
            render_order_text(order, for_admin=True),
            inline_keyboard=build_admin_order_keyboard(order),
        )
        return

    if data.startswith("admin:delivery_toggle:"):
        order_id = int(data.split(":", maxsplit=2)[2])
        order = find_order_by_id(order_id)
        if not order:
            send_admin_message(platform, chat_id_str, "Заказ не найден или уже удалён.", inline_keyboard=build_orders_list_keyboard())
            return
        update_delivery_flag(order, not order["has_delivery"])
        notify_customer_order_update(
            order,
            f"По заказу #{order['id']} изменён способ получения: {'доставка' if order['has_delivery'] else 'самовывоз'}.",
        )
        send_admin_message(
            platform,
            chat_id_str,
            render_order_text(order, for_admin=True),
            inline_keyboard=build_admin_order_keyboard(order),
        )
        return

    if data.startswith("admin:payment_full:"):
        order_id = int(data.split(":", maxsplit=2)[2])
        order = find_order_by_id(order_id)
        if not order:
            send_admin_message(platform, chat_id_str, "Заказ не найден или уже удалён.", inline_keyboard=build_orders_list_keyboard())
            return
        mark_fully_paid(order)
        notify_customer_order_update(order, f"По заказу #{order['id']} отмечена полная оплата.")
        send_admin_message(
            platform,
            chat_id_str,
            render_order_text(order, for_admin=True),
            inline_keyboard=build_admin_order_keyboard(order),
        )
        return

    if data.startswith("admin:payment_add:"):
        order_id = int(data.split(":", maxsplit=2)[2])
        order = find_order_by_id(order_id)
        if not order:
            send_admin_message(platform, chat_id_str, "Заказ не найден или уже удалён.", inline_keyboard=build_orders_list_keyboard())
            return
        set_conversation(actor_key(platform, chat_id_str), "awaiting_payment_add", order_id=order_id)
        send_admin_message(platform, chat_id_str, "Введи сумму доплаты в рублях, например: 5000")
        return

    if data.startswith("admin:finish:"):
        order_id = int(data.split(":", maxsplit=2)[2])
        order = find_order_by_id(order_id)
        if not order:
            send_admin_message(platform, chat_id_str, "Заказ не найден или уже удалён.", inline_keyboard=build_orders_list_keyboard())
            return
        send_admin_message(
            platform,
            chat_id_str,
            f"Завершить заказ #{order['id']}?\nПосле подтверждения клиент получит сообщение с благодарностью.",
            inline_keyboard=build_finish_confirmation_keyboard(order_id),
        )
        return

    if data.startswith("admin:finish_yes:"):
        order_id = int(data.split(":", maxsplit=2)[2])
        order = find_order_by_id(order_id)
        if not order:
            send_admin_message(platform, chat_id_str, "Заказ не найден или уже удалён.", inline_keyboard=build_orders_list_keyboard())
            return
        complete_order(order)
        notify_customer_order_completed(order)
        send_admin_message(
            platform,
            chat_id_str,
            f"✅ Заказ #{order['id']} завершён.",
            inline_keyboard={"inline_keyboard": [[{"text": "К списку заказов", "callback_data": "admin:list"}]]},
        )
        return

    if data.startswith("admin:finish_no:"):
        order_id = int(data.split(":", maxsplit=2)[2])
        order = find_order_by_id(order_id)
        if not order:
            send_admin_message(platform, chat_id_str, "Заказ не найден или уже удалён.", inline_keyboard=build_orders_list_keyboard())
            return
        send_admin_message(
            platform,
            chat_id_str,
            render_order_text(order, for_admin=True),
            inline_keyboard=build_admin_order_keyboard(order),
        )
        return

    if data.startswith("admin:delete:"):
        order_id = int(data.split(":", maxsplit=2)[2])
        order = find_order_by_id(order_id)
        if not order:
            send_admin_message(platform, chat_id_str, "Заказ не найден или уже удалён.", inline_keyboard=build_orders_list_keyboard())
            return
        send_admin_message(
            platform,
            chat_id_str,
            f"Удалить заказ #{order['id']} без возможности восстановления?",
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
                        f"Заказ #{order['id']} удалён из системы отслеживания.\n"
                        "Если вы считаете, что это произошло без вашего уведомления, напишите нам по кнопке ниже."
                    ),
                    reply_markup=build_public_keyboard(binding["platform"], binding["chat_id"]),
                )
        deleted = delete_order(order_id)
        if not deleted:
            send_admin_message(platform, chat_id_str, "Заказ не найден или уже удалён.", inline_keyboard=build_orders_list_keyboard())
            return
        send_admin_message(
            platform,
            chat_id_str,
            f"🗑 Заказ #{order_id} удалён.",
            inline_keyboard={"inline_keyboard": [[{"text": "К списку заказов", "callback_data": "admin:list"}]]},
        )
        return

    if data.startswith("admin:delete_no:"):
        order_id = int(data.split(":", maxsplit=2)[2])
        order = find_order_by_id(order_id)
        if not order:
            send_admin_message(platform, chat_id_str, "Заказ не найден или уже удалён.", inline_keyboard=build_orders_list_keyboard())
            return
        send_admin_message(
            platform,
            chat_id_str,
            render_order_text(order, for_admin=True),
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



def extract_max_chat_id_from_message(message: dict[str, Any]) -> str | None:
    sender = message.get("sender") if isinstance(message, dict) else None
    if isinstance(sender, dict) and sender.get("user_id") is not None:
        return str(sender["user_id"])
    recipient = message.get("recipient") if isinstance(message, dict) else None
    if isinstance(recipient, dict):
        if recipient.get("chat_id") is not None:
            return str(recipient["chat_id"])
        if recipient.get("user_id") is not None:
            return str(recipient["user_id"])
        chat = recipient.get("chat")
        if isinstance(chat, dict) and chat.get("chat_id") is not None:
            return str(chat["chat_id"])
        user = recipient.get("user")
        if isinstance(user, dict) and user.get("user_id") is not None:
            return str(user["user_id"])
    return None



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
        send_admin_message("telegram", str(chat_id), "Поддерживаются текстовые команды и сообщения.")
    else:
        send_public_welcome("telegram", str(chat_id))



def handle_max_update(update: dict[str, Any]) -> None:
    update_type = str(update.get("update_type") or "")
    if update_type == "bot_started":
        chat_id = update.get("chat_id")
        if chat_id is None:
            return
        payload = str(update.get("payload") or "")
        handle_public_start("max", str(chat_id), payload)
        return

    if update_type == "message_callback":
        message = update.get("message") or {}
        callback = update.get("callback") or {}
        chat_id = extract_max_chat_id_from_message(message)
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
        return

    if is_admin("max", chat_id):
        send_admin_message("max", chat_id, "Поддерживаются текстовые команды и сообщения.")
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
    if payload.get("marker") is not None:
        state["max_marker"] = payload.get("marker")
        save_state()
    return payload.get("updates", [])



def initialize_telegram_profile() -> None:
    if not platform_enabled("telegram"):
        return
    payload = telegram_api_request("getMe")
    result = payload.get("result", {})
    bot_profiles["telegram"]["username"] = result.get("username")
    bot_profiles["telegram"]["name"] = result.get("first_name")
    if not bot_profiles["telegram"]["username"]:
        raise RuntimeError("У Telegram-бота не найден username. Укажи username через @BotFather.")



def initialize_max_profile() -> None:
    if not platform_enabled("max"):
        return
    result = max_api_request("GET", "/me")
    bot_profiles["max"]["username"] = result.get("username")
    bot_profiles["max"]["name"] = result.get("first_name") or result.get("name")
    if not bot_profiles["max"]["username"]:
        raise RuntimeError("У MAX-бота не найден username. Проверь настройки бота в MAX.")



def run_telegram_polling(stop_event: threading.Event) -> None:
    while not stop_event.is_set():
        try:
            telegram_updates = fetch_telegram_updates()
            for update in telegram_updates:
                try:
                    with state_lock:
                        handle_telegram_update(update)
                except requests.exceptions.RequestException as exc:
                    print(f"❌ Ошибка requests при обработке Telegram update {update.get('update_id')}: {exc}")
                except RuntimeError as exc:
                    print(f"⚠️ Ошибка Telegram API при обработке update {update.get('update_id')}: {exc}")
                finally:
                    with state_lock:
                        state["telegram_last_update_id"] = update.get("update_id")
                        save_state()
        except requests.exceptions.Timeout:
            print("⏳ Таймаут Telegram long polling, продолжаю работу...")
        except requests.exceptions.ConnectionError:
            print("🌐 Ошибка соединения Telegram, повтор через несколько секунд...")
            time.sleep(5)
        except requests.exceptions.RequestException as exc:
            print(f"❌ Ошибка requests Telegram: {exc}")
            time.sleep(5)
        except RuntimeError as exc:
            print(f"⚠️ Ошибка Telegram API: {exc}")
            time.sleep(5)



def run_max_polling(stop_event: threading.Event) -> None:
    while not stop_event.is_set():
        try:
            max_updates = fetch_max_updates()
            for update in max_updates:
                try:
                    with state_lock:
                        handle_max_update(update)
                except requests.exceptions.RequestException as exc:
                    print(f"❌ Ошибка requests при обработке MAX update {update.get('timestamp')}: {exc}")
                except RuntimeError as exc:
                    print(f"⚠️ Ошибка MAX API при обработке update {update.get('timestamp')}: {exc}")
        except requests.exceptions.Timeout:
            print("⏳ Таймаут MAX long polling, продолжаю работу...")
        except requests.exceptions.ConnectionError:
            print("🌐 Ошибка соединения MAX, повтор через несколько секунд...")
            time.sleep(5)
        except requests.exceptions.RequestException as exc:
            print(f"❌ Ошибка requests MAX: {exc}")
            time.sleep(5)
        except RuntimeError as exc:
            print(f"⚠️ Ошибка MAX API: {exc}")
            time.sleep(5)



def main() -> None:
    initialize_telegram_profile()
    initialize_max_profile()
    with state_lock:
        sync_archives()
    print("🤖 CULT_BOT запущен")
    print(f"🕒 Часовой пояс: {TIMEZONE_NAME}")
    print(f"🗃 Архив заказов: {ARCHIVE_DIR}")
    if platform_enabled("telegram"):
        print(f"📨 Telegram admin chat_id={TELEGRAM_ADMIN_CHAT_ID}")
        print(f"🔗 Telegram deep-link: @{bot_profiles['telegram']['username']}")
    if platform_enabled("max"):
        print(f"📨 MAX admin chat_id={MAX_ADMIN_CHAT_ID}")
        print(f"🔗 MAX deep-link: @{bot_profiles['max']['username']}")
        print("⚠️ MAX long polling подходит для разработки; для production документация MAX рекомендует Webhook.")

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
        print("\n👋 Выход...")
        stop_event.set()
        for worker in workers:
            worker.join(timeout=1)


if __name__ == "__main__":
    main()
