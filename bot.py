import json
import os
import re
import secrets
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


TOKEN = get_env_value("TOKEN")
ADMIN_CHAT_ID = get_env_value("ADMIN_CHAT_ID")
PROXY = get_env_value("PROXY")
TIMEZONE_NAME = get_env_value("TIMEZONE", "UTC")
ORDERS_FILE = resolve_runtime_file("ORDERS_FILE", "orders.json")
STATE_FILE = resolve_runtime_file("STATE_FILE", "bot_state.json")
ARCHIVE_DIR = Path(get_env_value("ARCHIVE_DIR", "archive"))
ALLOWED_PROXY_SCHEMES = {"http", "https", "socks5", "socks5h"}
POLL_TIMEOUT_SECONDS = 10
REQUEST_TIMEOUT_SECONDS = 20
LOOP_INTERVAL_SECONDS = 2
MAX_TITLE_LENGTH = 200
MAX_PRICE_LENGTH = 60
MAX_NOTES_LENGTH = 1000
CONTACT_URL = "https://t.me/cultmebel?direct"
VK_URL = "https://vk.com/cultmebel"
TG_URL = "https://t.me/cultmebel"

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

if not TOKEN:
    raise ValueError("❌ Не найден TOKEN в .env")

if not ADMIN_CHAT_ID:
    raise ValueError("❌ Не найден ADMIN_CHAT_ID в .env")

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

session = requests.Session()
session.trust_env = False
if PROXY:
    session.proxies.update({"http": PROXY, "https": PROXY})

API_BASE_URL = f"https://api.telegram.org/bot{TOKEN}"
conversation_state: dict[str, dict[str, Any]] = {}
bot_profile: dict[str, Any] = {"username": None, "name": None}



def api_request(method: str, *, data: dict[str, Any] | None = None) -> dict[str, Any]:
    response = session.post(
        f"{API_BASE_URL}/{method}",
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



def load_json(path: Path, fallback: Any) -> Any:
    if not path.exists():
        return fallback

    try:
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)
    except (OSError, json.JSONDecodeError):
        return fallback


state = load_json(STATE_FILE, {"last_update_id": None})
orders: list[dict[str, Any]] = load_json(ORDERS_FILE, [])



def ensure_parent_dir(path: Path) -> None:
    parent = path.parent
    if parent != Path("") and not parent.exists():
        parent.mkdir(parents=True, exist_ok=True)



def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)



def save_state() -> None:
    ensure_parent_dir(STATE_FILE)
    STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )



def save_orders() -> None:
    ensure_parent_dir(ORDERS_FILE)
    ORDERS_FILE.write_text(
        json.dumps(orders, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )



def parse_rubles(raw_value: str | int) -> int:
    if isinstance(raw_value, int):
        return max(raw_value, 0)
    cleaned = re.sub(r"(руб\.?|р\.?|₽|\s|[.,])", "", str(raw_value).lower())
    if not cleaned.isdigit():
        raise ValueError("Укажи сумму в рублях числом, например 21000.")
    return int(cleaned)



def get_timezone_label() -> str:
    now_local = datetime.now(LOCAL_TZ)
    offset = now_local.utcoffset() or timedelta(0)
    total_minutes = int(offset.total_seconds() // 60)
    sign = "+" if total_minutes >= 0 else "-"
    total_minutes = abs(total_minutes)
    hours, minutes = divmod(total_minutes, 60)
    return f"UTC{sign}{hours:02d}:{minutes:02d}"


def migrate_order(order: dict[str, Any]) -> dict[str, Any]:
    migrated = dict(order)
    if migrated.get("status") == "ready_waiting_delivery":
        migrated["status"] = "awaiting_delivery"

    total_price = migrated.get("total_price")
    if total_price is None:
        raw_price = migrated.get("price", "0")
        total_price = parse_rubles(raw_price)
    migrated["total_price"] = total_price
    migrated["price"] = f"{total_price:,}".replace(",", ".") + " ₽"

    paid_amount = migrated.get("paid_amount")
    if paid_amount is None:
        payment_percent = int(migrated.get("payment_percent", 0) or 0)
        paid_amount = round(total_price * payment_percent / 100)
    migrated["paid_amount"] = max(0, min(int(paid_amount), total_price))

    migrated.setdefault("notes", "")
    migrated.setdefault("customer_chat_id", None)
    migrated.setdefault("completed_at", None)
    migrated.setdefault("updated_at", migrated.get("created_at", now_utc_iso()))
    migrated.setdefault("delivery_planned_for", None)
    migrated.setdefault("history", [])
    return migrated


orders = [migrate_order(order) for order in orders]
state.setdefault("next_order_id", max((item["id"] for item in orders), default=0) + 1)



def json_dumps(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False)



def send_message(
    chat_id: str,
    text: str,
    *,
    reply_markup: dict[str, Any] | None = None,
    disable_web_page_preview: bool = True,
    parse_mode: str | None = None,
) -> None:
    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": disable_web_page_preview,
    }
    if reply_markup:
        payload["reply_markup"] = json_dumps(reply_markup)
    if parse_mode:
        payload["parse_mode"] = parse_mode
    api_request("sendMessage", data=payload)



def edit_message(
    chat_id: str,
    message_id: int,
    text: str,
    *,
    reply_markup: dict[str, Any] | None = None,
    disable_web_page_preview: bool = True,
) -> None:
    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "message_id": str(message_id),
        "text": text,
        "disable_web_page_preview": disable_web_page_preview,
    }
    if reply_markup:
        payload["reply_markup"] = json_dumps(reply_markup)
    api_request("editMessageText", data=payload)



def answer_callback_query(callback_query_id: str, text: str = "") -> None:
    payload: dict[str, Any] = {"callback_query_id": callback_query_id}
    if text:
        payload["text"] = text
    api_request("answerCallbackQuery", data=payload)



def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()



def format_local_time(iso_timestamp: str | None) -> str:
    if not iso_timestamp:
        return "—"
    dt_utc = datetime.fromisoformat(iso_timestamp)
    dt_local = dt_utc.astimezone(LOCAL_TZ)
    return f"{dt_local.strftime('%Y-%m-%d %H:%M')} {get_timezone_label()}"



def is_admin(chat_id: int) -> bool:
    return str(chat_id) == str(ADMIN_CHAT_ID)



def set_conversation(chat_id: str, step: str, **extra: Any) -> None:
    conversation_state[chat_id] = {"step": step, **extra}



def clear_conversation(chat_id: str) -> None:
    conversation_state.pop(chat_id, None)



def next_order_id() -> int:
    order_id = int(state.get("next_order_id", max((item["id"] for item in orders), default=0) + 1))
    state["next_order_id"] = order_id + 1
    save_state()
    return order_id



def generate_order_token() -> str:
    existing_tokens = {item["token"] for item in orders}
    while True:
        token = secrets.token_urlsafe(8)
        if token not in existing_tokens:
            return token


def find_orders_for_customer(chat_id: str) -> list[dict[str, Any]]:
    return sorted(
        [order for order in orders if order.get("customer_chat_id") == chat_id],
        key=lambda item: item["id"],
        reverse=True,
    )


def has_customer_orders(chat_id: str) -> bool:
    return bool(find_orders_for_customer(chat_id))



def get_status_keys(has_delivery: bool) -> list[str]:
    keys = list(BASE_STATUS_KEYS)
    if has_delivery:
        keys.extend(DELIVERY_EXTRA_STATUS_KEYS)
    return keys



def get_status_label(status_key: str) -> str:
    return STATUS_LABELS.get(status_key, status_key)


def format_price(value: int) -> str:
    return f"{value:,}".replace(",", ".") + " ₽"


def normalize_price(raw_value: str) -> str:
    cleaned = raw_value.strip()
    numeric_candidate = re.sub(r"(руб\.?|р\.?|₽|\s|[.,])", "", cleaned.lower())
    if numeric_candidate.isdigit():
        return format_price(int(numeric_candidate))
    return cleaned


def calculate_payment_percent(order: dict[str, Any]) -> int:
    total_price = max(order["total_price"], 1)
    return round(order["paid_amount"] * 100 / total_price)


def get_paid_text(order: dict[str, Any]) -> str:
    return (
        f"{calculate_payment_percent(order)}% "
        f"({format_price(order['paid_amount'])} из {format_price(order['total_price'])})"
    )


def format_order_link(token: str) -> str:
    username = bot_profile.get("username")
    if not username:
        return f"Токен заказа: {token}"
    return f"https://t.me/{username}?start=order_{token}"


def archive_file_path(order_id: int) -> Path:
    return ARCHIVE_DIR / f"order_{order_id:05d}.txt"


def append_history(order: dict[str, Any], text: str) -> None:
    order.setdefault("history", []).append(
        {
            "timestamp": now_utc_iso(),
            "text": text,
        }
    )


def write_order_archive(order: dict[str, Any], lifecycle_state: str) -> None:
    ensure_dir(ARCHIVE_DIR)
    history_lines = order.get("history", [])
    lines = [
        f"Заказ #{order['id']}",
        f"Состояние: {lifecycle_state}",
        f"Наименование: {order['title']}",
        f"Цена: {format_price(order['total_price'])}",
        f"Оплачено: {get_paid_text(order)}",
        f"Статус: {get_status_label(order['status'])}",
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
                "customer_chat_id": order.get("customer_chat_id"),
                "history": history_lines,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    archive_file_path(order["id"]).write_text("\n".join(lines), encoding="utf-8")


def persist_order(order: dict[str, Any], lifecycle_state: str = "active") -> None:
    order["price"] = format_price(order["total_price"])
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
) -> dict[str, Any]:
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
        "created_at": now_utc_iso(),
        "updated_at": now_utc_iso(),
        "completed_at": None,
        "customer_chat_id": None,
        "delivery_planned_for": None,
        "history": [],
    }
    append_history(order, "Заказ создан.")
    orders.append(order)
    persist_order(order)
    return order



def update_order_status(order: dict[str, Any], status_key: str) -> None:
    order["status"] = status_key
    if status_key != "awaiting_delivery":
        order["delivery_planned_for"] = None
    order["updated_at"] = now_utc_iso()
    append_history(order, f"Статус изменён на «{get_status_label(status_key)}».")
    persist_order(order)


def set_delivery_schedule(order: dict[str, Any], schedule_text: str) -> None:
    order["status"] = "awaiting_delivery"
    order["delivery_planned_for"] = schedule_text
    order["updated_at"] = now_utc_iso()
    append_history(order, f"Доставка запланирована на {schedule_text}.")
    persist_order(order)


def update_delivery_flag(order: dict[str, Any], has_delivery: bool) -> None:
    order["has_delivery"] = has_delivery
    if not has_delivery and order.get("status") in DELIVERY_EXTRA_STATUS_KEYS:
        order["status"] = "ready"
        order["delivery_planned_for"] = None
    order["updated_at"] = now_utc_iso()
    append_history(order, f"Доставка изменена: {'Да' if has_delivery else 'Нет'}")
    persist_order(order)


def add_payment(order: dict[str, Any], amount: int) -> None:
    order["paid_amount"] = min(order["total_price"], order["paid_amount"] + amount)
    order["updated_at"] = now_utc_iso()
    append_history(order, f"Получена доплата: {format_price(amount)}.")
    persist_order(order)


def mark_fully_paid(order: dict[str, Any]) -> None:
    order["paid_amount"] = order["total_price"]
    order["updated_at"] = now_utc_iso()
    append_history(order, "Заказ оплачен полностью.")
    persist_order(order)



def delete_order(order_id: int) -> bool:
    for index, order in enumerate(orders):
        if order["id"] == order_id:
            order["updated_at"] = now_utc_iso()
            append_history(order, "Заказ удалён из активного интерфейса.")
            write_order_archive(order, "deleted")
            del orders[index]
            save_orders()
            return True
    return False



def complete_order(order: dict[str, Any]) -> None:
    order["status"] = "completed"
    order["completed_at"] = now_utc_iso()
    order["updated_at"] = now_utc_iso()
    append_history(order, "Заказ завершён.")
    persist_order(order, "completed")



def build_public_keyboard(
    chat_id: str | None = None,
    include_refresh_token: str | None = None,
) -> dict[str, Any]:
    keyboard: list[list[dict[str, Any]]] = []
    if include_refresh_token:
        keyboard.append(
            [{"text": "Обновить статус", "callback_data": f"client:refresh:{include_refresh_token}"}]
        )
    if chat_id and has_customer_orders(chat_id):
        keyboard.append([{"text": "Мои заказы", "callback_data": "client:list"}])
    keyboard.extend(
        [
            [{"text": "Связаться", "url": CONTACT_URL}],
            [{"text": "Соц.сети Культ Мебель", "callback_data": "public:socials"}],
        ]
    )
    return {"inline_keyboard": keyboard}


def build_customer_orders_text(chat_id: str) -> str:
    customer_orders = find_orders_for_customer(chat_id)
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
                    f"#{order['id']} • {order['title']}",
                    f"Статус: {get_status_label(order['status'])}",
                    f"Цена: {format_price(order['total_price'])}",
                    f"Оплачено: {get_paid_text(order)}",
                    f"Создан: {format_local_time(order['created_at'])}",
                ]
            )
        )
    return "\n\n".join(lines)


def build_customer_orders_keyboard(chat_id: str) -> dict[str, Any]:
    rows: list[list[dict[str, Any]]] = []
    for order in find_orders_for_customer(chat_id):
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
    inline_keyboard.append(
        [{"text": "К списку заказов", "callback_data": "admin:list"}]
    )
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



def build_status_choice_keyboard(has_delivery: bool) -> dict[str, Any]:
    buttons = [
        {"text": get_status_label(status_key), "callback_data": f"create_status:{status_key}"}
        for status_key in get_status_keys(has_delivery)
    ]
    return {"inline_keyboard": chunk_buttons(buttons, 2)}



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
                    f"#{order['id']} • {order['title']}",
                    f"Статус: {get_status_label(order['status'])}",
                    f"Оплачено: {get_paid_text(order)}",
                    f"Создан: {format_local_time(order['created_at'])}",
                ]
            )
        )
    return "\n\n".join(lines)



def build_orders_list_keyboard() -> dict[str, Any] | None:
    active_orders = build_active_orders()
    if not active_orders:
        return None

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
    return {"inline_keyboard": rows}



def render_order_text(order: dict[str, Any], *, for_admin: bool) -> str:
    lines = [
        f"📦 Заказ #{order['id']}",
        f"Наименование: {order['title']}",
        f"Цена: {format_price(order['total_price'])}",
        f"Оплачено: {get_paid_text(order)}",
        f"Статус: {get_status_label(order['status'])}",
        f"Доставка: {'Да' if order['has_delivery'] else 'Нет'}",
        f"Создан: {format_local_time(order['created_at'])}",
    ]

    if order.get("notes"):
        lines.append(f"Примечание: {order['notes']}")
    else:
        lines.append("Примечание: —")

    if for_admin:
        lines.append(f"Ссылка для клиента: {format_order_link(order['token'])}")
        lines.append(
            f"Клиент открыл заказ: {'Да' if order.get('customer_chat_id') else 'Нет'}"
        )
        if order.get("completed_at"):
            lines.append(f"Завершён: {format_local_time(order['completed_at'])}")
    else:
        lines.append("Срок изготовления указан в оферте.")
        if order.get("paid_amount", 0) < order.get("total_price", 0):
            lines.append("Если вам необходимо доплатить, нажмите кнопку «Связаться».")
        if order["status"] == "ready":
            if order["has_delivery"]:
                lines.append(
                    "В ближайшее время мы напишем вам для уточнения вопроса доставки. Если нужно быстрее — нажмите «Связаться»."
                )
            else:
                lines.append(
                    "В ближайшее время мы напишем вам для уточнения вопроса самовывоза. Если нужно быстрее — нажмите «Связаться»."
                )
        if order["status"] == "awaiting_delivery" and order.get("delivery_planned_for"):
            lines.append(f"Доставка запланирована на {order['delivery_planned_for']}.")
        if order["status"] == "completed":
            lines.append("Спасибо за заказ! Если понадобится ещё мебель — мы на связи.")

    return "\n".join(lines)



def send_order_snapshot(chat_id: str, order: dict[str, Any]) -> None:
    send_message(
        chat_id,
        render_order_text(order, for_admin=False),
        reply_markup=build_public_keyboard(chat_id, order["token"]),
    )



def send_customer_orders(chat_id: str) -> None:
    send_message(
        chat_id,
        build_customer_orders_text(chat_id),
        reply_markup=build_customer_orders_keyboard(chat_id),
    )



def notify_customer_order_update(order: dict[str, Any], intro_text: str) -> None:
    customer_chat_id = order.get("customer_chat_id")
    if not customer_chat_id:
        return
    send_message(
        str(customer_chat_id),
        f"{intro_text}\n\n{render_order_text(order, for_admin=False)}",
        reply_markup=build_public_keyboard(str(customer_chat_id), order["token"]),
    )



def send_public_welcome(chat_id: str) -> None:
    send_message(
        chat_id,
        (
            "Привет! Это бот отслеживания заказов Культ Мебель.\n\n"
            "Если вам отправили персональную ссылку на заказ, просто откройте её — бот покажет статус, оплату и примечания.\n"
            "Чтобы оформить заказ, напишите нам напрямую."
        ),
        reply_markup=build_public_keyboard(chat_id),
    )



def send_socials_message(chat_id: str) -> None:
    send_message(
        chat_id,
        "Соцсети Культ Мебель:",
        reply_markup=build_socials_keyboard(),
    )



def send_admin_help(chat_id: str) -> None:
    send_message(
        chat_id,
        (
            "Привет! Я бот для отслеживания заказов.\n\n"
            "Команды:\n"
            "/neworder — создать новый заказ\n"
            "/orders — список текущих заказов\n"
            "/report — отчёт по периоду\n"
            "/cancel — отменить текущее действие"
        ),
    )



def prompt_for_order_status(chat_id: str, draft: dict[str, Any]) -> None:
    set_conversation(str(chat_id), "awaiting_status", draft=draft)
    send_message(
        str(chat_id),
        "Выбери стартовый статус заказа:",
        reply_markup=build_status_choice_keyboard(draft["has_delivery"]),
    )



def parse_payment_percent(raw_value: str) -> int:
    cleaned = raw_value.strip().replace("%", "")
    if not cleaned.isdigit():
        raise ValueError("Укажи оплату целым числом от 0 до 100.")
    value = int(cleaned)
    if value < 0 or value > 100:
        raise ValueError("Процент оплаты должен быть от 0 до 100.")
    return value


def parse_paid_amount(raw_value: str) -> int:
    return parse_rubles(raw_value)


def parse_russian_period(raw_value: str) -> tuple[datetime, datetime]:
    cleaned = raw_value.strip()
    if "_" not in cleaned:
        raise ValueError("Используй формат периода: 22 января 2025_1 сентября 2025")

    start_raw, end_raw = [item.strip().lower() for item in cleaned.split("_", maxsplit=1)]

    def parse_single(value: str, *, end_of_day: bool) -> datetime:
        match = re.fullmatch(r"(\d{1,2})\s+([а-яё]+)\s+(\d{4})", value)
        if not match:
            raise ValueError("Используй формат периода: 22 января 2025_1 сентября 2025")
        day = int(match.group(1))
        month_name = match.group(2)
        year = int(match.group(3))
        month = RUSSIAN_MONTHS.get(month_name)
        if month is None:
            raise ValueError(f"Не удалось распознать месяц: {month_name}")
        hour = 23 if end_of_day else 0
        minute = 59 if end_of_day else 0
        second = 59 if end_of_day else 0
        return datetime(year, month, day, hour, minute, second, tzinfo=LOCAL_TZ).astimezone(timezone.utc)

    start_dt = parse_single(start_raw, end_of_day=False)
    end_dt = parse_single(end_raw, end_of_day=True)
    if end_dt < start_dt:
        raise ValueError("Конец периода не может быть раньше начала.")
    return start_dt, end_dt



def build_report_text(start_dt: datetime, end_dt: datetime) -> str:
    archived_orders = load_archived_orders()
    filtered_orders = []
    for order in archived_orders:
        created_at = order.get("created_at")
        if not created_at:
            continue
        created_dt = datetime.fromisoformat(created_at)
        if start_dt <= created_dt <= end_dt:
            filtered_orders.append(order)

    if not filtered_orders:
        return (
            "📊 За указанный период заказов не найдено.\n"
            f"Период: {format_local_time(start_dt.isoformat())} — {format_local_time(end_dt.isoformat())}"
        )

    total_price = sum(int(order.get("total_price", 0)) for order in filtered_orders)
    total_paid = sum(int(order.get("paid_amount", 0)) for order in filtered_orders)
    completed_count = sum(1 for order in filtered_orders if order.get("lifecycle_state") == "completed")
    deleted_count = sum(1 for order in filtered_orders if order.get("lifecycle_state") == "deleted")
    active_count = len(filtered_orders) - completed_count - deleted_count

    return "\n".join(
        [
            "📊 Отчёт по заказам:",
            f"Период: {format_local_time(start_dt.isoformat())} — {format_local_time(end_dt.isoformat())}",
            f"Всего заказов: {len(filtered_orders)}",
            f"Активные: {active_count}",
            f"Завершённые: {completed_count}",
            f"Удалённые: {deleted_count}",
            f"Сумма заказов: {format_price(total_price)}",
            f"Получено оплат: {format_price(total_paid)}",
            f"Осталось получить: {format_price(max(total_price - total_paid, 0))}",
        ]
    )



def handle_command(chat_id: int, text: str) -> None:
    stripped = text.strip()
    if not is_admin(chat_id):
        if stripped.startswith("/start"):
            parts = stripped.split(maxsplit=1)
            payload = parts[1].strip() if len(parts) > 1 else ""
            handle_public_start(chat_id, payload)
            return
        send_public_welcome(str(chat_id))
        return

    if stripped.startswith("/start"):
        clear_conversation(str(chat_id))
        send_admin_help(str(chat_id))
        return

    if stripped == "/neworder":
        set_conversation(str(chat_id), "awaiting_title")
        send_message(str(chat_id), "Введите наименование заказа, например: Кровать Milano 160x200")
        return

    if stripped == "/orders":
        send_message(
            str(chat_id),
            build_orders_list_text(),
            reply_markup=build_orders_list_keyboard(),
        )
        return

    if stripped == "/report":
        set_conversation(str(chat_id), "awaiting_report_period")
        send_message(
            str(chat_id),
            "Введи период в формате: 22 января 2025_1 сентября 2025",
        )
        return

    if stripped == "/cancel":
        clear_conversation(str(chat_id))
        send_message(str(chat_id), "🛑 Текущее действие отменено.")
        return

    send_message(
        str(chat_id),
        "Неизвестная команда. Используй /neworder, /orders или /cancel.",
    )



def handle_public_start(chat_id: int, payload: str) -> None:
    if not payload.startswith("order_"):
        send_public_welcome(str(chat_id))
        return

    token = payload.removeprefix("order_").strip()
    order = find_order_by_token(token)
    if not order:
        send_message(
            str(chat_id),
            "Заказ по этой ссылке не найден или уже удалён. Напишите нам, и мы поможем уточнить информацию.",
            reply_markup=build_public_keyboard(str(chat_id)),
        )
        return

    if order.get("customer_chat_id") != str(chat_id):
        order["customer_chat_id"] = str(chat_id)
        order["updated_at"] = now_utc_iso()
        append_history(order, f"Клиент открыл персональную ссылку из чата {chat_id}.")
        persist_order(order, "completed" if order["status"] == "completed" else "active")

    send_order_snapshot(str(chat_id), order)



def handle_text_message(chat_id: int, text: str) -> None:
    if text.startswith("/"):
        handle_command(chat_id, text)
        return

    if not is_admin(chat_id):
        send_public_welcome(str(chat_id))
        return

    state_for_chat = conversation_state.get(str(chat_id))
    if not state_for_chat:
        send_message(
            str(chat_id),
            "Используй /neworder, чтобы создать заказ, или /orders, чтобы посмотреть список.",
        )
        return

    step = state_for_chat.get("step")
    cleaned_text = text.strip()

    if step == "awaiting_title":
        if not cleaned_text:
            send_message(str(chat_id), "Наименование не может быть пустым.")
            return
        if len(cleaned_text) > MAX_TITLE_LENGTH:
            send_message(str(chat_id), f"Наименование слишком длинное. Лимит — {MAX_TITLE_LENGTH} символов.")
            return
        set_conversation(str(chat_id), "awaiting_price", draft={"title": cleaned_text})
        send_message(str(chat_id), "Введите цену заказа, например: 42000. Бот сам покажет её как 42.000 ₽")
        return

    if step == "awaiting_price":
        if not cleaned_text:
            send_message(str(chat_id), "Цена не может быть пустой.")
            return
        if len(cleaned_text) > MAX_PRICE_LENGTH:
            send_message(str(chat_id), f"Цена слишком длинная. Лимит — {MAX_PRICE_LENGTH} символов.")
            return
        draft = dict(state_for_chat["draft"])
        draft["total_price"] = parse_rubles(cleaned_text)
        set_conversation(str(chat_id), "awaiting_payment", draft=draft)
        send_message(str(chat_id), "Сколько уже оплачено? Укажи сумму в рублях, например: 21000")
        return

    if step == "awaiting_payment":
        try:
            paid_amount = parse_paid_amount(cleaned_text)
        except ValueError as exc:
            send_message(str(chat_id), f"⚠️ {exc}")
            return
        draft = dict(state_for_chat["draft"])
        if paid_amount > draft["total_price"]:
            send_message(str(chat_id), "Оплаченная сумма не может быть больше полной цены заказа.")
            return
        draft["paid_amount"] = paid_amount
        set_conversation(str(chat_id), "awaiting_delivery", draft=draft)
        send_message(str(chat_id), "Нужна доставка? Ответь: Да или Нет")
        return

    if step == "awaiting_delivery":
        lowered = cleaned_text.lower()
        if lowered not in {"да", "нет"}:
            send_message(str(chat_id), "Ответь, пожалуйста: Да или Нет")
            return
        draft = dict(state_for_chat["draft"])
        draft["has_delivery"] = lowered == "да"
        set_conversation(str(chat_id), "awaiting_notes", draft=draft)
        send_message(
            str(chat_id),
            "Введите примечание к заказу. Если примечания нет — отправьте одиночный символ -",
        )
        return

    if step == "awaiting_notes":
        notes = "" if cleaned_text == "-" else cleaned_text
        if len(notes) > MAX_NOTES_LENGTH:
            send_message(str(chat_id), f"Примечание слишком длинное. Лимит — {MAX_NOTES_LENGTH} символов.")
            return
        draft = dict(state_for_chat["draft"])
        draft["notes"] = notes
        order = create_order(
            title=draft["title"],
            total_price=draft["total_price"],
            paid_amount=draft["paid_amount"],
            has_delivery=draft["has_delivery"],
            notes=draft["notes"],
        )
        clear_conversation(str(chat_id))
        send_message(
            str(chat_id),
            (
                "✅ Заказ создан.\n\n"
                f"{render_order_text(order, for_admin=True)}"
            ),
            reply_markup=build_admin_order_keyboard(order),
        )
        send_message(
            str(chat_id),
            (
                "Готовый текст для клиента:\n"
                f"Здравствуйте! Это персональная ссылка для отслеживания заказа #{order['id']} «{order['title']}».\n"
                "Откройте её, чтобы увидеть статус, оплату и примечания.\n\n"
                f"<code>{format_order_link(order['token'])}</code>"
            ),
            parse_mode="HTML",
        )
        return

    if step == "awaiting_payment_add":
        order = find_order_by_id(int(state_for_chat["order_id"]))
        if not order:
            clear_conversation(str(chat_id))
            send_message(str(chat_id), "Заказ не найден.")
            return
        try:
            amount = parse_paid_amount(cleaned_text)
        except ValueError as exc:
            send_message(str(chat_id), f"⚠️ {exc}")
            return
        add_payment(order, amount)
        clear_conversation(str(chat_id))
        notify_customer_order_update(
            order,
            f"По заказу #{order['id']} отмечена новая оплата: {format_price(amount)}.",
        )
        send_message(
            str(chat_id),
            f"✅ Оплата обновлена.\n\n{render_order_text(order, for_admin=True)}",
            reply_markup=build_admin_order_keyboard(order),
        )
        return

    if step == "awaiting_delivery_schedule":
        order = find_order_by_id(int(state_for_chat["order_id"]))
        if not order:
            clear_conversation(str(chat_id))
            send_message(str(chat_id), "Заказ не найден.")
            return
        if not cleaned_text:
            send_message(str(chat_id), "Укажи дату и время доставки, например: 20 января, 20:00")
            return
        set_delivery_schedule(order, cleaned_text)
        clear_conversation(str(chat_id))
        notify_customer_order_update(
            order,
            f"По заказу #{order['id']} обновлён статус: Ожидание доставки.",
        )
        send_message(
            str(chat_id),
            f"✅ Доставка запланирована.\n\n{render_order_text(order, for_admin=True)}",
            reply_markup=build_admin_order_keyboard(order),
        )
        return

    if step == "awaiting_report_period":
        try:
            start_dt, end_dt = parse_russian_period(cleaned_text)
        except ValueError as exc:
            send_message(str(chat_id), f"⚠️ {exc}")
            return
        clear_conversation(str(chat_id))
        send_message(str(chat_id), build_report_text(start_dt, end_dt))
        return

    send_message(str(chat_id), "Используй /cancel и начни заново через /neworder.")



def notify_customer_order_completed(order: dict[str, Any]) -> None:
    customer_chat_id = order.get("customer_chat_id")
    if not customer_chat_id:
        return
    send_message(
        str(customer_chat_id),
        (
            "Спасибо за ваш заказ в Культ Мебель! ❤️\n\n"
            f"{order['title']} отмечен как завершённый. Если понадобится помощь, мы всегда на связи."
        ),
        reply_markup=build_public_keyboard(str(customer_chat_id), order["token"]),
    )



def safe_edit_or_send(chat_id: str, message_id: int, text: str, reply_markup: dict[str, Any] | None = None) -> None:
    try:
        edit_message(chat_id, message_id, text, reply_markup=reply_markup)
    except (RuntimeError, requests.exceptions.RequestException):
        send_message(chat_id, text, reply_markup=reply_markup)


def safe_answer_callback_query(callback_query_id: str) -> None:
    try:
        answer_callback_query(callback_query_id)
    except (RuntimeError, requests.exceptions.RequestException):
        return



def handle_callback_query(callback_query: dict[str, Any]) -> None:
    callback_id = callback_query.get("id")
    data = callback_query.get("data", "")
    message = callback_query.get("message", {})
    chat = message.get("chat", {})
    chat_id = chat.get("id")
    message_id = message.get("message_id")

    if callback_id:
        safe_answer_callback_query(callback_id)

    if chat_id is None or message_id is None:
        return

    chat_id_str = str(chat_id)

    if data == "public:socials":
        send_socials_message(chat_id_str)
        return

    if data == "client:list":
        safe_edit_or_send(
            chat_id_str,
            message_id,
            build_customer_orders_text(chat_id_str),
            build_customer_orders_keyboard(chat_id_str),
        )
        return

    if data.startswith("client:view:"):
        token = data.split(":", maxsplit=2)[2]
        order = find_order_by_token(token)
        if not order or order.get("customer_chat_id") != chat_id_str:
            safe_edit_or_send(
                chat_id_str,
                message_id,
                "Не удалось открыть заказ. Если нужна помощь — напишите нам.",
                build_public_keyboard(chat_id_str),
            )
            return
        safe_edit_or_send(
            chat_id_str,
            message_id,
            render_order_text(order, for_admin=False),
            build_public_keyboard(chat_id_str, order["token"]),
        )
        return

    if data.startswith("client:refresh:"):
        token = data.split(":", maxsplit=2)[2]
        order = find_order_by_token(token)
        if not order or order.get("customer_chat_id") != chat_id_str:
            safe_edit_or_send(
                chat_id_str,
                message_id,
                "Заказ больше недоступен. Напишите нам, и мы поможем уточнить информацию.",
                build_public_keyboard(chat_id_str),
            )
            return
        safe_edit_or_send(
            chat_id_str,
            message_id,
            render_order_text(order, for_admin=False),
            build_public_keyboard(chat_id_str, order["token"]),
        )
        return

    if not is_admin(chat_id):
        send_public_welcome(chat_id_str)
        return

    if data == "admin:list":
        safe_edit_or_send(
            chat_id_str,
            message_id,
            build_orders_list_text(),
            build_orders_list_keyboard(),
        )
        return

    if data.startswith("admin:view:"):
        order_id = int(data.split(":", maxsplit=2)[2])
        order = find_order_by_id(order_id)
        if not order:
            safe_edit_or_send(chat_id_str, message_id, "Заказ не найден или уже удалён.")
            return
        safe_edit_or_send(
            chat_id_str,
            message_id,
            render_order_text(order, for_admin=True),
            build_admin_order_keyboard(order),
        )
        return

    if data.startswith("admin:status:"):
        _, _, order_id_str, status_key = data.split(":", maxsplit=3)
        order = find_order_by_id(int(order_id_str))
        if not order:
            safe_edit_or_send(chat_id_str, message_id, "Заказ не найден или уже удалён.")
            return
        allowed_statuses = get_status_keys(order["has_delivery"])
        if status_key not in allowed_statuses:
            safe_edit_or_send(chat_id_str, message_id, "Этот статус недоступен для выбранного заказа.")
            return
        if status_key == "awaiting_delivery":
            set_conversation(chat_id_str, "awaiting_delivery_schedule", order_id=order["id"])
            send_message(chat_id_str, "Укажи дату и время доставки, например: 20 января, 20:00")
            return
        update_order_status(order, status_key)
        notify_customer_order_update(
            order,
            f"По заказу #{order['id']} обновлён статус: {get_status_label(status_key)}.",
        )
        safe_edit_or_send(
            chat_id_str,
            message_id,
            render_order_text(order, for_admin=True),
            build_admin_order_keyboard(order),
        )
        return

    if data.startswith("admin:delivery_toggle:"):
        order_id = int(data.split(":", maxsplit=2)[2])
        order = find_order_by_id(order_id)
        if not order:
            safe_edit_or_send(chat_id_str, message_id, "Заказ не найден или уже удалён.")
            return
        update_delivery_flag(order, not order["has_delivery"])
        notify_customer_order_update(
            order,
            f"По заказу #{order['id']} изменён способ получения: {'доставка' if order['has_delivery'] else 'самовывоз'}.",
        )
        safe_edit_or_send(
            chat_id_str,
            message_id,
            render_order_text(order, for_admin=True),
            build_admin_order_keyboard(order),
        )
        return

    if data.startswith("admin:payment_full:"):
        order_id = int(data.split(":", maxsplit=2)[2])
        order = find_order_by_id(order_id)
        if not order:
            safe_edit_or_send(chat_id_str, message_id, "Заказ не найден или уже удалён.")
            return
        mark_fully_paid(order)
        notify_customer_order_update(
            order,
            f"По заказу #{order['id']} отмечена полная оплата.",
        )
        safe_edit_or_send(
            chat_id_str,
            message_id,
            render_order_text(order, for_admin=True),
            build_admin_order_keyboard(order),
        )
        return

    if data.startswith("admin:payment_add:"):
        order_id = int(data.split(":", maxsplit=2)[2])
        order = find_order_by_id(order_id)
        if not order:
            safe_edit_or_send(chat_id_str, message_id, "Заказ не найден или уже удалён.")
            return
        set_conversation(chat_id_str, "awaiting_payment_add", order_id=order_id)
        send_message(chat_id_str, "Введи сумму доплаты в рублях, например: 5000")
        return

    if data.startswith("admin:finish:"):
        order_id = int(data.split(":", maxsplit=2)[2])
        order = find_order_by_id(order_id)
        if not order:
            safe_edit_or_send(chat_id_str, message_id, "Заказ не найден или уже удалён.")
            return
        safe_edit_or_send(
            chat_id_str,
            message_id,
            (
                f"Завершить заказ #{order['id']}?\n"
                "После подтверждения клиент получит сообщение с благодарностью."
            ),
            build_finish_confirmation_keyboard(order_id),
        )
        return

    if data.startswith("admin:finish_yes:"):
        order_id = int(data.split(":", maxsplit=2)[2])
        order = find_order_by_id(order_id)
        if not order:
            safe_edit_or_send(chat_id_str, message_id, "Заказ не найден или уже удалён.")
            return
        complete_order(order)
        notify_customer_order_completed(order)
        safe_edit_or_send(
            chat_id_str,
            message_id,
            f"✅ Заказ #{order['id']} завершён.",
            {"inline_keyboard": [[{"text": "К списку заказов", "callback_data": "admin:list"}]]},
        )
        return

    if data.startswith("admin:finish_no:"):
        order_id = int(data.split(":", maxsplit=2)[2])
        order = find_order_by_id(order_id)
        if not order:
            safe_edit_or_send(chat_id_str, message_id, "Заказ не найден или уже удалён.")
            return
        safe_edit_or_send(
            chat_id_str,
            message_id,
            render_order_text(order, for_admin=True),
            build_admin_order_keyboard(order),
        )
        return

    if data.startswith("admin:delete:"):
        order_id = int(data.split(":", maxsplit=2)[2])
        order = find_order_by_id(order_id)
        if not order:
            safe_edit_or_send(chat_id_str, message_id, "Заказ не найден или уже удалён.")
            return
        safe_edit_or_send(
            chat_id_str,
            message_id,
            f"Удалить заказ #{order['id']} без возможности восстановления?",
            build_delete_confirmation_keyboard(order_id),
        )
        return

    if data.startswith("admin:delete_yes:"):
        order_id = int(data.split(":", maxsplit=2)[2])
        order = find_order_by_id(order_id)
        if order:
            customer_chat_id = order.get("customer_chat_id")
            if customer_chat_id:
                send_message(
                    str(customer_chat_id),
                    (
                        f"Заказ #{order['id']} удалён из системы отслеживания.\n"
                        "Если вы считаете, что это произошло без вашего уведомления, напишите нам по кнопке ниже."
                    ),
                    reply_markup=build_public_keyboard(str(customer_chat_id)),
                )
        deleted = delete_order(order_id)
        if not deleted:
            safe_edit_or_send(chat_id_str, message_id, "Заказ не найден или уже удалён.")
            return
        safe_edit_or_send(
            chat_id_str,
            message_id,
            f"🗑 Заказ #{order_id} удалён.",
            {"inline_keyboard": [[{"text": "К списку заказов", "callback_data": "admin:list"}]]},
        )
        return

    if data.startswith("admin:delete_no:"):
        order_id = int(data.split(":", maxsplit=2)[2])
        order = find_order_by_id(order_id)
        if not order:
            safe_edit_or_send(chat_id_str, message_id, "Заказ не найден или уже удалён.")
            return
        safe_edit_or_send(
            chat_id_str,
            message_id,
            render_order_text(order, for_admin=True),
            build_admin_order_keyboard(order),
        )
        return



def handle_update(update: dict[str, Any]) -> None:
    callback_query = update.get("callback_query")
    if callback_query:
        handle_callback_query(callback_query)
        return

    message = update.get("message")
    if not message:
        return

    chat = message.get("chat", {})
    chat_id = chat.get("id")
    if chat_id is None:
        return

    text = message.get("text")
    if text:
        handle_text_message(chat_id, text)
        return

    if is_admin(chat_id):
        send_message(str(chat_id), "Поддерживаются текстовые команды и сообщения.")
    else:
        send_public_welcome(str(chat_id))



def fetch_updates() -> list[dict[str, Any]]:
    params: dict[str, Any] = {"timeout": POLL_TIMEOUT_SECONDS}
    last_update_id = state.get("last_update_id")
    if last_update_id is not None:
        params["offset"] = last_update_id + 1

    payload = api_request("getUpdates", data=params)
    return payload.get("result", [])



def initialize_bot_profile() -> None:
    payload = api_request("getMe")
    result = payload.get("result", {})
    bot_profile["username"] = result.get("username")
    bot_profile["name"] = result.get("first_name")
    if not bot_profile["username"]:
        raise RuntimeError("У бота не найден username. Укажи username через @BotFather.")



def main() -> None:
    initialize_bot_profile()
    sync_archives()
    print("🤖 Telegram order tracker bot запущен")
    print(f"👤 Управление из chat_id={ADMIN_CHAT_ID}")
    print(f"🕒 Часовой пояс: {TIMEZONE_NAME}")
    print(f"🔗 Deep-link username: @{bot_profile['username']}")
    print(f"🗃 Архив заказов: {ARCHIVE_DIR}")

    while True:
        try:
            updates = fetch_updates()
            for update in updates:
                try:
                    handle_update(update)
                except requests.exceptions.RequestException as exc:
                    print(f"❌ Ошибка requests при обработке update {update['update_id']}: {exc}")
                except RuntimeError as exc:
                    print(f"⚠️ Ошибка Telegram API при обработке update {update['update_id']}: {exc}")
                finally:
                    state["last_update_id"] = update["update_id"]
                    save_state()

            time.sleep(LOOP_INTERVAL_SECONDS)
        except KeyboardInterrupt:
            print("\n👋 Выход...")
            break
        except requests.exceptions.Timeout:
            print("⏳ Таймаут long polling, продолжаю работу...")
        except requests.exceptions.ConnectionError:
            print("🌐 Ошибка соединения, повтор через несколько секунд...")
            time.sleep(5)
        except requests.exceptions.RequestException as exc:
            print(f"❌ Ошибка requests: {exc}")
            time.sleep(5)
        except RuntimeError as exc:
            print(f"⚠️ Ошибка Telegram API: {exc}")
            time.sleep(5)


if __name__ == "__main__":
    main()
