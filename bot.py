"""
Telegram бот для отслеживания здоровья питомцев с системой супервизоров
"""

import os
import json
import logging
from datetime import datetime
from typing import Optional
from pathlib import Path

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

from database import Database
from pdf_export import generate_pdf_report

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Инициализация БД
db = Database("pet_health.db")

# Состояния пользователя
USER_STATES = {}

# Константы состояний
STATE_ONBOARDING_NAME = "onboarding_name"
STATE_ONBOARDING_TYPE = "onboarding_type"
STATE_REMINDER_TEXT = "reminder_text"
STATE_REMINDER_TIME = "reminder_time"
STATE_WAITING_FOR_PDF = "waiting_for_pdf"
STATE_SUPERVISOR_TRANSCRIPTION = "supervisor_transcription"
STATE_NORMAL = "normal"


def get_user_state(user_id: int) -> str:
    """Получить текущее состояние пользователя"""
    return USER_STATES.get(user_id, STATE_NORMAL)


def set_user_state(user_id: int, state: str, data: dict = None):
    """Установить состояние пользователя"""
    USER_STATES[user_id] = state
    if data:
        USER_STATES[f"{user_id}_data"] = data


def get_user_data(user_id: int) -> dict:
    """Получить временные данные пользователя"""
    return USER_STATES.get(f"{user_id}_data", {})


def clear_user_state(user_id: int):
    """Очистить состояние пользователя"""
    USER_STATES.pop(user_id, None)
    USER_STATES.pop(f"{user_id}_data", None)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start — онбординг"""
    user_id = update.effective_user.id
    
    # Проверяем, является ли пользователь супервизором
    if db.is_supervisor(user_id):
        pending = db.get_pending_transcription_requests()
        await update.message.reply_text(
            f"🔬 Режим супервизора активен\n\n"
            f"Ожидающих запросов: {len(pending)}\n\n"
            f"Команды:\n"
            f"/pending — посмотреть ожидающие запросы\n"
            f"/supervisor_off — отключить режим супервизора"
        )
        return
    
    # Проверяем, есть ли уже питомец
    pet = db.get_pet(user_id)
    
    if pet:
        await update.message.reply_text(
            f"С возвращением! 🐾\n\n"
            f"Твой питомец: {pet['name']} ({pet['type']})\n\n"
            f"Ты можешь:\n"
            f"— присылать фото и заметки\n"
            f"— /reminder — создать напоминание\n"
            f"— /history — посмотреть историю\n"
            f"— /export — отправить PDF от врача на расшифровку"
        )
    else:
        set_user_state(user_id, STATE_ONBOARDING_NAME)
        await update.message.reply_text(
            "Привет! Я помогу следить за здоровьем питомца. 🐾\n\n"
            "Как зовут питомца?"
        )


async def handle_onboarding(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка шагов онбординга"""
    user_id = update.effective_user.id
    state = get_user_state(user_id)
    text = update.message.text.strip()
    
    if state == STATE_ONBOARDING_NAME:
        # Сохраняем имя, спрашиваем тип
        set_user_state(user_id, STATE_ONBOARDING_TYPE, {"name": text})
        
        keyboard = [
            [
                InlineKeyboardButton("🐱 Кошка", callback_data="pet_type_кошка"),
                InlineKeyboardButton("🐶 Собака", callback_data="pet_type_собака"),
            ],
            [
                InlineKeyboardButton("🐹 Другое", callback_data="pet_type_другое"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"{text} — отличное имя! Это кошка или собака?",
            reply_markup=reply_markup
        )
        return True
    
    return False


async def handle_pet_type_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка выбора типа питомца"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    pet_type = query.data.replace("pet_type_", "")
    user_data = get_user_data(user_id)
    
    if not user_data or "name" not in user_data:
        await query.edit_message_text("Что-то пошло не так. Напиши /start чтобы начать заново.")
        return
    
    pet_name = user_data["name"]
    
    # Создаём питомца
    db.create_pet(user_id, pet_name, pet_type)
    clear_user_state(user_id)
    
    await query.edit_message_text(
        f"Готово! 🎉\n\n"
        f"{pet_name} добавлен.\n\n"
        f"Ты можешь:\n"
        f"— присылать фото и заметки\n"
        f"— /reminder — создать напоминание\n"
        f"— /history — посмотреть историю\n"
        f"— /export — отправить PDF от врача на расшифровку"
    )


async def reminder_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /reminder — создание напоминания"""
    user_id = update.effective_user.id
    
    pet = db.get_pet(user_id)
    if not pet:
        await update.message.reply_text(
            "Сначала добавь питомца!\nНапиши /start"
        )
        return
    
    set_user_state(user_id, STATE_REMINDER_TEXT)
    await update.message.reply_text("Что нужно напомнить?")


async def handle_reminder_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка создания напоминания"""
    user_id = update.effective_user.id
    state = get_user_state(user_id)
    text = update.message.text.strip()
    
    if state == STATE_REMINDER_TEXT:
        set_user_state(user_id, STATE_REMINDER_TIME, {"text": text})
        
        keyboard = [
            [
                InlineKeyboardButton("Через 1 час", callback_data="remind_1h"),
                InlineKeyboardButton("Через 3 часа", callback_data="remind_3h"),
            ],
            [
                InlineKeyboardButton("Завтра утром", callback_data="remind_tomorrow_morning"),
                InlineKeyboardButton("Завтра вечером", callback_data="remind_tomorrow_evening"),
            ],
            [
                InlineKeyboardButton("Через неделю", callback_data="remind_1w"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "Когда напомнить?",
            reply_markup=reply_markup
        )
        return True
    
    return False


async def handle_reminder_time_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка выбора времени напоминания"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    time_choice = query.data.replace("remind_", "")
    user_data = get_user_data(user_id)
    
    if not user_data or "text" not in user_data:
        await query.edit_message_text("Что-то пошло не так. Напиши /reminder чтобы начать заново.")
        return
    
    reminder_text = user_data["text"]
    pet = db.get_pet(user_id)
    
    # Вычисляем время напоминания
    from datetime import timedelta
    now = datetime.now()
    
    time_deltas = {
        "1h": timedelta(hours=1),
        "3h": timedelta(hours=3),
        "tomorrow_morning": timedelta(days=1, hours=9 - now.hour),
        "tomorrow_evening": timedelta(days=1, hours=19 - now.hour),
        "1w": timedelta(weeks=1),
    }
    
    remind_at = now + time_deltas.get(time_choice, timedelta(hours=1))
    
    # Создаём напоминание
    db.create_reminder(user_id, pet["id"], reminder_text, remind_at)
    clear_user_state(user_id)
    
    time_str = remind_at.strftime("%d.%m в %H:%M")
    
    await query.edit_message_text(
        f"✅ Напоминание создано!\n\n"
        f"📝 {reminder_text}\n"
        f"⏰ {time_str}"
    )


async def handle_reminder_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка действий с напоминанием (выполнено/пропущено)"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    parts = data.split("_")
    action = parts[1]  # done или skip
    reminder_id = int(parts[2])
    
    status = "выполнено" if action == "done" else "пропущено"
    db.update_reminder_status(reminder_id, status)
    
    emoji = "👍" if action == "done" else "⏭"
    await query.edit_message_text(f"Отметил {emoji}")


async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /history — просмотр истории"""
    user_id = update.effective_user.id
    
    pet = db.get_pet(user_id)
    if not pet:
        await update.message.reply_text(
            "Сначала добавь питомца!\nНапиши /start"
        )
        return
    
    records = db.get_records(pet["id"], limit=10)
    
    if not records:
        await update.message.reply_text(
            f"У {pet['name']} пока нет записей.\n"
            f"Присылай фото и заметки — я всё сохраню!"
        )
        return
    
    history_text = f"📋 Последние события {pet['name']}:\n\n"
    
    for record in records:
        date = datetime.fromisoformat(record["created_at"]).strftime("%d %B")
        tag = f"· {record['tag']}" if record.get("tag") else ""
        text = record["text"][:50] + "..." if record["text"] and len(record["text"]) > 50 else (record["text"] or "")
        
        history_text += f"— {date} {tag}\n  {text}\n\n"
    
    await update.message.reply_text(history_text)


async def reminders_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /reminders — история напоминаний"""
    user_id = update.effective_user.id
    
    pet = db.get_pet(user_id)
    if not pet:
        await update.message.reply_text(
            "Сначала добавь питомца!\nНапиши /start"
        )
        return
    
    reminders = db.get_reminders_history(pet["id"], limit=10)
    
    if not reminders:
        await update.message.reply_text(
            f"У {pet['name']} пока нет напоминаний.\n"
            f"Создай первое: /reminder"
        )
        return
    
    text = f"🔔 Напоминания {pet['name']}:\n\n"
    
    for r in reminders:
        status_emoji = "✅" if r["status"] == "выполнено" else "⏭" if r["status"] == "пропущено" else "⏳"
        text += f"— {r['text']} · {status_emoji} {r['status']}\n"
    
    await update.message.reply_text(text)


async def export_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /export — отправка PDF на расшифровку"""
    user_id = update.effective_user.id
    
    pet = db.get_pet(user_id)
    if not pet:
        await update.message.reply_text(
            "Сначала добавь питомца!\nНапиши /start"
        )
        return
    
    # Проверяем, есть ли супервизоры в системе
    supervisors = db.get_all_supervisors()
    if not supervisors:
        await update.message.reply_text(
            "⚠️ Сервис расшифровки временно недоступен.\n"
            "Попробуйте позже."
        )
        return
    
    set_user_state(user_id, STATE_WAITING_FOR_PDF, {"pet_id": pet["id"]})
    await update.message.reply_text(
        "📄 Отправь PDF документ от врача.\n\n"
        "Наш специалист расшифрует его и добавит в историю здоровья питомца."
    )


async def handle_pdf_for_transcription(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка PDF документа для расшифровки"""
    user_id = update.effective_user.id
    state = get_user_state(user_id)
    
    if state != STATE_WAITING_FOR_PDF:
        return False
    
    if not update.message.document:
        await update.message.reply_text(
            "Пожалуйста, отправь документ в формате PDF."
        )
        return True
    
    document = update.message.document
    if not document.file_name.lower().endswith('.pdf'):
        await update.message.reply_text(
            "Пожалуйста, отправь документ в формате PDF."
        )
        return True
    
    user_data = get_user_data(user_id)
    pet_id = user_data.get("pet_id")
    
    if not pet_id:
        await update.message.reply_text(
            "Произошла ошибка. Попробуй /export снова."
        )
        clear_user_state(user_id)
        return True
    
    # Создаём запрос на расшифровку
    request_id = db.create_transcription_request(user_id, pet_id, document.file_id)
    clear_user_state(user_id)
    
    await update.message.reply_text(
        "✅ Документ получен!\n\n"
        "Запрос отправлен специалисту на расшифровку.\n"
        "Я уведомлю тебя, когда расшифровка будет готова."
    )
    
    # Уведомляем всех супервизоров о новом запросе
    await notify_supervisors_about_new_request(context, request_id)
    
    return True


async def notify_supervisors_about_new_request(context: ContextTypes.DEFAULT_TYPE, request_id: int):
    """Уведомление супервизоров о новом запросе"""
    request = db.get_transcription_request(request_id)
    if not request:
        return
    
    pet = db.get_pet_by_id(request["pet_id"])
    supervisors = db.get_all_supervisors()
    
    keyboard = [
        [InlineKeyboardButton("📝 Взять в работу", callback_data=f"take_request_{request_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    for supervisor in supervisors:
        try:
            await context.bot.send_message(
                chat_id=supervisor["user_id"],
                text=f"🔔 Новый запрос на расшифровку!\n\n"
                     f"Питомец: {pet['name']} ({pet['type']})\n"
                     f"Запрос #{request_id}",
                reply_markup=reply_markup
            )
        except Exception as e:
            logger.error(f"Не удалось уведомить супервизора {supervisor['user_id']}: {e}")


async def handle_take_request_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка взятия запроса в работу супервизором"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    request_id = int(query.data.replace("take_request_", ""))
    
    # Проверяем, что пользователь - супервизор
    if not db.is_supervisor(user_id):
        await query.edit_message_text("⛔ У вас нет прав супервизора.")
        return
    
    # Проверяем, что запрос ещё доступен
    request = db.get_transcription_request(request_id)
    if not request or request["status"] != "pending":
        await query.edit_message_text("⚠️ Этот запрос уже взят в работу.")
        return
    
    # Назначаем запрос супервизору
    supervisor = db.get_supervisor_by_user_id(user_id)
    db.assign_transcription_to_supervisor(request_id, supervisor["id"])
    
    # Отправляем PDF супервизору
    pet = db.get_pet_by_id(request["pet_id"])
    
    try:
        await context.bot.send_document(
            chat_id=user_id,
            document=request["pdf_file_id"],
            caption=f"📄 PDF для расшифровки\n\n"
                    f"Питомец: {pet['name']} ({pet['type']})\n"
                    f"Запрос #{request_id}\n\n"
                    f"Напиши расшифровку текстом."
        )
        
        set_user_state(user_id, STATE_SUPERVISOR_TRANSCRIPTION, {
            "request_id": request_id,
            "user_id": request["user_id"],
            "pet_id": request["pet_id"]
        })
        
        await query.edit_message_text(
            f"✅ Запрос #{request_id} взят в работу!\n\n"
            f"Документ отправлен. Напиши расшифровку."
        )
    except Exception as e:
        logger.error(f"Ошибка при отправке PDF: {e}")
        await query.edit_message_text(
            f"⚠️ Ошибка при загрузке документа: {e}"
        )


async def handle_supervisor_transcription(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка расшифровки от супервизора"""
    user_id = update.effective_user.id
    state = get_user_state(user_id)
    
    if state != STATE_SUPERVISOR_TRANSCRIPTION:
        return False
    
    if not update.message.text:
        await update.message.reply_text(
            "Пожалуйста, отправь текстовую расшифровку документа."
        )
        return True
    
    transcription = update.message.text.strip()
    user_data = get_user_data(user_id)
    
    request_id = user_data.get("request_id")
    original_user_id = user_data.get("user_id")
    pet_id = user_data.get("pet_id")
    
    if not all([request_id, original_user_id, pet_id]):
        await update.message.reply_text(
            "Произошла ошибка. Попробуйте взять запрос заново."
        )
        clear_user_state(user_id)
        return True
    
    # Сохраняем расшифровку
    db.complete_transcription_request(request_id, transcription)
    
    # Сохраняем в записи питомца
    db.create_record(
        pet_id=pet_id,
        text=transcription,
        tag="визит к врачу",
        description="Расшифровка визита от супервизора",
        is_visit=True
    )
    
    clear_user_state(user_id)
    
    await update.message.reply_text(
        f"✅ Расшифровка сохранена!\n\n"
        f"Запрос #{request_id} выполнен. Пользователь получил уведомление."
    )
    
    # Уведомляем пользователя
    try:
        pet = db.get_pet_by_id(pet_id)
        await context.bot.send_message(
            chat_id=original_user_id,
            text=f"📄 Расшифровка готова!\n\n"
                 f"Документ для {pet['name']} был расшифрован:\n\n"
                 f"{transcription[:500]}{'...' if len(transcription) > 500 else ''}\n\n"
                 f"Полная расшифровка добавлена в историю.\n"
                 f"Используй /history чтобы посмотреть."
        )
    except Exception as e:
        logger.error(f"Не удалось уведомить пользователя {original_user_id}: {e}")
    
    return True


async def pending_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /pending — просмотр ожидающих запросов (для супервизоров)"""
    user_id = update.effective_user.id
    
    if not db.is_supervisor(user_id):
        await update.message.reply_text(
            "⛔ Эта команда доступна только супервизорам."
        )
        return
    
    pending = db.get_pending_transcription_requests()
    
    if not pending:
        await update.message.reply_text(
            "📭 Нет ожидающих запросов."
        )
        return
    
    text = "📋 Ожидающие запросы:\n\n"
    
    for req in pending:
        pet = db.get_pet_by_id(req["pet_id"])
        created = datetime.fromisoformat(req["created_at"]).strftime("%d.%m %H:%M")
        text += f"#{req['id']} — {pet['name']} ({pet['type']}) · {created}\n"
    
    keyboard = []
    for req in pending[:5]:  # Показываем кнопки для первых 5
        keyboard.append([
            InlineKeyboardButton(
                f"Взять запрос #{req['id']}", 
                callback_data=f"take_request_{req['id']}"
            )
        ])
    
    reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
    await update.message.reply_text(text, reply_markup=reply_markup)


async def supervisor_on_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /supervisor_on — активация режима супервизора"""
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name
    
    db.add_supervisor(user_id, username)
    
    await update.message.reply_text(
        "🔬 Режим супервизора активирован!\n\n"
        "Доступные команды:\n"
        "/pending — посмотреть ожидающие запросы\n"
        "/supervisor_off — отключить режим"
    )


async def supervisor_off_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /supervisor_off — деактивация режима супервизора"""
    user_id = update.effective_user.id
    
    db.remove_supervisor(user_id)
    clear_user_state(user_id)
    
    await update.message.reply_text(
        "👋 Режим супервизора отключён."
    )


async def handle_record(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка записей (текст/фото)"""
    user_id = update.effective_user.id
    
    # Проверяем, не в процессе ли супервизор расшифровки
    state = get_user_state(user_id)
    
    if state == STATE_SUPERVISOR_TRANSCRIPTION:
        await handle_supervisor_transcription(update, context)
        return
    
    if state == STATE_ONBOARDING_NAME:
        await handle_onboarding(update, context)
        return
    
    if state == STATE_REMINDER_TEXT:
        await handle_reminder_flow(update, context)
        return
    
    if state == STATE_WAITING_FOR_PDF:
        return  # PDF обрабатывается отдельно
    
    # Проверяем, есть ли питомец
    pet = db.get_pet(user_id)
    if not pet:
        set_user_state(user_id, STATE_ONBOARDING_NAME)
        await update.message.reply_text(
            "Привет! Давай сначала добавим питомца.\n\n"
            "Как зовут питомца?"
        )
        return
    
    # Обрабатываем как запись
    text = update.message.text or update.message.caption or ""
    photo_id = None
    
    if update.message.photo:
        photo_id = update.message.photo[-1].file_id
    
    if not text and not photo_id:
        return
    
    # Автоматическое определение тега
    tag = auto_detect_tag(text)
    
    # Сохраняем запись
    db.create_record(pet["id"], text, photo_id, tag)
    
    response = "✅ Я сохранил запись."
    if tag:
        response += f"\n🏷 Тег: {tag}"
    
    await update.message.reply_text(response)


def auto_detect_tag(text: str) -> Optional[str]:
    """Простое автоматическое определение тега"""
    text_lower = text.lower()
    
    tag_keywords = {
        "вакцинация": ["прививка", "вакцин", "укол"],
        "осмотр": ["врач", "ветеринар", "клиника", "осмотр", "приём"],
        "лекарство": ["лекарств", "таблетк", "капл", "мазь", "препарат"],
        "анализы": ["анализ", "кровь", "моча", "узи"],
        "обработка": ["обработка", "блох", "клещ", "глист", "паразит"],
        "кормление": ["корм", "еда", "питание", "диета"],
    }
    
    for tag, keywords in tag_keywords.items():
        if any(kw in text_lower for kw in keywords):
            return tag
    
    return None


async def send_pending_reminders(context: ContextTypes.DEFAULT_TYPE):
    """Отправка напоминаний (запускается по расписанию)"""
    pending = db.get_pending_reminders()
    
    for reminder in pending:
        pet = db.get_pet_by_id(reminder["pet_id"])
        
        keyboard = [
            [
                InlineKeyboardButton("✅ Выполнено", callback_data=f"reminder_done_{reminder['id']}"),
                InlineKeyboardButton("⏭ Пропущено", callback_data=f"reminder_skip_{reminder['id']}"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        try:
            await context.bot.send_message(
                chat_id=reminder["user_id"],
                text=f"🔔 Напоминание:\n\n{reminder['text']}\n\n({pet['name']})",
                reply_markup=reply_markup
            )
            db.mark_reminder_sent(reminder["id"])
        except Exception as e:
            logger.error(f"Не удалось отправить напоминание {reminder['id']}: {e}")


async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Роутер для callback запросов"""
    query = update.callback_query
    data = query.data
    
    if data.startswith("pet_type_"):
        await handle_pet_type_callback(update, context)
    elif data.startswith("remind_"):
        await handle_reminder_time_callback(update, context)
    elif data.startswith("reminder_"):
        await handle_reminder_action(update, context)
    elif data.startswith("take_request_"):
        await handle_take_request_callback(update, context)


def main():
    """Запуск бота"""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        print("❌ Установите TELEGRAM_BOT_TOKEN в переменных окружения")
        print("   export TELEGRAM_BOT_TOKEN='ваш_токен'")
        return
    
    # Создаём приложение
    app = Application.builder().token(token).build()
    
    # Регистрируем обработчики
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reminder", reminder_command))
    app.add_handler(CommandHandler("history", history_command))
    app.add_handler(CommandHandler("reminders", reminders_command))
    app.add_handler(CommandHandler("export", export_command))
    app.add_handler(CommandHandler("pending", pending_command))
    app.add_handler(CommandHandler("supervisor_on", supervisor_on_command))
    app.add_handler(CommandHandler("supervisor_off", supervisor_off_command))
    
    # Callback обработчики
    app.add_handler(CallbackQueryHandler(callback_router))
    
    # Обработчик PDF документов
    app.add_handler(MessageHandler(filters.Document.PDF, handle_pdf_for_transcription))
    
    # Обработчик записей (текст и фото)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_record))
    app.add_handler(MessageHandler(filters.PHOTO, handle_record))
    
    # Запускаем проверку напоминаний каждую минуту
    job_queue = app.job_queue
    job_queue.run_repeating(send_pending_reminders, interval=60, first=10)
    
    print("🚀 Бот запущен!")
    print("📋 Доступные команды:")
    print("   /supervisor_on — активировать режим супервизора")
    print("   /supervisor_off — деактивировать режим супервизора")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
