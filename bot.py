import os
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv

# Загружаем переменные из .env
load_dotenv()

TOKEN = os.getenv("TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
PROXY = os.getenv("PROXY")
ALLOWED_PROXY_SCHEMES = {"http", "https", "socks5", "socks5h"}


# Проверки
if not TOKEN:
    raise ValueError("❌ Не найден TOKEN в .env")

if not CHAT_ID:
    raise ValueError("❌ Не найден CHAT_ID в .env")

if PROXY:
    parsed_proxy = urlparse(PROXY)
    if parsed_proxy.scheme.lower() not in ALLOWED_PROXY_SCHEMES:
        raise ValueError(
            "❌ Некорректная схема PROXY. Используй http://, https://, socks5:// или socks5h://"
        )


# Создаём сессию
session = requests.Session()
session.trust_env = False

# URL Telegram API
url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

print("🤖 Бот запущен. Вводи сообщение:")
print("Для выхода: exit или q\n")

while True:
    try:
        text = input(">> ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\n👋 Выход...")
        break

    if not text:
        continue

    if text.lower() in ["exit", "q"]:
        print("👋 Выход...")
        break

    try:
        request_kwargs = {
            "data": {
                "chat_id": CHAT_ID,
                "text": text,
            },
            "timeout": 20,
            "allow_redirects": False,
        }

        # Добавляем прокси только если он есть
        if PROXY:
            request_kwargs["proxies"] = {
                "http": PROXY,
                "https": PROXY,
            }

        response = session.post(url, **request_kwargs)
        response.raise_for_status()

        try:
            payload = response.json()
        except ValueError:
            print(f"📡 Status: {response.status_code}")
            print("⚠️ Telegram вернул не-JSON ответ\n")
            continue

        if payload.get("ok"):
            print(f"✅ Сообщение отправлено. Status: {response.status_code}\n")
        else:
            description = payload.get("description", "Неизвестная ошибка Telegram API")
            print(f"⚠️ Telegram API вернул ошибку: {description}\n")

    except requests.exceptions.Timeout:
        print("⏳ Таймаут запроса\n")

    except requests.exceptions.TooManyRedirects:
        print("⚠️ Обнаружено слишком много редиректов, запрос отменён\n")

    except requests.exceptions.HTTPError as exc:
        print(f"⚠️ HTTP ошибка: {exc.response.status_code}\n")

    except requests.exceptions.ConnectionError:
        print("🌐 Ошибка соединения (проверь интернет или прокси)\n")

    except requests.exceptions.RequestException as exc:
        print(f"❌ Ошибка запроса: {exc}\n")
