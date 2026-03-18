import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import requests
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID", CHAT_ID or "")
PROXY = os.getenv("PROXY")
TIMEZONE_NAME = os.getenv("TIMEZONE", "UTC")
QUEUE_FILE = Path(os.getenv("QUEUE_FILE", "queue.json"))
STATE_FILE = Path(os.getenv("STATE_FILE", "bot_state.json"))
ALLOWED_PROXY_SCHEMES = {"http", "https", "socks5", "socks5h"}
POLL_TIMEOUT_SECONDS = 10
REQUEST_TIMEOUT_SECONDS = 20
SCHEDULER_INTERVAL_SECONDS = 2
MAX_CAPTION_LENGTH = 1024

if not TOKEN:
    raise ValueError("❌ Не найден TOKEN в .env")

if not CHAT_ID:
    raise ValueError("❌ Не найден CHAT_ID в .env")

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
queue: list[dict[str, Any]] = load_json(QUEUE_FILE, [])


def save_state() -> None:
    STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )



def save_queue() -> None:
    QUEUE_FILE.write_text(
        json.dumps(queue, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )



def send_message(chat_id: str, text: str) -> None:
    api_request("sendMessage", data={"chat_id": chat_id, "text": text})



def send_photo(chat_id: str, photo_file_id: str, caption: str) -> None:
    api_request(
        "sendPhoto",
        data={
            "chat_id": chat_id,
            "photo": photo_file_id,
            "caption": caption,
        },
    )



def format_local_time(iso_timestamp: str) -> str:
    dt_utc = datetime.fromisoformat(iso_timestamp)
    dt_local = dt_utc.astimezone(LOCAL_TZ)
    return dt_local.strftime("%Y-%m-%d %H:%M %Z")



def parse_schedule(raw_value: str) -> datetime:
    cleaned = raw_value.strip()
    try:
        dt_local = datetime.strptime(cleaned, "%Y-%m-%d %H:%M")
    except ValueError as exc:
        raise ValueError("Используй формат даты и времени: YYYY-MM-DD HH:MM") from exc

    dt_local = dt_local.replace(tzinfo=LOCAL_TZ)
    dt_utc = dt_local.astimezone(timezone.utc)
    if dt_utc <= datetime.now(timezone.utc):
        raise ValueError("Дата и время должны быть в будущем")
    return dt_utc



def build_queue_text() -> str:
    pending_items = [item for item in queue if item["status"] == "pending"]
    if not pending_items:
        return "📭 Очередь пуста. Используй /newpost, чтобы добавить пост."

    pending_items.sort(key=lambda item: item["scheduled_at"])
    lines = ["🗂 Очередь постов:"]
    for item in pending_items:
        caption_preview = item["caption"].replace("\n", " ").strip()
        if len(caption_preview) > 40:
            caption_preview = f"{caption_preview[:37]}..."
        lines.append(
            f"#{item['id']} — {format_local_time(item['scheduled_at'])} — {caption_preview or '(без текста)'}"
        )
    return "\n".join(lines)



def next_post_id() -> int:
    return max((item["id"] for item in queue), default=0) + 1



def create_post(admin_chat_id: str, photo_file_id: str, caption: str, scheduled_at: datetime) -> dict[str, Any]:
    post = {
        "id": next_post_id(),
        "created_by": admin_chat_id,
        "photo_file_id": photo_file_id,
        "caption": caption,
        "scheduled_at": scheduled_at.astimezone(timezone.utc).isoformat(),
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "posted_at": None,
        "error": None,
    }
    queue.append(post)
    save_queue()
    return post



def set_conversation(chat_id: str, step: str, **extra: Any) -> None:
    conversation_state[chat_id] = {"step": step, **extra}



def clear_conversation(chat_id: str) -> None:
    conversation_state.pop(chat_id, None)



def is_admin(chat_id: int) -> bool:
    return str(chat_id) == str(ADMIN_CHAT_ID)



def handle_command(chat_id: int, text: str) -> None:
    text = text.strip()

    if text == "/start":
        clear_conversation(str(chat_id))
        send_message(
            str(chat_id),
            (
                "Привет! Я бот для отложенных постов.\n\n"
                "Команды:\n"
                "/newpost — создать новый пост\n"
                "/queue — показать очередь\n"
                "/cancel — отменить текущее создание поста"
            ),
        )
        return

    if text == "/newpost":
        set_conversation(str(chat_id), "awaiting_photo")
        send_message(str(chat_id), "📷 Отправь фото, которое нужно опубликовать.")
        return

    if text == "/queue":
        send_message(str(chat_id), build_queue_text())
        return

    if text == "/cancel":
        clear_conversation(str(chat_id))
        send_message(str(chat_id), "🛑 Создание поста отменено.")
        return

    send_message(
        str(chat_id),
        "Неизвестная команда. Используй /newpost, /queue или /cancel.",
    )



def handle_photo_message(chat_id: int, photos: list[dict[str, Any]]) -> None:
    state_for_chat = conversation_state.get(str(chat_id))
    if not state_for_chat or state_for_chat.get("step") != "awaiting_photo":
        send_message(str(chat_id), "Сначала используй /newpost, потом отправь фото.")
        return

    largest_photo = photos[-1]
    file_id = largest_photo.get("file_id")
    if not file_id:
        send_message(str(chat_id), "Не удалось получить file_id фото. Попробуй ещё раз.")
        return

    set_conversation(str(chat_id), "awaiting_caption", photo_file_id=file_id)
    send_message(
        str(chat_id),
        (
            "📝 Теперь отправь текст поста.\n"
            "Если текст не нужен, отправь одиночный символ -"
        ),
    )



def handle_text_message(chat_id: int, text: str) -> None:
    if text.startswith("/"):
        handle_command(chat_id, text)
        return

    state_for_chat = conversation_state.get(str(chat_id))
    if not state_for_chat:
        send_message(
            str(chat_id),
            "Используй /newpost, чтобы создать отложенный пост, или /queue, чтобы посмотреть очередь.",
        )
        return

    step = state_for_chat.get("step")
    if step == "awaiting_caption":
        caption = "" if text.strip() == "-" else text.strip()
        if len(caption) > MAX_CAPTION_LENGTH:
            send_message(
                str(chat_id),
                f"Текст слишком длинный. У Telegram лимит подписи к фото — {MAX_CAPTION_LENGTH} символа.",
            )
            return
        set_conversation(
            str(chat_id),
            "awaiting_schedule",
            photo_file_id=state_for_chat["photo_file_id"],
            caption=caption,
        )
        send_message(
            str(chat_id),
            (
                "📅 Отправь дату и время публикации в формате YYYY-MM-DD HH:MM\n"
                f"Часовой пояс бота: {TIMEZONE_NAME}"
            ),
        )
        return

    if step == "awaiting_schedule":
        try:
            scheduled_at = parse_schedule(text)
        except ValueError as exc:
            send_message(str(chat_id), f"⚠️ {exc}")
            return

        post = create_post(
            admin_chat_id=str(chat_id),
            photo_file_id=state_for_chat["photo_file_id"],
            caption=state_for_chat["caption"],
            scheduled_at=scheduled_at,
        )
        clear_conversation(str(chat_id))
        send_message(
            str(chat_id),
            (
                f"✅ Пост #{post['id']} добавлен в очередь.\n"
                f"Дата публикации: {format_local_time(post['scheduled_at'])}\n\n"
                f"Текущая очередь:\n{build_queue_text()}"
            ),
        )
        return

    send_message(str(chat_id), "Используй /cancel и начни заново через /newpost.")



def handle_update(update: dict[str, Any]) -> None:
    message = update.get("message")
    if not message:
        return

    chat = message.get("chat", {})
    chat_id = chat.get("id")
    if chat_id is None or not is_admin(chat_id):
        return

    if "photo" in message:
        handle_photo_message(chat_id, message["photo"])
        return

    text = message.get("text")
    if text:
        handle_text_message(chat_id, text)
        return

    send_message(str(chat_id), "Поддерживаются текстовые сообщения, команды и фото.")



def publish_due_posts() -> None:
    now_utc = datetime.now(timezone.utc)
    changed = False

    for item in sorted(queue, key=lambda row: row["scheduled_at"]):
        if item["status"] != "pending":
            continue

        scheduled_at = datetime.fromisoformat(item["scheduled_at"])
        if scheduled_at > now_utc:
            continue

        try:
            send_photo(CHAT_ID, item["photo_file_id"], item["caption"])
            item["status"] = "posted"
            item["posted_at"] = datetime.now(timezone.utc).isoformat()
            item["error"] = None
            send_message(
                str(ADMIN_CHAT_ID),
                f"🚀 Пост #{item['id']} опубликован ({format_local_time(item['scheduled_at'])}).",
            )
        except Exception as exc:
            item["status"] = "failed"
            item["error"] = str(exc)
            send_message(
                str(ADMIN_CHAT_ID),
                f"❌ Не удалось опубликовать пост #{item['id']}: {exc}",
            )
        changed = True

    if changed:
        save_queue()



def fetch_updates() -> list[dict[str, Any]]:
    params: dict[str, Any] = {"timeout": POLL_TIMEOUT_SECONDS}
    last_update_id = state.get("last_update_id")
    if last_update_id is not None:
        params["offset"] = last_update_id + 1

    payload = api_request("getUpdates", data=params)
    return payload.get("result", [])



def main() -> None:
    print("🤖 Telegram scheduler bot запущен")
    print(f"📨 Публикация в chat_id={CHAT_ID}")
    print(f"👤 Управление из chat_id={ADMIN_CHAT_ID}")
    print(f"🕒 Часовой пояс: {TIMEZONE_NAME}")

    while True:
        try:
            updates = fetch_updates()
            for update in updates:
                handle_update(update)
                state["last_update_id"] = update["update_id"]
                save_state()

            publish_due_posts()
            time.sleep(SCHEDULER_INTERVAL_SECONDS)
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
