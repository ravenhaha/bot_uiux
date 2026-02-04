"""
Telegram бот для отслеживания здоровья питомцев с системой супервизоров
"""

import os
import json
import logging
from datetime import datetime, timedelta
from typing import Optional
from pathlib import Path

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, InputFile
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)


def get_main_menu_keyboard():
    """Главное меню с кнопками"""
    keyboard = [
        [KeyboardButton("🐾 Мой питомец"), KeyboardButton("🔔 Напоминания")],
        [KeyboardButton("📋 История"), KeyboardButton("📄 Экспорт PDF")],
        [KeyboardButton("📝 Заметка")],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

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
STATE_ONBOARDING_TIMEZONE = "onboarding_timezone"
STATE_ONBOARDING_GENDER = "onboarding_gender"
STATE_ONBOARDING_BREED = "onboarding_breed"
STATE_ONBOARDING_BIRTHDATE = "onboarding_birthdate"
STATE_ONBOARDING_WEIGHT = "onboarding_weight"
STATE_ONBOARDING_VACCINATIONS = "onboarding_vaccinations"
STATE_ONBOARDING_PHOTO = "onboarding_photo"
STATE_ONBOARDING_OWNER = "onboarding_owner"
STATE_REMINDER_TEXT = "reminder_text"
STATE_REMINDER_DAY = "reminder_day"
STATE_REMINDER_TIME = "reminder_time"
STATE_REMINDER_RECURRING = "reminder_recurring"
STATE_EDIT_REMINDER_TEXT = "edit_reminder_text"
STATE_EDIT_REMINDER_DAY = "edit_reminder_day"
STATE_EDIT_REMINDER_TIME = "edit_reminder_time"
STATE_EDIT_PET_NAME = "edit_pet_name"
STATE_WAITING_FOR_PDF = "waiting_for_pdf"
STATE_SUPERVISOR_TRANSCRIPTION = "supervisor_transcription"
STATE_NORMAL = "normal"
STATE_NOTE_TEXT = "note_text"
STATE_NOTE_TAG = "note_tag"

# Серверный часовой пояс (Москва)
SERVER_TIMEZONE = "+03:00"


def parse_timezone_offset(tz_str: str) -> int:
    """Парсит строку часового пояса в минуты смещения от UTC"""
    # Формат: +03:00 или -05:30
    sign = 1 if tz_str[0] == '+' else -1
    parts = tz_str[1:].split(':')
    hours = int(parts[0])
    minutes = int(parts[1]) if len(parts) > 1 else 0
    return sign * (hours * 60 + minutes)


def convert_user_time_to_server(user_time: datetime, user_tz: str) -> datetime:
    """Конвертирует время пользователя в серверное (МСК)"""
    user_offset = parse_timezone_offset(user_tz)
    server_offset = parse_timezone_offset(SERVER_TIMEZONE)

    # Разница в минутах между часовыми поясами
    diff_minutes = user_offset - server_offset

    # Если пользователь впереди сервера, вычитаем разницу
    # Если позади - прибавляем
    server_time = user_time - timedelta(minutes=diff_minutes)
    return server_time


def convert_server_time_to_user(server_time: datetime, user_tz: str) -> datetime:
    """Конвертирует серверное время в время пользователя"""
    user_offset = parse_timezone_offset(user_tz)
    server_offset = parse_timezone_offset(SERVER_TIMEZONE)

    diff_minutes = user_offset - server_offset
    user_time = server_time + timedelta(minutes=diff_minutes)
    return user_time


# Дни недели
DAYS_OF_WEEK = {
    0: "Понедельник",
    1: "Вторник",
    2: "Среда",
    3: "Четверг",
    4: "Пятница",
    5: "Суббота",
    6: "Воскресенье"
}

# Сокращения дней недели для кнопок
DAY_ABBREV = {
    0: "ПН",
    1: "ВТ",
    2: "СР",
    3: "ЧТ",
    4: "ПТ",
    5: "СБ",
    6: "ВС",
}

# Часовые пояса (популярные)
TIMEZONES = [
    ("-12:00", "UTC-12:00"),
    ("-11:00", "UTC-11:00"),
    ("-10:00", "UTC-10:00"),
    ("-09:00", "UTC-09:00"),
    ("-08:00", "UTC-08:00"),
    ("-07:00", "UTC-07:00"),
    ("-06:00", "UTC-06:00"),
    ("-05:00", "UTC-05:00"),
    ("-04:00", "UTC-04:00"),
    ("-03:00", "UTC-03:00"),
    ("-02:00", "UTC-02:00"),
    ("-01:00", "UTC-01:00"),
    ("+00:00", "UTC+00:00"),
    ("+01:00", "UTC+01:00"),
    ("+02:00", "UTC+02:00"),
    ("+03:00", "UTC+03:00"),
    ("+04:00", "UTC+04:00"),
    ("+05:00", "UTC+05:00"),
    ("+05:30", "UTC+05:30"),
    ("+06:00", "UTC+06:00"),
    ("+07:00", "UTC+07:00"),
    ("+08:00", "UTC+08:00"),
    ("+09:00", "UTC+09:00"),
    ("+10:00", "UTC+10:00"),
    ("+11:00", "UTC+11:00"),
    ("+12:00", "UTC+12:00"),
]


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
    # На всякий случай очищаем старые состояния (напоминания и т.п.),
    # чтобы они не мешали новому онбордингу
    clear_user_state(user_id)
    
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
        tz_info = f"\nЧасовой пояс: UTC{pet.get('timezone', '+03:00')}" if pet.get('timezone') else ""
        await update.message.reply_text(
            f"С возвращением! 🐾\n\n"
            f"Твой питомец: {pet['name']} ({pet['type']}){tz_info}\n\n"
            f"Ты можешь присылать фото и заметки о питомце.\n"
            f"Используй меню внизу для навигации.",
            reply_markup=get_main_menu_keyboard()
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
    text = (update.message.text or "").strip()
    
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

    # Дополнительные вопросы онбординга (пол, порода, дата рождения, вес, прививки, владелец)
    from database import Database  # только для подсветки типов, в рантайме уже импортировано

    if state == STATE_ONBOARDING_GENDER:
        # Пол питомца
        gender_norm = text.lower()
        gender = None
        if gender_norm in ("м", "мальчик", "самец"):
            gender = "м"
        elif gender_norm in ("ж", "девочка", "самка"):
            gender = "ж"

        if not gender and gender_norm and not gender_norm.startswith("пропус"):
            await update.message.reply_text(
                "Укажи пол питомца: м/ж.\n\n"
                "Чтобы пропустить пункт, напиши «Пропустить»."
            )
            return True

        if gender:
            db.update_pet_details(user_id, gender=gender)

        set_user_state(user_id, STATE_ONBOARDING_BREED)
        await update.message.reply_text(
            "Какой породы питомец?\n\n"
            "Например: «британская короткошёрстная» или «лабрадор».\n"
            "Чтобы пропустить пункт, напиши «Пропустить»."
        )
        return True

    if state == STATE_ONBOARDING_BREED:
        if text and not text.lower().startswith("пропус"):
            db.update_pet_details(user_id, breed=text)

        set_user_state(user_id, STATE_ONBOARDING_BIRTHDATE)
        await update.message.reply_text(
            "Когда у питомца дата рождения?\n\n"
            "Формат: ДД.ММ.ГГГГ, например 05.03.2021.\n"
            "Можно написать «Пропустить»."
        )
        return True

    if state == STATE_ONBOARDING_BIRTHDATE:
        if text and not text.lower().startswith("пропус"):
            # Лёгкая валидация формата, но не жесткая
            import re
            if re.match(r"^\d{1,2}\.\d{1,2}\.\d{4}$", text):
                db.update_pet_details(user_id, birth_date=text)
            else:
                await update.message.reply_text(
                    "Не похоже на дату. Введи в формате ДД.ММ.ГГГГ.\n\n"
                    "Чтобы пропустить пункт, напиши «Пропустить»."
                )
                return True

        set_user_state(user_id, STATE_ONBOARDING_WEIGHT)
        await update.message.reply_text(
            "Сколько весит питомец сейчас? (в кг)\n\n"
            "Например: 4.2\n"
            "Чтобы пропустить пункт, напиши «Пропустить»."
        )
        return True

    if state == STATE_ONBOARDING_WEIGHT:
        if text and not text.lower().startswith("пропус"):
            try:
                weight = float(text.replace(",", "."))
                db.update_pet_details(user_id, weight=weight)
            except ValueError:
                await update.message.reply_text(
                    "Не получилось распознать вес. Введи число, например 4.2.\n\n"
                    "Чтобы пропустить пункт, напиши «Пропустить»."
                )
                return True

        set_user_state(user_id, STATE_ONBOARDING_VACCINATIONS)
        await update.message.reply_text(
            "Есть ли сведения о вакцинации?\n\n"
            "Например: «комплексная прививка весна 2024», «бешенство февраль 2025».\n"
            "Чтобы пропустить пункт, напиши «Пропустить»."
        )
        return True

    if state == STATE_ONBOARDING_VACCINATIONS:
        if text and not text.lower().startswith("пропус"):
            db.update_pet_details(user_id, vaccinations=text)

        set_user_state(user_id, STATE_ONBOARDING_PHOTO)
        await update.message.reply_text(
            "Пришли, пожалуйста, фото питомца 🐾\n\n"
            "Чтобы пропустить пункт, напиши «Пропустить»."
        )
        return True

    if state == STATE_ONBOARDING_OWNER:
        if text and not text.lower().startswith("пропус"):
            db.update_pet_details(user_id, owner_name=text)

        # После завершения анкеты формируем мини-PDF «паспорт питомца»
        pet = db.get_pet(user_id)

        # Пытаемся скачать фото питомца, если оно есть
        pet_photo_path = None
        photo_id = pet.get("photo_id") if pet else None
        if photo_id:
            try:
                file = await context.bot.get_file(photo_id)
                pet_photo_path = f"/tmp/pet_{pet['id']}_passport.jpg"
                await file.download_to_drive(pet_photo_path)
            except Exception as e:
                logger.error(f"Не удалось скачать фото питомца для паспорта: {e}")
                pet_photo_path = None

        if pet:
            try:
                # Мини-отчёт без записей и напоминаний
                pdf_path = generate_pdf_report(pet, [], [], pet_photo_path)
                from telegram import InputFile  # локальный импорт на всякий случай
                from pathlib import Path as _Path

                await update.message.reply_text(
                    "Готово! Я собрал мини‑паспорт питомца в PDF и прикрепил ниже."
                )

                with open(pdf_path, "rb") as f:
                    await context.bot.send_document(
                        chat_id=user_id,
                        document=InputFile(f, filename=_Path(pdf_path).name),
                        caption="📄 Паспорт питомца"
                    )
            except Exception as e:
                logger.error(f"Ошибка при генерации паспорта питомца: {e}")

        clear_user_state(user_id)
        await update.message.reply_text(
            "Спасибо! Я сохранил данные о питомце и владельце. 🐾\n\n"
            "Теперь можно присылать заметки и пользоваться напоминаниями.",
            reply_markup=get_main_menu_keyboard()
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

    # Сохраняем тип, переходим к выбору часового пояса
    user_data["type"] = pet_type
    set_user_state(user_id, STATE_ONBOARDING_TIMEZONE, user_data)
    
    # Показываем популярные часовые пояса (без названий городов)
    keyboard = [
        [InlineKeyboardButton("UTC+03:00", callback_data="tz_+03:00")],
        [InlineKeyboardButton("UTC+02:00", callback_data="tz_+02:00")],
        [InlineKeyboardButton("UTC+05:00", callback_data="tz_+05:00")],
        [InlineKeyboardButton("UTC+06:00", callback_data="tz_+06:00")],
        [InlineKeyboardButton("Другой часовой пояс...", callback_data="tz_other")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        "Укажи свой часовой пояс для корректных напоминаний.\n\n"
        "Часовой пояс указывается в формате смещения от UTC (Гринвича).\n"
        "Например: UTC+03:00 — это московское время.\n\n"
        "Выбери свой часовой пояс:",
        reply_markup=reply_markup
    )


async def handle_timezone_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка выбора часового пояса"""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    data = query.data

    if data == "tz_other":
        # Показываем полный список
        keyboard = []
        row = []
        for tz_offset, tz_name in TIMEZONES:
            row.append(InlineKeyboardButton(tz_name, callback_data=f"tz_{tz_offset}"))
            if len(row) == 2:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)

        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "Выбери свой часовой пояс:",
            reply_markup=reply_markup
        )
        return

    # Извлекаем часовой пояс
    timezone = data.replace("tz_", "")
    user_data = get_user_data(user_id)

    if not user_data or "name" not in user_data or "type" not in user_data:
        await query.edit_message_text("Что-то пошло не так. Напиши /start чтобы начать заново.")
        return

    pet_name = user_data["name"]
    pet_type = user_data["type"]

    # Создаём питомца с часовым поясом
    db.create_pet(user_id, pet_name, pet_type, timezone)
    # Переходим к расширенному онбордингу (пол, порода и т.д.)
    set_user_state(user_id, STATE_ONBOARDING_GENDER)
    
    await query.edit_message_text(
        f"Готово! 🎉\n\n"
        f"{pet_name} добавлен.\n"
        f"Часовой пояс: UTC{timezone}\n\n"
        f"Давай добавим ещё немного информации.\n\n"
        f"Какой пол у питомца? м/ж\n"
        f"Можно написать «Пропустить»."
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
        set_user_state(user_id, STATE_REMINDER_DAY, {"text": text})

        # Выбор дня
        from datetime import timedelta
        today = datetime.now()

        keyboard = [
            [
                InlineKeyboardButton("Сегодня", callback_data="day_today"),
                InlineKeyboardButton("Завтра", callback_data="day_tomorrow"),
            ],
            [
                InlineKeyboardButton("Через 1 час", callback_data="day_quick_1h"),
                InlineKeyboardButton("Через 3 часа", callback_data="day_quick_3h"),
            ],
        ]

        # Добавляем дни недели
        days_row = []
        for i in range(7):
            day = (today + timedelta(days=i)).weekday()
            day_name = DAY_ABBREV[day]
            days_row.append(InlineKeyboardButton(day_name, callback_data=f"day_week_{day}"))
            if len(days_row) == 4:
                keyboard.append(days_row)
                days_row = []
        if days_row:
            keyboard.append(days_row)

        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            "Когда напомнить?\n\n"
            "Выбери день или быстрый вариант:",
            reply_markup=reply_markup
        )
        return True

    return False


async def handle_reminder_day_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка выбора дня для напоминания"""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    data = query.data
    user_data = get_user_data(user_id)

    if not user_data or "text" not in user_data:
        await query.edit_message_text("Что-то пошло не так. Напиши /reminder чтобы начать заново.")
        return

    from datetime import timedelta
    now = datetime.now()
    pet = db.get_pet(user_id)

    user_tz = pet.get("timezone", "+03:00")

    # Быстрые варианты (сразу создаём напоминание)
    # Время "через X часов" не зависит от часового пояса - просто добавляем к текущему
    if data == "day_quick_1h":
        remind_at = now + timedelta(hours=1)
        # Показываем пользователю время в его часовом поясе
        user_time = convert_server_time_to_user(remind_at, user_tz)
        db.create_reminder(user_id, pet["id"], user_data["text"], remind_at)
        clear_user_state(user_id)
        await query.edit_message_text(
            f"✅ Напоминание создано!\n\n"
            f"📝 {user_data['text']}\n"
            f"⏰ {user_time.strftime('%d.%m в %H:%M')}"
        )
        return

    if data == "day_quick_3h":
        remind_at = now + timedelta(hours=3)
        user_time = convert_server_time_to_user(remind_at, user_tz)
        db.create_reminder(user_id, pet["id"], user_data["text"], remind_at)
        clear_user_state(user_id)
        await query.edit_message_text(
            f"✅ Напоминание создано!\n\n"
            f"📝 {user_data['text']}\n"
            f"⏰ {user_time.strftime('%d.%m в %H:%M')}"
        )
        return

    # Определяем выбранный день
    if data == "day_today":
        user_data["day"] = now.weekday()
        user_data["date"] = now.date().isoformat()
    elif data == "day_tomorrow":
        tomorrow = now + timedelta(days=1)
        user_data["day"] = tomorrow.weekday()
        user_data["date"] = tomorrow.date().isoformat()
    elif data.startswith("day_week_"):
        day_of_week = int(data.replace("day_week_", ""))
        user_data["day"] = day_of_week
        # Находим ближайший такой день
        days_ahead = day_of_week - now.weekday()
        if days_ahead < 0:
            days_ahead += 7
        target_date = now + timedelta(days=days_ahead)
        user_data["date"] = target_date.date().isoformat()

    set_user_state(user_id, STATE_REMINDER_TIME, user_data)

    day_name = DAYS_OF_WEEK[user_data["day"]]
    await query.edit_message_text(
        f"День: {day_name}\n\n"
        f"Введи время в формате ЧЧ:ММ\n"
        f"Например: 09:30 или 14:00"
    )


async def handle_reminder_time_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ввода времени напоминания пользователем"""
    user_id = update.effective_user.id
    text = update.message.text.strip()
    user_data = get_user_data(user_id)

    if not user_data or "text" not in user_data or "date" not in user_data:
        await update.message.reply_text("Что-то пошло не так. Напиши /reminder чтобы начать заново.")
        clear_user_state(user_id)
        return

    # Проверяем формат времени
    import re
    time_match = re.match(r'^(\d{1,2}):(\d{2})$', text)
    if not time_match:
        await update.message.reply_text(
            "Неверный формат времени.\n\n"
            "Введи время в формате ЧЧ:ММ\n"
            "Например: 09:30 или 14:00"
        )
        return

    hours = int(time_match.group(1))
    minutes = int(time_match.group(2))

    if hours < 0 or hours > 23 or minutes < 0 or minutes > 59:
        await update.message.reply_text(
            "Некорректное время.\n\n"
            "Часы: 00-23, минуты: 00-59\n"
            "Например: 09:30 или 14:00"
        )
        return

    time_str = f"{hours:02d}:{minutes:02d}"
    user_data["time"] = time_str
    set_user_state(user_id, STATE_REMINDER_RECURRING, user_data)

    # Спрашиваем о повторении
    keyboard = [
        [InlineKeyboardButton("Одноразово", callback_data="recurring_no")],
        [InlineKeyboardButton("Каждый день", callback_data="recurring_daily")],
        [InlineKeyboardButton("Каждую неделю", callback_data="recurring_weekly")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    day_name = DAYS_OF_WEEK[user_data["day"]]
    await update.message.reply_text(
        f"День: {day_name}\n"
        f"Время: {time_str}\n\n"
        f"Как часто напоминать?",
        reply_markup=reply_markup
    )


async def handle_reminder_time_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка выбора времени напоминания (для обратной совместимости)"""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    data = query.data
    user_data = get_user_data(user_id)

    if not user_data or "text" not in user_data:
        await query.edit_message_text("Что-то пошло не так. Напиши /reminder чтобы начать заново.")
        return

    # Старый формат для обратной совместимости
    time_choice = data.replace("remind_", "")
    reminder_text = user_data["text"]
    pet = db.get_pet(user_id)

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

    db.create_reminder(user_id, pet["id"], reminder_text, remind_at)
    clear_user_state(user_id)

    time_str = remind_at.strftime("%d.%m в %H:%M")

    await query.edit_message_text(
        f"✅ Напоминание создано!\n\n"
        f"📝 {reminder_text}\n"
        f"⏰ {time_str}"
    )


async def handle_recurring_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка выбора повторения напоминания"""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    data = query.data
    user_data = get_user_data(user_id)

    if not user_data or "text" not in user_data or "date" not in user_data or "time" not in user_data:
        await query.edit_message_text("Что-то пошло не так. Используй меню 🔔 Напоминания.")
        return

    is_recurring = data == "recurring_weekly"
    is_daily = data == "recurring_daily"
    pet = db.get_pet(user_id)
    user_tz = pet.get("timezone", "+03:00")

    # Собираем дату и время пользователя
    date_parts = user_data["date"].split("-")
    time_parts = user_data["time"].split(":")

    user_remind_at = datetime(
        int(date_parts[0]), int(date_parts[1]), int(date_parts[2]),
        int(time_parts[0]), int(time_parts[1])
    )

    # Конвертируем в серверное время (МСК)
    server_remind_at = convert_user_time_to_server(user_remind_at, user_tz)

    # Создаём напоминание
    db.create_reminder(
        user_id=user_id,
        pet_id=pet["id"],
        text=user_data["text"],
        remind_at=server_remind_at,
        day_of_week=user_data["day"],
        time_of_day=user_data["time"],
        is_recurring=is_recurring,
        is_daily=is_daily
    )
    clear_user_state(user_id)

    day_name = DAYS_OF_WEEK[user_data["day"]]

    if is_daily:
        recurring_text = "\n🔄 Повторяется каждый день"
    elif is_recurring:
        recurring_text = "\n🔄 Повторяется каждую неделю"
    else:
        recurring_text = ""

    await query.edit_message_text(
        f"✅ Напоминание создано!\n\n"
        f"📝 {user_data['text']}\n"
        f"📅 {day_name}\n"
        f"⏰ {user_data['time']}{recurring_text}"
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

    # Проверяем, повторяющееся ли это напоминание
    reminder = db.get_reminder_by_id(reminder_id)
    emoji = "👍" if action == "done" else "⏭"

    if reminder and reminder.get("is_daily") and reminder.get("is_active", 1):
        # Для ежедневного напоминания автоматически сбрасываем на завтра
        time_of_day = reminder.get("time_of_day", "12:00")
        pet = db.get_pet_by_id(reminder["pet_id"])
        user_tz = pet.get("timezone", "+03:00") if pet else "+03:00"

        tomorrow = datetime.now() + timedelta(days=1)
        time_parts = time_of_day.split(":")

        user_remind_at = datetime(
            tomorrow.year, tomorrow.month, tomorrow.day,
            int(time_parts[0]), int(time_parts[1])
        )
        server_remind_at = convert_user_time_to_server(user_remind_at, user_tz)

        db.reset_reminder_for_next_week(reminder_id, server_remind_at)

        await query.edit_message_text(
            f"{emoji} Отмечено как {status}!\n\n"
            f"📅 Напоминание повторится завтра в {time_of_day}"
        )

    elif reminder and reminder.get("is_recurring") and reminder.get("is_active", 1):
        # Для еженедельного напоминания показываем запрос
        day_name = DAYS_OF_WEEK.get(reminder.get("day_of_week"), "")
        time_str = reminder.get("time_of_day", "")

        keyboard = [
            [InlineKeyboardButton("✅ Да, повторить", callback_data=f"repeat_yes_{reminder_id}")],
            [InlineKeyboardButton("❌ Отменить повторение", callback_data=f"repeat_no_{reminder_id}")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            f"{emoji} Отмечено как {status}!\n\n"
            f"🔄 Это еженедельное напоминание.\n"
            f"📅 {day_name} {time_str}\n\n"
            f"Повторить на следующей неделе?",
            reply_markup=reply_markup
        )
    else:
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
    
    records = db.get_all_records(pet["id"])
    
    if not records:
        await update.message.reply_text(
            f"У {pet['name']} пока нет записей.\n"
            f"Присылай фото и заметки — я всё сохраню!"
        )
        return
    
    # Формируем красивую ленту с тегами
    entries = []
    for record in records:
        try:
            dt = datetime.fromisoformat(record["created_at"])
            date_str = dt.strftime("%d.%m.%Y")
            time_str = dt.strftime("%H:%M")
        except Exception:
            date_str = record.get("created_at", "")[:10]
            time_str = ""
        tag_value = record.get("tag")
        if tag_value:
            tag_str = f"🏷 #{tag_value}"
        else:
            tag_str = "🏷 без тега"
        
        text = record.get("text") or ""
        photo_id = record.get("photo_id")
        if text:
            preview = text if len(text) <= 90 else text[:87] + "..."
            if photo_id:
                content_line = f"🖼 + ✏️ {preview}"
            else:
                content_line = f"✏️ {preview}"
        else:
            if photo_id:
                content_line = "🖼 Фото без подписи"
            else:
                content_line = "—"
        
        entry = (
            f"━━━━━━━━━━━━\n"
            f"📅 {date_str} {time_str}\n"
            f"{content_line}\n"
            f"{tag_str}"
        )
        entries.append(entry)
    
    header = f"📜 История заметок {pet['name']}:\n"
    # Разбиваем историю на несколько сообщений, чтобы не упереться в лимит Telegram
    chunk = header + "\n"
    for entry in entries:
        if len(chunk) + len(entry) + 2 > 3500:
            await update.message.reply_text(chunk.rstrip())
            chunk = ""
        chunk += entry + "\n\n"
    if chunk.strip():
        await update.message.reply_text(chunk.rstrip())


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


async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /profile — управление карточкой питомца"""
    user_id = update.effective_user.id

    pet = db.get_pet(user_id)
    if not pet:
        await update.message.reply_text(
            "У тебя пока нет питомца.\n"
            "Напиши /start чтобы добавить."
        )
        return

    tz = pet.get('timezone', '+03:00')

    keyboard = [
        [InlineKeyboardButton("✏️ Изменить имя", callback_data="pet_edit_name")],
        [InlineKeyboardButton("🐾 Изменить тип", callback_data="pet_edit_type")],
        [InlineKeyboardButton("🕐 Изменить часовой пояс", callback_data="pet_edit_tz")],
        [InlineKeyboardButton("🗑 Удалить карточку", callback_data="pet_delete")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"🐾 Карточка питомца\n\n"
        f"Имя: {pet['name']}\n"
        f"Тип: {pet['type']}\n"
        f"Часовой пояс: UTC{tz}\n\n"
        f"Выбери действие:",
        reply_markup=reply_markup
    )


async def handle_pet_edit_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка редактирования карточки питомца"""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    data = query.data

    pet = db.get_pet(user_id)
    if not pet:
        await query.edit_message_text("Питомец не найден. Напиши /start")
        return

    if data == "pet_edit_name":
        set_user_state(user_id, STATE_EDIT_PET_NAME)
        await query.edit_message_text(
            f"Текущее имя: {pet['name']}\n\n"
            f"Введи новое имя питомца:"
        )

    elif data == "pet_edit_type":
        keyboard = [
            [
                InlineKeyboardButton("🐱 Кошка", callback_data="pet_set_type_кошка"),
                InlineKeyboardButton("🐶 Собака", callback_data="pet_set_type_собака"),
            ],
            [
                InlineKeyboardButton("🐹 Другое", callback_data="pet_set_type_другое"),
            ],
            [InlineKeyboardButton("« Назад", callback_data="pet_back")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            f"Текущий тип: {pet['type']}\n\n"
            f"Выбери новый тип:",
            reply_markup=reply_markup
        )

    elif data == "pet_edit_tz":
        keyboard = [
            [InlineKeyboardButton("UTC+03:00", callback_data="pet_set_tz_+03:00")],
            [InlineKeyboardButton("UTC+02:00", callback_data="pet_set_tz_+02:00")],
            [InlineKeyboardButton("UTC+05:00", callback_data="pet_set_tz_+05:00")],
            [InlineKeyboardButton("UTC+06:00", callback_data="pet_set_tz_+06:00")],
            [InlineKeyboardButton("Другой часовой пояс...", callback_data="pet_tz_other")],
            [InlineKeyboardButton("« Назад", callback_data="pet_back")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        tz = pet.get('timezone', '+03:00')
        await query.edit_message_text(
            f"Текущий часовой пояс: UTC{tz}\n\n"
            f"Выбери новый:",
            reply_markup=reply_markup
        )

    elif data == "pet_delete":
        keyboard = [
            [
                InlineKeyboardButton("✅ Да, удалить", callback_data="pet_confirm_delete"),
                InlineKeyboardButton("❌ Отмена", callback_data="pet_back"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            f"⚠️ Удалить карточку питомца?\n\n"
            f"Будут удалены:\n"
            f"— Все записи о {pet['name']}\n"
            f"— Все напоминания\n"
            f"— История расшифровок\n\n"
            f"Это действие нельзя отменить!",
            reply_markup=reply_markup
        )

    elif data == "pet_confirm_delete":
        pet_name = pet['name']
        db.delete_pet(user_id)
        clear_user_state(user_id)

        await query.edit_message_text(
            f"🗑 Карточка {pet_name} удалена.\n\n"
            f"Чтобы добавить нового питомца, напиши /start"
        )

    elif data == "pet_back":
        tz = pet.get('timezone', '+03:00')
        keyboard = [
            [InlineKeyboardButton("✏️ Изменить имя", callback_data="pet_edit_name")],
            [InlineKeyboardButton("🐾 Изменить тип", callback_data="pet_edit_type")],
            [InlineKeyboardButton("🕐 Изменить часовой пояс", callback_data="pet_edit_tz")],
            [InlineKeyboardButton("🗑 Удалить карточку", callback_data="pet_delete")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            f"🐾 Карточка питомца\n\n"
            f"Имя: {pet['name']}\n"
            f"Тип: {pet['type']}\n"
            f"Часовой пояс: UTC{tz}\n\n"
            f"Выбери действие:",
            reply_markup=reply_markup
        )

    elif data.startswith("pet_set_type_"):
        new_type = data.replace("pet_set_type_", "")
        db.update_pet_type(user_id, new_type)

        await query.edit_message_text(
            f"✅ Тип питомца изменён на: {new_type}\n\n"
            f"Управление карточкой: /profile"
        )

    elif data.startswith("pet_set_tz_"):
        new_tz = data.replace("pet_set_tz_", "")
        db.update_pet_timezone(user_id, new_tz)

        await query.edit_message_text(
            f"✅ Часовой пояс изменён на: UTC{new_tz}\n\n"
            f"Управление карточкой: /profile"
        )

    elif data == "pet_tz_other":
        keyboard = []
        row = []
        for tz_offset, tz_name in TIMEZONES:
            row.append(InlineKeyboardButton(tz_name, callback_data=f"pet_set_tz_{tz_offset}"))
            if len(row) == 2:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)
        keyboard.append([InlineKeyboardButton("« Назад", callback_data="pet_edit_tz")])

        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "Выбери часовой пояс:",
            reply_markup=reply_markup
        )


async def handle_edit_pet_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка редактирования имени питомца"""
    user_id = update.effective_user.id
    new_name = update.message.text.strip()

    if len(new_name) > 50:
        await update.message.reply_text("Имя слишком длинное. Максимум 50 символов.")
        return

    db.update_pet_name(user_id, new_name)
    clear_user_state(user_id)

    await update.message.reply_text(
        f"✅ Имя питомца изменено на: {new_name}\n\n"
        f"Управление карточкой: /profile"
    )


async def my_reminders_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /my_reminders — управление напоминаниями"""
    user_id = update.effective_user.id

    pet = db.get_pet(user_id)
    if not pet:
        await update.message.reply_text(
            "Сначала добавь питомца!\nНапиши /start"
        )
        return

    reminders = db.get_all_user_reminders(user_id)

    if not reminders:
        await update.message.reply_text(
            f"У тебя нет активных напоминаний.\n"
            f"Создай первое: /reminder"
        )
        return

    text = f"🔔 Твои напоминания:\n\n"

    keyboard = []
    for r in reminders[:10]:
        # Формируем информацию о напоминании
        day_info = ""
        if r.get("day_of_week") is not None:
            day_info = f" · {DAY_ABBREV[r['day_of_week']]}"
        time_info = ""
        if r.get("time_of_day"):
            time_info = f" {r['time_of_day']}"

        recurring_icon = "🔄" if r.get("is_recurring") else ""
        active_icon = "" if r.get("is_active", 1) else "⏸"

        text += f"{active_icon}{recurring_icon} {r['text'][:30]}{day_info}{time_info}\n"

        keyboard.append([
            InlineKeyboardButton(f"⚙️ #{r['id']}: {r['text'][:15]}...", callback_data=f"manage_{r['id']}")
        ])

    keyboard.append([InlineKeyboardButton("➕ Новое напоминание", callback_data="new_reminder")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(text, reply_markup=reply_markup)


async def handle_manage_reminder_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка управления конкретным напоминанием"""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    data = query.data

    if data == "new_reminder":
        # Начинаем создание нового напоминания
        set_user_state(user_id, STATE_REMINDER_TEXT)
        await query.edit_message_text("Что нужно напомнить?")
        return

    if data.startswith("manage_"):
        reminder_id = int(data.replace("manage_", ""))
        reminder = db.get_reminder_by_id(reminder_id)

        if not reminder or reminder["user_id"] != user_id:
            await query.edit_message_text("Напоминание не найдено.")
            return

        # Показываем детали и действия
        day_info = ""
        if reminder.get("day_of_week") is not None:
            day_info = f"\n📅 {DAYS_OF_WEEK[reminder['day_of_week']]}"
        time_info = ""
        if reminder.get("time_of_day"):
            time_info = f"\n⏰ {reminder['time_of_day']}"

        recurring_info = ""
        if reminder.get("is_daily"):
            recurring_info = "\n📅 Повторяется каждый день"
        elif reminder.get("is_recurring"):
            recurring_info = "\n🔄 Повторяется каждую неделю"

        active_info = ""
        if not reminder.get("is_active", 1):
            active_info = "\n⏸ Приостановлено"

        text = (
            f"📝 {reminder['text']}"
            f"{day_info}{time_info}{recurring_info}{active_info}\n\n"
            f"Выбери действие:"
        )

        keyboard = [
            [InlineKeyboardButton("✏️ Изменить текст", callback_data=f"edit_text_{reminder_id}")],
            [InlineKeyboardButton("📅 Изменить день/время", callback_data=f"edit_time_{reminder_id}")],
        ]

        # Кнопка включения/отключения
        if reminder.get("is_active", 1):
            keyboard.append([InlineKeyboardButton("⏸ Приостановить", callback_data=f"pause_{reminder_id}")])
        else:
            keyboard.append([InlineKeyboardButton("▶️ Возобновить", callback_data=f"resume_{reminder_id}")])

        # Кнопка управления повторением
        if reminder.get("is_recurring"):
            keyboard.append([InlineKeyboardButton("🔄 Отключить повторение", callback_data=f"no_recur_{reminder_id}")])
        else:
            keyboard.append([InlineKeyboardButton("🔄 Включить повторение", callback_data=f"yes_recur_{reminder_id}")])

        keyboard.append([InlineKeyboardButton("🗑 Удалить", callback_data=f"delete_{reminder_id}")])
        keyboard.append([InlineKeyboardButton("« Назад", callback_data="back_to_list")])

        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text, reply_markup=reply_markup)


async def handle_reminder_actions_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка действий над напоминаниями"""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    data = query.data

    if data == "back_to_list":
        # Возвращаемся к списку
        reminders = db.get_all_user_reminders(user_id)
        if not reminders:
            await query.edit_message_text("У тебя нет активных напоминаний.")
            return

        text = f"🔔 Твои напоминания:\n\n"
        keyboard = []
        for r in reminders[:10]:
            day_info = ""
            if r.get("day_of_week") is not None:
                day_info = f" · {DAY_ABBREV[r['day_of_week']]}"
            time_info = ""
            if r.get("time_of_day"):
                time_info = f" {r['time_of_day']}"

            recurring_icon = "🔄" if r.get("is_recurring") else ""
            active_icon = "" if r.get("is_active", 1) else "⏸"

            text += f"{active_icon}{recurring_icon} {r['text'][:30]}{day_info}{time_info}\n"
            keyboard.append([
                InlineKeyboardButton(f"⚙️ #{r['id']}: {r['text'][:15]}...", callback_data=f"manage_{r['id']}")
            ])

        keyboard.append([InlineKeyboardButton("➕ Новое напоминание", callback_data="new_reminder")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text, reply_markup=reply_markup)
        return

    # Извлекаем ID напоминания
    parts = data.split("_")
    action = parts[0]
    reminder_id = int(parts[-1])

    reminder = db.get_reminder_by_id(reminder_id)
    if not reminder or reminder["user_id"] != user_id:
        await query.edit_message_text("Напоминание не найдено.")
        return

    if action == "pause":
        db.toggle_reminder_active(reminder_id, False)
        await query.edit_message_text(
            f"⏸ Напоминание приостановлено.\n\n"
            f"📝 {reminder['text']}\n\n"
            f"Для возобновления используй /my_reminders"
        )

    elif action == "resume":
        db.toggle_reminder_active(reminder_id, True)
        await query.edit_message_text(
            f"▶️ Напоминание возобновлено!\n\n"
            f"📝 {reminder['text']}"
        )

    elif action == "delete":
        # Подтверждение удаления
        keyboard = [
            [
                InlineKeyboardButton("✅ Да, удалить", callback_data=f"confirm_del_{reminder_id}"),
                InlineKeyboardButton("❌ Отмена", callback_data=f"manage_{reminder_id}"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            f"Удалить напоминание?\n\n📝 {reminder['text']}",
            reply_markup=reply_markup
        )

    elif action == "confirm" and parts[1] == "del":
        db.delete_reminder(reminder_id)
        await query.edit_message_text(
            f"🗑 Напоминание удалено.\n\n"
            f"Управление напоминаниями: /my_reminders"
        )

    elif action == "no" and parts[1] == "recur":
        db.disable_reminder_recurring(reminder_id)
        await query.edit_message_text(
            f"🔄 Повторение отключено.\n\n"
            f"📝 {reminder['text']}\n\n"
            f"Напоминание больше не будет повторяться."
        )

    elif action == "yes" and parts[1] == "recur":
        db.update_reminder(reminder_id, is_recurring=True)
        await query.edit_message_text(
            f"🔄 Повторение включено!\n\n"
            f"📝 {reminder['text']}\n\n"
            f"Напоминание будет повторяться еженедельно."
        )

    elif action == "edit" and parts[1] == "text":
        set_user_state(user_id, STATE_EDIT_REMINDER_TEXT, {"reminder_id": reminder_id})
        await query.edit_message_text(
            f"Текущий текст: {reminder['text']}\n\n"
            f"Введи новый текст напоминания:"
        )

    elif action == "edit" and parts[1] == "time":
        set_user_state(user_id, STATE_EDIT_REMINDER_DAY, {"reminder_id": reminder_id})

        from datetime import timedelta
        today = datetime.now()

        keyboard = [
            [
                InlineKeyboardButton("Сегодня", callback_data="editday_today"),
                InlineKeyboardButton("Завтра", callback_data="editday_tomorrow"),
            ],
        ]

        days_row = []
        for i in range(7):
            day = (today + timedelta(days=i)).weekday()
            day_name = DAY_ABBREV[day]
            days_row.append(InlineKeyboardButton(day_name, callback_data=f"editday_week_{day}"))
            if len(days_row) == 4:
                keyboard.append(days_row)
                days_row = []
        if days_row:
            keyboard.append(days_row)

        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            f"📝 {reminder['text']}\n\n"
            f"Выбери новый день:",
            reply_markup=reply_markup
        )


async def handle_edit_reminder_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка редактирования текста напоминания"""
    user_id = update.effective_user.id
    state = get_user_state(user_id)

    if state != STATE_EDIT_REMINDER_TEXT:
        return False

    new_text = update.message.text.strip()
    user_data = get_user_data(user_id)
    reminder_id = user_data.get("reminder_id")

    if not reminder_id:
        await update.message.reply_text("Что-то пошло не так. Попробуй /my_reminders")
        clear_user_state(user_id)
        return True

    db.update_reminder(reminder_id, text=new_text)
    clear_user_state(user_id)

    await update.message.reply_text(
        f"✅ Текст напоминания обновлён!\n\n"
        f"📝 {new_text}"
    )
    return True


async def handle_edit_day_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка редактирования дня напоминания"""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    data = query.data
    user_data = get_user_data(user_id)

    reminder_id = user_data.get("reminder_id")
    if not reminder_id:
        await query.edit_message_text("Что-то пошло не так. Попробуй /my_reminders")
        return

    from datetime import timedelta
    now = datetime.now()

    if data == "editday_today":
        user_data["day"] = now.weekday()
        user_data["date"] = now.date().isoformat()
    elif data == "editday_tomorrow":
        tomorrow = now + timedelta(days=1)
        user_data["day"] = tomorrow.weekday()
        user_data["date"] = tomorrow.date().isoformat()
    elif data.startswith("editday_week_"):
        day_of_week = int(data.replace("editday_week_", ""))
        user_data["day"] = day_of_week
        days_ahead = day_of_week - now.weekday()
        if days_ahead < 0:
            days_ahead += 7
        target_date = now + timedelta(days=days_ahead)
        user_data["date"] = target_date.date().isoformat()

    set_user_state(user_id, STATE_EDIT_REMINDER_TIME, user_data)

    day_name = DAYS_OF_WEEK[user_data["day"]]
    await query.edit_message_text(
        f"День: {day_name}\n\n"
        f"Введи время в формате ЧЧ:ММ\n"
        f"Например: 09:30 или 14:00"
    )


async def handle_edit_time_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка редактирования времени напоминания (ввод пользователем)"""
    user_id = update.effective_user.id
    text = update.message.text.strip()
    user_data = get_user_data(user_id)

    reminder_id = user_data.get("reminder_id")
    if not reminder_id or "date" not in user_data:
        await update.message.reply_text("Что-то пошло не так. Попробуй /my_reminders")
        clear_user_state(user_id)
        return

    # Проверяем формат времени
    import re
    time_match = re.match(r'^(\d{1,2}):(\d{2})$', text)
    if not time_match:
        await update.message.reply_text(
            "Неверный формат времени.\n\n"
            "Введи время в формате ЧЧ:ММ\n"
            "Например: 09:30 или 14:00"
        )
        return

    hours = int(time_match.group(1))
    minutes = int(time_match.group(2))

    if hours < 0 or hours > 23 or minutes < 0 or minutes > 59:
        await update.message.reply_text(
            "Некорректное время.\n\n"
            "Часы: 00-23, минуты: 00-59\n"
            "Например: 09:30 или 14:00"
        )
        return

    pet = db.get_pet(user_id)
    user_tz = pet.get("timezone", "+03:00")

    time_str = f"{hours:02d}:{minutes:02d}"
    date_parts = user_data["date"].split("-")

    # Время пользователя
    user_remind_at = datetime(
        int(date_parts[0]), int(date_parts[1]), int(date_parts[2]),
        hours, minutes
    )

    # Конвертируем в серверное время
    server_remind_at = convert_user_time_to_server(user_remind_at, user_tz)

    db.update_reminder(
        reminder_id,
        remind_at=server_remind_at,
        day_of_week=user_data["day"],
        time_of_day=time_str
    )

    # Сбрасываем флаг отправки, чтобы напоминание снова сработало
    with db._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE reminders SET sent = 0, status = 'pending' WHERE id = ?",
            (reminder_id,)
        )

    clear_user_state(user_id)

    day_name = DAYS_OF_WEEK[user_data["day"]]
    await update.message.reply_text(
        f"✅ Напоминание обновлено!\n\n"
        f"📅 {day_name}\n"
        f"⏰ {time_str}"
    )


async def export_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /export — экспорт истории в PDF"""
    user_id = update.effective_user.id
    
    pet = db.get_pet(user_id)
    if not pet:
        await update.message.reply_text(
            "Сначала добавь питомца!\nНапиши /start"
        )
        return

    await update.message.reply_text(
        "Я подготовлю PDF файл с историей заметок. Это может занять некоторое время…"
    )

    # Собираем данные
    records = db.get_all_records(pet["id"])
    reminders = db.get_reminders_history(pet["id"], limit=50)

    # Скачиваем фото питомца (если есть) для встраивания в PDF
    pet_photo_path = None
    photo_id = pet.get("photo_id")
    if photo_id:
        try:
            file = await context.bot.get_file(photo_id)
            pet_photo_path = f"/tmp/pet_{pet['id']}_avatar.jpg"
            await file.download_to_drive(pet_photo_path)
        except Exception as e:
            logger.error(f"Не удалось скачать фото питомца для PDF: {e}")
            pet_photo_path = None

    # Генерируем PDF отчёт
    pdf_path = generate_pdf_report(pet, records, reminders, pet_photo_path)

    # Краткая сводка о питомце в чате
    gender_map = {"м": "мальчик", "ж": "девочка"}
    gender_txt = gender_map.get(pet.get("gender"), "не указан")
    summary_lines = [
        f"🐾 {pet['name']}",
        f"Вид: {pet['type']}",
        f"Пол: {gender_txt}",
    ]
    if pet.get("breed"):
        summary_lines.append(f"Порода: {pet['breed']}")
    if pet.get("birth_date"):
        summary_lines.append(f"Дата рождения: {pet['birth_date']}")
    if pet.get("weight") is not None:
        summary_lines.append(f"Вес: {pet['weight']} кг")
    if pet.get("vaccinations"):
        summary_lines.append(f"Вакцинация: {pet['vaccinations']}")

    notes_count = len(records)
    summary_lines.append(f"Заметок в истории: {notes_count}")

    await update.message.reply_text("📋 Краткая карта питомца:\n\n" + "\n".join(summary_lines))

    # Отправляем PDF пользователю
    try:
        with open(pdf_path, "rb") as f:
            await context.bot.send_document(
                chat_id=user_id,
                document=InputFile(f, filename=Path(pdf_path).name),
                caption="📄 История по питомцу в формате PDF"
            )
    except Exception as e:
        logger.error(f"Ошибка при отправке PDF: {e}")
        await update.message.reply_text("⚠️ Не удалось отправить PDF. Попробуй ещё раз позже.")


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


async def handle_menu_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка кнопок главного меню"""
    user_id = update.effective_user.id
    text = update.message.text

    if text == "🐾 Мой питомец":
        await profile_command(update, context)
        return True
    elif text == "🔔 Напоминания":
        await reminders_menu(update, context)
        return True
    elif text == "📋 История":
        await history_command(update, context)
        return True
    elif text in ("📄 Экспорт PDF", "📄 Расшифровка"):
        await export_command(update, context)
        return True
    elif text == "📝 Заметка":
        pet = db.get_pet(user_id)
        if not pet:
            await update.message.reply_text(
                "Сначала добавь питомца!\nНапиши /start"
            )
            return True
        set_user_state(user_id, STATE_NOTE_TEXT)
        await update.message.reply_text(
            "✏️ Отправь текст заметки или фото с подписью.\n\n"
            "После этого я предложу выбрать тег."
        )
        return True

    return False


async def reminders_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Меню напоминаний"""
    user_id = update.effective_user.id

    pet = db.get_pet(user_id)
    if not pet:
        await update.message.reply_text(
            "Сначала добавь питомца!\n"
            "Нажми 🐾 Мой питомец"
        )
        return

    # Получаем количество активных напоминаний
    reminders = db.get_all_user_reminders(user_id)
    count = len(reminders)

    keyboard = [
        [InlineKeyboardButton("➕ Создать напоминание", callback_data="menu_new_reminder")],
        [InlineKeyboardButton(f"📋 Мои напоминания ({count})", callback_data="menu_my_reminders")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "🔔 Напоминания\n\n"
        "Выбери действие:",
        reply_markup=reply_markup
    )


async def handle_reminders_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка меню напоминаний"""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    data = query.data

    if data == "menu_new_reminder":
        set_user_state(user_id, STATE_REMINDER_TEXT)
        await query.edit_message_text("Что нужно напомнить?")

    elif data == "menu_my_reminders":
        reminders = db.get_all_user_reminders(user_id)

        if not reminders:
            keyboard = [
                [InlineKeyboardButton("➕ Создать напоминание", callback_data="menu_new_reminder")],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                "У тебя пока нет напоминаний.",
                reply_markup=reply_markup
            )
            return

        text = "📋 Твои напоминания:\n\n"

        keyboard = []
        for r in reminders[:10]:
            day_info = ""
            if r.get("day_of_week") is not None:
                day_info = f" · {DAY_ABBREV[r['day_of_week']]}"
            time_info = ""
            if r.get("time_of_day"):
                time_info = f" {r['time_of_day']}"

            if r.get("is_daily"):
                recurring_icon = "📅"  # каждый день
            elif r.get("is_recurring"):
                recurring_icon = "🔄"  # каждую неделю
            else:
                recurring_icon = ""
            active_icon = "⏸ " if not r.get("is_active", 1) else ""

            text += f"{active_icon}{recurring_icon} {r['text'][:30]}{day_info}{time_info}\n"

            keyboard.append([
                InlineKeyboardButton(f"⚙️ {r['text'][:20]}...", callback_data=f"manage_{r['id']}")
            ])

        keyboard.append([InlineKeyboardButton("➕ Создать напоминание", callback_data="menu_new_reminder")])
        keyboard.append([InlineKeyboardButton("« Назад", callback_data="menu_reminders_back")])

        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text, reply_markup=reply_markup)

    elif data == "menu_reminders_back":
        reminders = db.get_all_user_reminders(user_id)
        count = len(reminders)

        keyboard = [
            [InlineKeyboardButton("➕ Создать напоминание", callback_data="menu_new_reminder")],
            [InlineKeyboardButton(f"📋 Мои напоминания ({count})", callback_data="menu_my_reminders")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            "🔔 Напоминания\n\n"
            "Выбери действие:",
            reply_markup=reply_markup
        )


async def handle_record(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка записей (текст/фото)"""
    user_id = update.effective_user.id

    # Проверяем кнопки меню
    if update.message.text and await handle_menu_buttons(update, context):
        return

    # Проверяем, не в процессе ли супервизор расшифровки
    state = get_user_state(user_id)

    if state == STATE_SUPERVISOR_TRANSCRIPTION:
        await handle_supervisor_transcription(update, context)
        return

    if state in {
        STATE_ONBOARDING_NAME,
        STATE_ONBOARDING_GENDER,
        STATE_ONBOARDING_BREED,
        STATE_ONBOARDING_BIRTHDATE,
        STATE_ONBOARDING_WEIGHT,
        STATE_ONBOARDING_VACCINATIONS,
        STATE_ONBOARDING_OWNER,
    } and update.message.text:
        await handle_onboarding(update, context)
        return

    if state == STATE_REMINDER_TEXT:
        await handle_reminder_flow(update, context)
        return

    if state == STATE_EDIT_REMINDER_TEXT:
        await handle_edit_reminder_text(update, context)
        return

    if state == STATE_REMINDER_TIME:
        await handle_reminder_time_input(update, context)
        return

    if state == STATE_EDIT_REMINDER_TIME:
        await handle_edit_time_input(update, context)
        return

    if state == STATE_EDIT_PET_NAME:
        await handle_edit_pet_name(update, context)
        return
    
    if state == STATE_NOTE_TEXT:
        # Пришёл контент заметки для явного сохранения
        text = update.message.text or update.message.caption or ""
        photo_id = None
        if update.message.photo:
            photo_id = update.message.photo[-1].file_id
        
        if not text and not photo_id:
            await update.message.reply_text("Отправь текст или фото для заметки.")
            return
        
        # Сохраняем временно в state и просим выбрать тег
        set_user_state(user_id, STATE_NOTE_TEXT, {"text": text, "photo_id": photo_id})
        
        preview = text if text and len(text) <= 70 else (text[:67] + "...") if text else "без текста"
        
        keyboard = [
            [
                InlineKeyboardButton("💉 Вакцинация", callback_data="note_tag_вакцинация"),
                InlineKeyboardButton("🩺 Осмотр", callback_data="note_tag_осмотр"),
            ],
            [
                InlineKeyboardButton("💊 Лекарство", callback_data="note_tag_лекарство"),
                InlineKeyboardButton("🧪 Анализы", callback_data="note_tag_анализы"),
            ],
            [
                InlineKeyboardButton("🛡 Обработка", callback_data="note_tag_обработка"),
                InlineKeyboardButton("🍽 Кормление", callback_data="note_tag_кормление"),
            ],
            [
                InlineKeyboardButton("🏷 Свой тег", callback_data="note_tag_custom"),
                InlineKeyboardButton("🚫 Без тега", callback_data="note_tag_none"),
            ],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"Окей, сохраним заметку:\n\n«{preview}»\n\n"
            f"Выбери тег или введи свой.",
            reply_markup=reply_markup
        )
        return

    if state == STATE_WAITING_FOR_PDF:
        return  # PDF обрабатывается отдельно
    
    if state == STATE_NOTE_TAG and update.message.text:
        await handle_note_custom_tag_input(update, context)
        return

    if state == STATE_ONBOARDING_PHOTO:
        # Обработка фото питомца или пропуска
        photo_id = None
        if update.message.photo:
            photo_id = update.message.photo[-1].file_id
            db.update_pet_details(user_id, photo_id=photo_id)
        elif update.message.text and update.message.text.strip().lower().startswith("пропус"):
            # просто пропускаем без сохранения фото
            pass
        else:
            await update.message.reply_text(
                "Пришли фото питомца.\n\n"
                "Чтобы пропустить пункт, напиши «Пропустить»."
            )
            return

        set_user_state(user_id, STATE_ONBOARDING_OWNER)
        await update.message.reply_text(
            "Как тебя зовут? Напиши своё имя (или ФИ), чтобы я знал, как к тебе обращаться.\n\n"
            "Чтобы пропустить пункт, напиши «Пропустить»."
        )
        return
    
    # В обычном режиме (когда не активен специальный flow)
    # ничего не сохраняем автоматически, чтобы не плодить записи.
    # Пользователь должен явно нажать кнопку «📝 Заметка».
    return


async def handle_note_tag_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка выбора тега для заметки (inline-клавиатура)"""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    data = query.data

    user_data = get_user_data(user_id)
    if not user_data:
        await query.edit_message_text(
            "Не нашёл текст заметки. Нажми «📝 Заметка» и начни заново."
        )
        clear_user_state(user_id)
        return

    pet = db.get_pet(user_id)
    if not pet:
        await query.edit_message_text(
            "Сначала добавь питомца!\nНапиши /start"
        )
        clear_user_state(user_id)
        return

    text = user_data.get("text") or ""
    photo_id = user_data.get("photo_id")

    if data == "note_tag_custom":
        # Переходим к вводу собственного тега
        set_user_state(user_id, STATE_NOTE_TAG, {"text": text, "photo_id": photo_id})
        await query.edit_message_text(
            "Введи название тега для этой заметки.\n\n"
            "Например: «контроль веса», «сон», «игры»."
        )
        return

    if data == "note_tag_none":
        tag = None
    else:
        tag = data.replace("note_tag_", "")

    db.create_record(pet["id"], text, photo_id, tag)
    clear_user_state(user_id)

    tag_text = f"🏷 #{tag}" if tag else "🏷 без тега"
    await query.edit_message_text(
        f"✅ Заметка сохранена.\n{tag_text}"
    )


async def handle_note_custom_tag_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ввода собственного тега пользователем"""
    user_id = update.effective_user.id
    state = get_user_state(user_id)

    if state != STATE_NOTE_TAG:
        return

    tag = (update.message.text or "").strip()
    if not tag:
        await update.message.reply_text("Тег не должен быть пустым. Введи название тега.")
        return

    user_data = get_user_data(user_id)
    if not user_data:
        await update.message.reply_text(
            "Не нашёл текст заметки. Нажми «📝 Заметка» и начни заново."
        )
        clear_user_state(user_id)
        return

    pet = db.get_pet(user_id)
    if not pet:
        await update.message.reply_text(
            "Сначала добавь питомца!\nНапиши /start"
        )
        clear_user_state(user_id)
        return

    text = user_data.get("text") or ""
    photo_id = user_data.get("photo_id")

    db.create_record(pet["id"], text, photo_id, tag)
    clear_user_state(user_id)

    await update.message.reply_text(
        f"✅ Заметка сохранена.\n🏷 #{tag}"
    )


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
        # Пропускаем неактивные
        if not reminder.get("is_active", 1):
            continue

        pet = db.get_pet_by_id(reminder["pet_id"])

        keyboard = [
            [
                InlineKeyboardButton("✅ Выполнено", callback_data=f"reminder_done_{reminder['id']}"),
                InlineKeyboardButton("⏭ Пропущено", callback_data=f"reminder_skip_{reminder['id']}"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        recurring_info = ""
        if reminder.get("is_recurring"):
            recurring_info = "\n🔄 Повторяющееся"

        try:
            await context.bot.send_message(
                chat_id=reminder["user_id"],
                text=f"🔔 Напоминание:\n\n{reminder['text']}\n\n({pet['name']}){recurring_info}",
                reply_markup=reply_markup
            )
            db.mark_reminder_sent(reminder["id"])
        except Exception as e:
            logger.error(f"Не удалось отправить напоминание {reminder['id']}: {e}")


async def check_recurring_reminders(context: ContextTypes.DEFAULT_TYPE):
    """Проверка повторяющихся напоминаний в конце недели (запускается раз в день)"""
    from datetime import timedelta

    # Получаем все повторяющиеся напоминания, которые были отправлены
    recurring = db.get_recurring_reminders_to_confirm()

    for reminder in recurring:
        pet = db.get_pet_by_id(reminder["pet_id"])

        keyboard = [
            [InlineKeyboardButton("✅ Да, повторить", callback_data=f"repeat_yes_{reminder['id']}")],
            [InlineKeyboardButton("❌ Нет, отменить повторение", callback_data=f"repeat_no_{reminder['id']}")],
            [InlineKeyboardButton("⏸ Приостановить", callback_data=f"repeat_pause_{reminder['id']}")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        day_name = DAYS_OF_WEEK.get(reminder.get("day_of_week"), "")
        time_str = reminder.get("time_of_day", "")

        try:
            await context.bot.send_message(
                chat_id=reminder["user_id"],
                text=f"🔄 Подтверждение напоминания\n\n"
                     f"📝 {reminder['text']}\n"
                     f"📅 {day_name} {time_str}\n"
                     f"🐾 {pet['name']}\n\n"
                     f"Повторить это напоминание на следующей неделе?",
                reply_markup=reply_markup
            )
        except Exception as e:
            logger.error(f"Не удалось отправить подтверждение {reminder['id']}: {e}")


async def handle_repeat_confirmation_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка подтверждения повторения напоминания"""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    data = query.data

    parts = data.split("_")
    action = parts[1]  # yes, no, pause
    reminder_id = int(parts[2])

    reminder = db.get_reminder_by_id(reminder_id)
    if not reminder or reminder["user_id"] != user_id:
        await query.edit_message_text("Напоминание не найдено.")
        return

    from datetime import timedelta

    if action == "yes":
        # Вычисляем следующую дату
        day_of_week = reminder.get("day_of_week")
        time_of_day = reminder.get("time_of_day", "12:00")

        pet = db.get_pet_by_id(reminder["pet_id"])
        user_tz = pet.get("timezone", "+03:00") if pet else "+03:00"

        now = datetime.now()
        days_ahead = day_of_week - now.weekday() + 7
        if days_ahead <= 0:
            days_ahead += 7

        next_date = now + timedelta(days=days_ahead)
        time_parts = time_of_day.split(":")

        # Время пользователя
        user_remind_at = datetime(
            next_date.year, next_date.month, next_date.day,
            int(time_parts[0]), int(time_parts[1])
        )

        # Конвертируем в серверное время
        server_remind_at = convert_user_time_to_server(user_remind_at, user_tz)

        db.reset_reminder_for_next_week(reminder_id, server_remind_at)

        day_name = DAYS_OF_WEEK.get(day_of_week, "")
        await query.edit_message_text(
            f"✅ Напоминание повторится!\n\n"
            f"📝 {reminder['text']}\n"
            f"📅 Следующее: {day_name} {time_of_day}"
        )

    elif action == "no":
        db.disable_reminder_recurring(reminder_id)
        await query.edit_message_text(
            f"🔄 Повторение отменено.\n\n"
            f"📝 {reminder['text']}\n\n"
            f"Напоминание больше не будет повторяться."
        )

    elif action == "pause":
        db.toggle_reminder_active(reminder_id, False)
        await query.edit_message_text(
            f"⏸ Напоминание приостановлено.\n\n"
            f"📝 {reminder['text']}\n\n"
            f"Возобновить можно через /my_reminders"
        )


async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Роутер для callback запросов"""
    query = update.callback_query
    data = query.data

    if data.startswith("pet_type_"):
        await handle_pet_type_callback(update, context)
    elif data.startswith("pet_"):
        await handle_pet_edit_callback(update, context)
    elif data.startswith("tz_"):
        await handle_timezone_callback(update, context)
    elif data.startswith("day_"):
        await handle_reminder_day_callback(update, context)
    elif data.startswith("recurring_"):
        await handle_recurring_callback(update, context)
    elif data.startswith("menu_"):
        await handle_reminders_menu_callback(update, context)
    elif data.startswith("remind_"):
        await handle_reminder_time_callback(update, context)
    elif data.startswith("reminder_"):
        await handle_reminder_action(update, context)
    elif data.startswith("manage_") or data == "new_reminder" or data == "back_to_list":
        await handle_manage_reminder_callback(update, context)
    elif data.startswith(("pause_", "resume_", "delete_", "confirm_del_", "no_recur_", "yes_recur_", "edit_text_", "edit_time_")):
        await handle_reminder_actions_callback(update, context)
    elif data.startswith("editday_"):
        await handle_edit_day_callback(update, context)
    elif data.startswith("repeat_"):
        await handle_repeat_confirmation_callback(update, context)
    elif data.startswith("take_request_"):
        await handle_take_request_callback(update, context)
    elif data.startswith("note_tag_"):
        await handle_note_tag_callback(update, context)


def main():
    """Запуск бота"""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        print("ERROR: Set TELEGRAM_BOT_TOKEN environment variable")
        print("   export TELEGRAM_BOT_TOKEN='your_token'")
        return

    # Создаём приложение
    app = Application.builder().token(token).build()

    # Регистрируем обработчики
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("profile", profile_command))
    app.add_handler(CommandHandler("reminder", reminder_command))
    app.add_handler(CommandHandler("my_reminders", my_reminders_command))
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

    # Проверяем повторяющиеся напоминания раз в день (в 10:00)
    from datetime import time as time_type
    job_queue.run_daily(check_recurring_reminders, time=time_type(hour=10, minute=0))

    print("Bot started!")
    print("Commands:")
    print("   /reminder - create reminder")
    print("   /my_reminders - manage reminders")
    print("   /history - view history")
    print("   /supervisor_on - enable supervisor mode")
    print("   /supervisor_off - disable supervisor mode")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
