# CULT_BOT 🤖

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)]()
[![License](https://img.shields.io/badge/license-MIT-green.svg)]()

Telegram-бот на Python с использованием переменных окружения.

---

## 📦 Возможности

* Работа с Telegram Bot API
* Использование `.env` для хранения секретов
* Готов к деплою (Render / Railway / VPS)

---

## 📁 Структура проекта

```
CULT_BOT/
├── bot.py
├── .env.example
├── .gitignore
└── README.md
```

---

## ⚙️ Настройка

### 1. Создай `.env`

```bash
cp .env.example .env
```

### 2. Заполни данные

```env
TOKEN=your_bot_token_here
CHAT_ID=your_chat_id_here
PROXY=
```

---

## 🚀 Запуск

```bash
python bot.py
```

---

## 📚 Зависимости

Установить все зависимости:

```bash
pip install -r requirements.txt
```

---

## 🔐 Безопасность

* `.env` не должен попадать в GitHub
* Никогда не публикуй `TOKEN`
* Используй `.env.example` как шаблон

---

## 🧠 Как это работает

Бот берёт данные из переменных окружения:

* `TOKEN` — токен бота
* `CHAT_ID` — ID чата
* `PROXY` — прокси (опционально)

---

## ☁️ Деплой

Можно запустить на:

* Railway
* Render
* VPS

Просто добавь переменные окружения в настройках сервиса.

---

## 📌 Примечание

Если бот не работает:

* проверь `.env`
* проверь токен
* проверь интернет / прокси
