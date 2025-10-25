"""
ai_content_bot_payments.py
AIContentPro — Telegram-бот для генерации идей + оплата через CryptoBot (TON/USDT/Stars).
ВАЖНО: НЕ вставляй реальные токены сюда. Укажи их как переменные окружения в Render.
"""

import os
import json
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types
from aiogram.types import LabeledPrice
from aiogram.utils import executor
import openai

# ------------------ НАСТРОЙКИ ------------------
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
PAYMENT_PROVIDER_TOKEN = os.getenv("PAYMENT_PROVIDER_TOKEN")

DATA_FILE = "users_data.json"
FREE_DAILY_QUOTA = 3

if not TELEGRAM_TOKEN or not OPENAI_API_KEY or not PAYMENT_PROVIDER_TOKEN:
    raise SystemExit("⚠️ Установи TELEGRAM_TOKEN, OPENAI_API_KEY и PAYMENT_PROVIDER_TOKEN в Environment Variables.")

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher(bot)
openai.api_key = OPENAI_API_KEY


# ------------------ ХРАНИЛИЩЕ ------------------
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"users": {}, "conversations": {}}


def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


data = load_data()


def get_user(uid):
    uid = str(uid)
    users = data.setdefault("users", {})
    if uid not in users:
        users[uid] = {
            "free_used_today": 0,
            "last_reset": datetime.utcnow().date().isoformat(),
            "is_paid": False,
            "paid_until": None,
        }
        save_data(data)
    return users[uid]


def reset_quota(user):
    last = datetime.fromisoformat(user["last_reset"])
    if datetime.utcnow().date() > last.date():
        user["free_used_today"] = 0
        user["last_reset"] = datetime.utcnow().date().isoformat()


# ------------------ OpenAI ------------------
def ask_openai(prompt, model="gpt-4", max_tokens=600, temperature=0.8):
    try:
        response = openai.ChatCompletion.create(
            model=model,
            messages=[
                {"role": "system", "content": "Ты — помощник по маркетингу и генерации контента для соцсетей."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return response["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return f"Ошибка OpenAI: {e}"


# ------------------ ОПЛАТЫ ------------------
@dp.message_handler(commands=["buy"])
async def cmd_buy(message: types.Message):
    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton("💎 Оплатить в TON", callback_data="buy_ton"),
        types.InlineKeyboardButton("💵 Оплатить в USDT", callback_data="buy_usdt"),
    )
    kb.add(types.InlineKeyboardButton("⭐ Telegram Stars", callback_data="buy_stars"))
    await message.answer("Выбери валюту для оплаты (подписка 1 месяц):", reply_markup=kb)


@dp.callback_query_handler(lambda c: c.data and c.data.startswith("buy_"))
async def process_buy(callback: types.CallbackQuery):
    currency = callback.data.split("_", 1)[1].upper()

    if currency == "USDT":
        prices = [LabeledPrice(label="AIContentPro — Подписка 1 месяц (USDT)", amount=10 * 100)]
        currency_code = "USD"
    elif currency == "TON":
        prices = [LabeledPrice(label="AIContentPro — Подписка 1 месяц (TON)", amount=15 * 100)]
        currency_code = "USD"
    else:
        prices = [LabeledPrice(label="AIContentPro — Подписка 1 месяц (Stars)", amount=100 * 100)]
        currency_code = "XTR"

    try:
        await bot.send_invoice(
            chat_id=callback.from_user.id,
            title="AIContentPro — Подписка (1 месяц)",
            description=f"Оплата в {currency}. Безлимит идей на 30 дней.",
            provider_token=PAYMENT_PROVIDER_TOKEN,
            currency=currency_code,
            prices=prices,
            start_parameter=f"sub_{currency.lower()}",
            payload=f"subscription_{currency.lower()}_{datetime.utcnow().isoformat()}",
        )
        await bot.answer_callback_query(callback.id)
    except Exception as e:
        await bot.answer_callback_query(callback.id, str(e))


@dp.pre_checkout_query_handler(lambda q: True)
async def pre_checkout(pre_q: types.PreCheckoutQuery):
    await bot.answer_pre_checkout_query(pre_q.id, ok=True)


@dp.message_handler(content_types=types.ContentType.SUCCESSFUL_PAYMENT)
async def successful_payment(message: types.Message):
    user = get_user(message.from_user.id)
    user["is_paid"] = True
    user["paid_until"] = (datetime.utcnow() + timedelta(days=30)).isoformat()
    save_data(data)
    await message.answer("✅ Оплата получена! Подписка активна до 30 дней.")


# ------------------ КОМАНДЫ ------------------
@dp.message_handler(commands=["start", "help"])
async def start_cmd(message: types.Message):
    user = get_user(message.from_user.id)
    reset_quota(user)
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("/ideas", "/buy", "/status")
    text = (
        "🤖 *AIContentPro* — твой бот для идей и коротких текстов.\n\n"
        "Команды:\n"
        "📌 /ideas <тема> — 5 идей + тексты\n"
        "💰 /buy — подписка\n"
        "📊 /status — статус подписки и квоты\n"
    )
    await message.answer(text, parse_mode="Markdown", reply_markup=kb)


@dp.message_handler(commands=["status"])
async def status_cmd(message: types.Message):
    user = get_user(message.from_user.id)
    reset_quota(user)
    remain = FREE_DAILY_QUOTA - user["free_used_today"]
    paid_until = user["paid_until"] or "—"
    await message.answer(
        f"📊 Подписка: {'✅ Активна' if user['is_paid'] else '❌ Нет'}\n"
        f"⏳ Действует до: {paid_until}\n"
        f"Бесплатных генераций осталось: {remain}"
    )


@dp.message_handler(commands=["ideas"])
async def ideas_cmd(message: types.Message):
    args = message.get_args().strip()
    if not args:
        await message.reply("Используй: /ideas тема — например `/ideas косметика`")
        return

    user = get_user(message.from_user.id)
    reset_quota(user)

    if not user["is_paid"]:
        if user["free_used_today"] >= FREE_DAILY_QUOTA:
            await message.reply("⚠️ Бесплатная квота исчерпана. Купи подписку через /buy")
            return
        user["free_used_today"] += 1
        save_data(data)

    await message.answer("✍️ Генерирую идеи... подожди немного ⏳")

    prompt = (
        f"Дай 5 идей для коротких постов на тему '{args}'. "
        "Для каждой идеи добавь пример короткого текста (до 3 предложений) и 2-3 хэштега."
    )
    result = ask_openai(prompt)

    convs = data.setdefault("conversations", {})
    convs.setdefault(str(message.from_user.id), []).append(
        {"ts": datetime.utcnow().isoformat(), "topic": args, "result": result}
    )
    save_data(data)

    await message.answer(result)


@dp.message_handler()
async def fallback(message: types.Message):
    await message.reply("Не понял 🤔. Используй /ideas <тема> или /buy.")


if __name__ == "__main__":
    print("🚀 AIContentPro запущен и ожидает сообщения...")
    executor.start_polling(dp, skip_updates=True)
