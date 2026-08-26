import logging
import os
import re
from datetime import datetime, timedelta, timezone

from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InputMediaVideo
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

# Твой токен от BotFather
TOKEN = "7722427747:AAFS11MutsqtvjVf8XiSy8GDBfnQjhY94Es"

VIDEO_URL = "http://195.133.60.26:8080/vecherniy.mp4"
CHANNEL_LINK = "https://t.me/гибкое_тело"
PHONE_RE = re.compile(r"^[78]\d{10}$")

BTN_PLASTIC = "🌿 Хочу пластичное и гибкое тело"
BTN_BACK = "🔥 Устала спина от сидячего дня"
BTN_MORNING = "☀️ Хочу разбудить тело утром"
BTN_EVENING = "🌙 Хочу расслабить тело перед сном"
BTN_CLUB = "Хочу в клуб"

START_TEXT = (
    "Привет\n\n"
    "Я бот Леры Ливи. Здесь ты можешь забрать один из моих коротких комплексов — "
    "под конкретный запрос твоего тела.\n\n"
    "Что тебе сейчас нужнее всего?"
)

COMPLEX_TEXTS = {
    BTN_BACK: (
        "Комплекс от зажимов в спине после сидячего дня — 15 минут. "
        "Тебе нужен только коврик.\n\n"
        "Сделаешь — напиши мне, что изменилось. Мне важно знать 💛\n\n"
        "Если хочешь задать вопрос лично — просто напиши мне в этот чат."
    ),
    BTN_MORNING: (
        "Утренний комплекс — 10 минут. Идеально делать сразу после пробуждения, "
        "но подойдёт в любое время до 12:00.\n\n"
        "Сделаешь — напиши, как ощущения. Мне важно знать 💛\n\n"
        "Если хочешь задать вопрос лично — просто напиши мне в этот чат."
    ),
    BTN_PLASTIC: (
        "Комплекс на пластику для сильного и гибкого тела — 20 минут. "
        "Тебе нужен только коврик.\n\n"
        "Сделаешь — напиши мне, что почувствовала. Мне важно знать 💛\n\n"
        "Если хочешь задать вопрос лично — просто напиши мне в этот чат."
    ),
    BTN_EVENING: (
        "Вечерний комплекс — 15 минут. Делай перед сном, в удобной одежде, "
        "на коврике или прямо в кровати.\n\n"
        "Сделаешь — напиши, что почувствовала. Мне важно знать 💛\n\n"
        "Если хочешь задать вопрос лично — просто напиши мне в этот чат."
    ),
}

CLUB_SUCCESS_TEXT = (
    "Супер! Твой номер телефона получен 📱\n\n"
    "Добавляю тебя в список участников клуба. Я свяжусь с тобой в ближайшее время "
    "(в течение часа), чтобы подтвердить доступ и отправить все материалы.\n\n"
    "Добро пожаловать в «Гибкое тело»! 🔥"
)

WARMUP_MESSAGES = [
    "Привет! Не забывай про своё тело. Как прошла тренировка? Поделись ощущениями 💛",
    "Ты в порядке? Если хочешь, я могу прислать тебе ещё один комплекс или ответить на вопросы.",
    "Знаешь, многие говорят, что после 3 дней занятий тело начинает просить движения. Как ты?",
    "Я здесь, чтобы помочь тебе чувствовать себя лучше. Напиши, если захочешь поговорить.",
    "Ты важна. Твоё тело — твой дом. Если хочешь присоединиться к клубу — просто напиши «Хочу в клуб».",
]

WARMUP_DELAYS = [
    60 * 60,        # 1 час
    12 * 60 * 60,   # 12 часов
    24 * 60 * 60,   # 24 часа
    48 * 60 * 60,   # 48 часов
    72 * 60 * 60,   # 72 часа
]

# Состояние пользователей: chat_id -> dict
user_data = {}

# Все входящие личные сообщения (для админа)
incoming_messages = []

START_KEYBOARD = ReplyKeyboardMarkup(
    [[BTN_PLASTIC], [BTN_BACK], [BTN_MORNING], [BTN_EVENING]],
    resize_keyboard=True,
)

CLUB_KEYBOARD = ReplyKeyboardMarkup([[BTN_CLUB]], resize_keyboard=True)


def get_state(chat_id: int) -> dict:
    if chat_id not in user_data:
        user_data[chat_id] = {
            "complex": None,
            "awaiting_phone": False,
            "phone": None,
            "last_activity": datetime.now(timezone.utc),
        }
    return user_data[chat_id]


async def warmup_job(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.chat_id
    index = context.job.data["index"]
    await context.bot.send_message(chat_id=chat_id, text=WARMUP_MESSAGES[index])


def schedule_warmup(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    job_queue = context.job_queue
    if job_queue is None:
        return
    for job in job_queue.get_jobs_by_name(f"warmup_{chat_id}"):
        job.schedule_removal()
    for index, delay in enumerate(WARMUP_DELAYS):
        job_queue.run_once(
            warmup_job,
            when=timedelta(seconds=delay),
            chat_id=chat_id,
            name=f"warmup_{chat_id}",
            data={"index": index},
        )


def touch(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    state = get_state(chat_id)
    state["last_activity"] = datetime.now(timezone.utc)
    schedule_warmup(chat_id, context)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    state = get_state(chat_id)
    touch(chat_id, context)

    # Полная очистка старой клавиатуры
    await update.message.reply_text(
        "Начинаем заново!",
        reply_markup=ReplyKeyboardRemove()
    )

    if state["complex"] is not None:
        if state["complex"] in COMPLEX_TEXTS:
            await update.message.reply_text(
                COMPLEX_TEXTS[state["complex"]],
                reply_markup=CLUB_KEYBOARD,
            )
        else:
            state["complex"] = None
            await update.message.reply_text(START_TEXT, reply_markup=START_KEYBOARD)
        return

    await update.message.reply_text(START_TEXT, reply_markup=START_KEYBOARD)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    text = (update.message.text or "").strip()
    state = get_state(chat_id)
    touch(chat_id, context)

    # Ожидание номера телефона
    if state["awaiting_phone"]:
        phone = re.sub(r"[^\d]", "", text)
        if PHONE_RE.match(phone):
            state["phone"] = phone
            state["awaiting_phone"] = False
            logger.info("Новый участник клуба: chat_id=%s, телефон=%s", chat_id, phone)
            await update.message.reply_text(
                CLUB_SUCCESS_TEXT, reply_markup=ReplyKeyboardRemove()
            )
            await update.message.reply_text(
                f"Ссылка на канал: {CHANNEL_LINK}"
            )
        else:
            await update.message.reply_text(
                "Кажется, номер введён неверно. Напиши номер из 11 цифр, "
                "начиная с 7 или 8. Например: 79991234567"
            )
        return

    # Выбор комплекса — только если ещё не выбран
   if state["complex"] is None:
    if text in COMPLEX_TEXTS:
        state["complex"] = text
        
        # Отправляем видео как файл
        await update.message.reply_video(
            video=open("/app/vecherniy.mp4", "rb"),
            caption=COMPLEX_TEXTS[text],
            reply_markup=CLUB_KEYBOARD  # Кнопка "Хочу в клуб" прямо под видео
        )
        return
    else:
        # Комплекс уже выбран — кнопки выбора больше не работают
        if text in COMPLEX_TEXTS:
            return

    # Кнопка "Хочу в клуб"
    if text == BTN_CLUB or text.lower() == BTN_CLUB.lower():
        if state["phone"]:
            await update.message.reply_text(
                "Твой номер уже у меня 💛 Я свяжусь с тобой в ближайшее время."
            )
            return
        state["awaiting_phone"] = True
        await update.message.reply_text(
            "Отлично! Напиши, пожалуйста, свой номер телефона — "
            "11 цифр, начиная с 7 или 8. Например: 79991234567",
            reply_markup=ReplyKeyboardRemove(),
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

    print("Бот запущен...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
