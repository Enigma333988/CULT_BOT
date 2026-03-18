import requests
import os
from dotenv import load_dotenv

# загрузка .env
load_dotenv()

TOKEN = os.getenv("TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
PROXY = os.getenv("PROXY")

session = requests.Session()
session.trust_env = False

proxies = {
    "http": PROXY,
    "https": PROXY,
}

url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

while True:
    text = input("Введите сообщение: ").strip()
    
    if not text:
        continue
    if text.lower() in ["exit", "q"]:
        break

    try:
        response = session.post(
            url,
            data={
                "chat_id": CHAT_ID,
                "text": text
            },
            proxies=proxies,
            timeout=20,
        )

        print(response.status_code)
        print(response.text)

    except Exception as e:
        print("Ошибка:", e)
