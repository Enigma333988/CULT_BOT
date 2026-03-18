import requests
import os
from dotenv import load_dotenv

# Загружаем переменные из .env
load_dotenv()

TOKEN = os.getenv("TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
PROXY = os.getenv("PROXY")

# Проверки
if not TOKEN:
    raise ValueError("❌ Не найден TOKEN в .env")

if not CHAT_ID:
    raise ValueError("❌ Не найден CHAT_ID в .env")

# Создаём сессию
session = requests.Session()
session.trust_env = False

# URL Telegram API
url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

print("🤖 Бот запущен. Вводи сообщение:")
print("Для выхода: exit или q\n")

while True:
    text = input(">> ").strip()

    if not text:
        continue

    if text.lower() in ["exit", "q"]:
        print("👋 Выход...")
        break

    try:
        request_kwargs = {
            "data": {
                "chat_id": CHAT_ID,
                "text": text
            },
            "timeout": 20,
        }

        # Добавляем прокси только если он есть
        if PROXY:
            request_kwargs["proxies"] = {
                "http": PROXY,
                "https": PROXY,
            }

        response = session.post(url, **request_kwargs)

        print(f"📡 Status: {response.status_code}")
        print(f"📨 Response: {response.text}\n")

    except requests.exceptions.Timeout:
        print("⏳ Таймаут запроса\n")

    except requests.exceptions.ConnectionError:
        print("🌐 Ошибка соединения (проверь интернет или прокси)\n")

    except Exception as e:
        print(f"❌ Ошибка: {e}\n")
