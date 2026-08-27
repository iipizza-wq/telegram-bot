import logging
import re
import os
from datetime import datetime, timedelta, timezone

from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, KeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TOKEN")

VIDEO_URL = "http://195.133.60.26:8080/vecherniy.mp4"
CHANNEL_LINK = "https://t.me/leralivingston"
BTN_GET_COMPLEX = "🎥 Хочу получить комплекс"
BTN_CLUB = "Хочу в клуб"
BTN_SHARE_PHONE = "📱 Поделиться номером"

START_TEXT = (
    "Привет!\n\n"
    "Я бот Леры Ливи. Здесь ты можешь получить короткий комплекс — "
    "под конкретный запрос твоего тела.\n\n"
    "Нажми на кнопку ниже, чтобы получить комплекс."
)

COMPLEX_TEXT = (
    "Вечерний комплекс — 15 минут. Делай перед сном, в удобной одежде, "
    "на коврике или прямо в кровати.\n\n"
    "[🎥 Смотреть видео «Лера Ливи»](http://195.133.60.26:8080/vecherniy.mp4)\n\n"
    "Сделаешь — напиши мне, что почувствовала. Мне важно знать 💛\n\n"
    "Если хочешь задать вопрос лично — просто напиши мне в этот чат."
)

CLUB_SUCCESS_TEXT = (
    "Супер! Твой номер телефона получен 📱\n\n"
    "Добавляю тебя в список участников клуба. Я свяжусь с тобой в ближайшее время "
    "(в течение часа), чтобы подтвердить доступ и отправить все материалы.\n\n"
    "Добро пожаловать в LIVICLUB! 🕊✨"
)

# Сообщения для прогрева (каждый час — 3 сообщения, каждый день — 1 сообщение)
WARMUP_HOURLY = [
    "Привет! Как настроение? Надеюсь, тебе понравился комплекс 💛",
    "Если хочешь, я могу прислать тебе ещё один комплекс или ответить на вопросы.",
    "Знаешь, многие говорят, что после 3 дней занятий тело начинает просить движения. Как ты?",
]

WARMUP_DAILY = [
    "Доброе утро! Как спалось? Не забывай про свои ощущения после комплекса 💛",
    "Привет! Как дела? Если хочешь, можем обсудить твой прогресс.",
    "Ты уже сделала несколько шагов к здоровому телу. Горжусь тобой! Продолжай в том же духе.",
]

user_data = {}
incoming_messages = []

START_KEYBOARD = ReplyKeyboardMarkup(
    [[BTN_GET_COMPLEX]],
    resize_keyboard=True,
)

CLUB_KEYBOARD = ReplyKeyboardMarkup(
    [[BTN_CLUB]],
    resize_keyboard=True,
)

PHONE_KEYBOARD = ReplyKeyboardMarkup(
    [[KeyboardButton(BTN_SHARE_PHONE, request_contact=True)]],
    resize_keyboard=True,
)


def get_state(chat_id: int) -> dict:
    if chat_id not in user_data:
        user_data[chat_id] = {
            "complex_given": False,
            "phone": None,
            "last_activity": datetime.now(timezone.utc),
            "hourly_index": 0,
            "daily_index": 0,
        }
    return user_data[chat_id]


async def warmup_job(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.chat_id
    job_type = context.job.data["type"]
    state = get_state(chat_id)

    if job_type == "hourly":
        if state["hourly_index"] < len(WARMUP_HOURLY):
            await context.bot.send_message(
                chat_id=chat_id,
                text=WARMUP_HOURLY[state["hourly_index"]]
            )
            state["hourly_index"] += 1
    elif job_type == "daily":
        if state["daily_index"] < len(WARMUP_DAILY):
            await context.bot.send_message(
                chat_id=chat_id,
                text=WARMUP_DAILY[state["daily_index"]]
            )
            state["daily_index"] += 1


def schedule_warmup(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    job_queue = context.job_queue
    if job_queue is None:
        return

    # Удаляем старые задачи
    for job in job_queue.get_jobs_by_name(f"warmup_{chat_id}"):
        job.schedule_removal()

    # Каждый час — 3 сообщения
    for i in range(3):
        job_queue.run_once(
            warmup_job,
            when=timedelta(hours=i + 1),
            chat_id=chat_id,
            name=f"warmup_{chat_id}",
            data={"type": "hourly"},
        )

    # Раз в день — 3 сообщения
    for i in range(3):
        job_queue.run_once(
            warmup_job,
            when=timedelta(days=i + 1),
            chat_id=chat_id,
            name=f"warmup_{chat_id}",
            data={"type": "daily"},
        )


def touch(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    state = get_state(chat_id)
    state["last_activity"] = datetime.now(timezone.utc)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    state = get_state(chat_id)
    touch(chat_id, context)

    await update.message.reply_text(
        "Начинаем заново!",
        reply_markup=ReplyKeyboardRemove()
    )

    if state["complex_given"]:
        await update.message.reply_text(
            COMPLEX_TEXT,
            reply_markup=CLUB_KEYBOARD,
            parse_mode='Markdown'
        )
        return

    await update.message.reply_text(START_TEXT, reply_markup=START_KEYBOARD)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    text = (update.message.text or "").strip()
    state = get_state(chat_id)
    touch(chat_id, context)

    # Обработка номера телефона через кнопку
    if update.message.contact:
        phone = update.message.contact.phone_number
        state["phone"] = phone
        logger.info("Новый участник клуба: chat_id=%s, телефон=%s", chat_id, phone)
        await update.message.reply_text(
            CLUB_SUCCESS_TEXT, reply_markup=ReplyKeyboardRemove()
        )
        await update.message.reply_text(
            f"Ссылка на канал: {CHANNEL_LINK}"
        )
        return

    # Кнопка "Хочу получить комплекс"
    if text == BTN_GET_COMPLEX:
        state["complex_given"] = True
        await update.message.reply_text(
            COMPLEX_TEXT,
            reply_markup=CLUB_KEYBOARD,
        )
        schedule_warmup(chat_id, context)
        return

    # Кнопка "Хочу в клуб"
    if text == BTN_CLUB or text.lower() == BTN_CLUB.lower():
        if state["phone"]:
            await update.message.reply_text(
                "Твой номер уже у меня 💛 Я свяжусь с тобой в ближайшее время."
            )
            return
        await update.message.reply_text(
            "Нажми на кнопку ниже, чтобы поделиться номером:",
            reply_markup=PHONE_KEYBOARD,
        )
        return

    # Любое другое сообщение — сохраняем для админа
    record = {
        "chat_id": chat_id,
        "username": update.effective_user.username,
        "name": update.effective_user.full_name,
        "text": text,
        "date": datetime.now(timezone.utc).isoformat(),
    }
    incoming_messages.append(record)
    logger.info("СООБЩЕНИЕ ОТ ПОЛЬЗОВАТЕЛЯ: %s", record)
    print(f"[СООБЩЕНИЕ] {record}")

    await update.message.reply_text(
        "Твоё сообщение получено. Я отвечу тебе в ближайшее время 💛"
    )


def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.CONTACT, handle_message))

    print("Бот запущен...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
