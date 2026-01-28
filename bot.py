"""
Telegram бот для сбора фото и создания PDF
+ Админка для отправки PDF пользователям
"""

import os
import logging
from datetime import datetime
from pathlib import Path
from typing import List

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

from pdf_creator import create_pdf_from_images

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ============ НАСТРОЙКИ ============

# Твой Telegram ID (админ) — узнай через @userinfobot
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))

# Папка для файлов
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

# Хранилище данных пользователей (в памяти, можно заменить на БД)
# {user_id: {"files": [path1, path2], "state": "normal"}}
users_data = {}


def get_user_files(user_id: int) -> List[str]:
    """Получить список файлов пользователя"""
    if user_id not in users_data:
        users_data[user_id] = {"files": [], "state": "normal"}
    return users_data[user_id]["files"]


def add_user_file(user_id: int, file_path: str):
    """Добавить файл пользователю"""
    if user_id not in users_data:
        users_data[user_id] = {"files": [], "state": "normal"}
    users_data[user_id]["files"].append(file_path)


def clear_user_files(user_id: int):
    """Очистить файлы пользователя"""
    if user_id in users_data:
        # Удаляем файлы с диска
        for f in users_data[user_id]["files"]:
            if os.path.exists(f):
                os.remove(f)
        users_data[user_id]["files"] = []


def get_user_state(user_id: int) -> str:
    if user_id not in users_data:
        users_data[user_id] = {"files": [], "state": "normal"}
    return users_data[user_id].get("state", "normal")


def set_user_state(user_id: int, state: str, **extra):
    if user_id not in users_data:
        users_data[user_id] = {"files": [], "state": "normal"}
    users_data[user_id]["state"] = state
    users_data[user_id].update(extra)


# ============ КОМАНДЫ ПОЛЬЗОВАТЕЛЯ ============

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start"""
    user_id = update.effective_user.id
    user_name = update.effective_user.first_name
    
    # Уведомляем админа о новом пользователе
    if ADMIN_ID and user_id != ADMIN_ID:
        try:
            await context.bot.send_message(
                ADMIN_ID,
                f"👤 Новый пользователь!\n\n"
                f"Имя: {user_name}\n"
                f"ID: `{user_id}`",
                parse_mode="Markdown"
            )
        except:
            pass
    
    files_count = len(get_user_files(user_id))
    
    text = (
        f"Привет, {user_name}! 👋\n\n"
        f"Я помогу собрать фото в PDF.\n\n"
        f"📸 Просто отправляй мне фото\n"
        f"📄 Когда будешь готов — нажми /pdf\n\n"
    )
    
    if files_count > 0:
        text += f"📁 У тебя уже {files_count} фото"
    
    await update.message.reply_text(text)


async def pdf_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /pdf — создать PDF из загруженных фото"""
    user_id = update.effective_user.id
    files = get_user_files(user_id)
    
    if not files:
        await update.message.reply_text(
            "❌ У тебя нет загруженных фото.\n\n"
            "Сначала отправь мне фото, потом нажми /pdf"
        )
        return
    
    keyboard = [
        [InlineKeyboardButton(f"✅ Создать PDF ({len(files)} фото)", callback_data="make_pdf")],
        [InlineKeyboardButton("🗑 Очистить всё", callback_data="clear_files")],
    ]
    
    await update.message.reply_text(
        f"📁 У тебя {len(files)} фото.\n\nЧто делаем?",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def my_files_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /files — посмотреть свои файлы"""
    user_id = update.effective_user.id
    files = get_user_files(user_id)
    
    if not files:
        await update.message.reply_text("📁 У тебя пока нет файлов.\n\nОтправь мне фото!")
        return
    
    await update.message.reply_text(
        f"📁 Твои файлы: {len(files)} шт.\n\n"
        f"/pdf — создать PDF\n"
        f"/clear — очистить всё"
    )


async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /clear — очистить свои файлы"""
    user_id = update.effective_user.id
    clear_user_files(user_id)
    await update.message.reply_text("🗑 Все файлы удалены!")


# ============ КОМАНДЫ АДМИНА ============

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /admin — панель админа"""
    user_id = update.effective_user.id
    
    if user_id != ADMIN_ID:
        await update.message.reply_text("⛔ Нет доступа")
        return
    
    # Список пользователей с файлами
    users_with_files = [(uid, data) for uid, data in users_data.items() if data["files"]]
    
    if not users_with_files:
        text = "👤 Пользователей с файлами нет"
    else:
        text = "👥 Пользователи с файлами:\n\n"
        for uid, data in users_with_files:
            text += f"• ID: `{uid}` — {len(data['files'])} файлов\n"
    
    text += (
        "\n\n📤 Чтобы отправить PDF пользователю:\n"
        "`/send ID` — затем отправь PDF файл"
    )
    
    await update.message.reply_text(text, parse_mode="Markdown")


async def send_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /send ID — отправить PDF пользователю"""
    user_id = update.effective_user.id
    
    if user_id != ADMIN_ID:
        await update.message.reply_text("⛔ Нет доступа")
        return
    
    if not context.args:
        await update.message.reply_text(
            "❌ Укажи ID пользователя:\n"
            "`/send 123456789`",
            parse_mode="Markdown"
        )
        return
    
    try:
        target_user_id = int(context.args[0])
    except:
        await update.message.reply_text("❌ Неверный ID")
        return
    
    set_user_state(user_id, "waiting_pdf_for_user", target_user_id=target_user_id)
    
    await update.message.reply_text(
        f"📤 Отправь PDF для пользователя `{target_user_id}`\n\n"
        f"Или /cancel для отмены",
        parse_mode="Markdown"
    )


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /cancel"""
    user_id = update.effective_user.id
    set_user_state(user_id, "normal")
    await update.message.reply_text("❌ Отменено")


async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /broadcast — отправить сообщение всем"""
    user_id = update.effective_user.id
    
    if user_id != ADMIN_ID:
        await update.message.reply_text("⛔ Нет доступа")
        return
    
    set_user_state(user_id, "waiting_broadcast")
    await update.message.reply_text(
        "📢 Отправь сообщение (текст, фото или PDF) для рассылки всем пользователям.\n\n"
        "/cancel — отмена"
    )


# ============ ОБРАБОТЧИКИ СООБЩЕНИЙ ============

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка фото от пользователя"""
    user_id = update.effective_user.id
    
    # Скачиваем фото
    photo = update.message.photo[-1]  # Лучшее качество
    file = await context.bot.get_file(photo.file_id)
    
    # Создаём папку пользователя
    user_dir = UPLOAD_DIR / str(user_id)
    user_dir.mkdir(exist_ok=True)
    
    # Сохраняем
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_path = user_dir / f"{timestamp}.jpg"
    await file.download_to_drive(file_path)
    
    add_user_file(user_id, str(file_path))
    files_count = len(get_user_files(user_id))
    
    await update.message.reply_text(
        f"✅ Фото сохранено! (всего: {files_count})\n\n"
        f"Отправь ещё или нажми /pdf"
    )


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка документов"""
    user_id = update.effective_user.id
    doc = update.message.document
    state = get_user_state(user_id)
    
    # Админ отправляет PDF пользователю
    if user_id == ADMIN_ID and state == "waiting_pdf_for_user":
        if doc.mime_type != "application/pdf":
            await update.message.reply_text("❌ Отправь PDF файл")
            return
        
        target_user_id = users_data[user_id].get("target_user_id")
        
        try:
            await context.bot.send_document(
                chat_id=target_user_id,
                document=doc.file_id,
                caption="📄 Документ от администратора"
            )
            await update.message.reply_text(f"✅ PDF отправлен пользователю {target_user_id}")
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка: {e}")
        
        set_user_state(user_id, "normal")
        return
    
    # Админ делает рассылку
    if user_id == ADMIN_ID and state == "waiting_broadcast":
        await do_broadcast(update, context, document=doc)
        return
    
    # Обычный пользователь отправил изображение как документ
    if doc.mime_type and doc.mime_type.startswith("image/"):
        file = await context.bot.get_file(doc.file_id)
        
        user_dir = UPLOAD_DIR / str(user_id)
        user_dir.mkdir(exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        ext = doc.file_name.split(".")[-1] if doc.file_name else "jpg"
        file_path = user_dir / f"{timestamp}.{ext}"
        await file.download_to_drive(file_path)
        
        add_user_file(user_id, str(file_path))
        files_count = len(get_user_files(user_id))
        
        await update.message.reply_text(
            f"✅ Изображение сохранено! (всего: {files_count})\n\n"
            f"Отправь ещё или нажми /pdf"
        )
    else:
        await update.message.reply_text(
            "❌ Отправляй фото или изображения.\n"
            "PDF и другие документы не поддерживаются."
        )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка текста"""
    user_id = update.effective_user.id
    state = get_user_state(user_id)
    
    # Админ делает рассылку текстом
    if user_id == ADMIN_ID and state == "waiting_broadcast":
        await do_broadcast(update, context, text=update.message.text)
        return
    
    await update.message.reply_text(
        "📸 Отправь мне фото!\n\n"
        "Когда загрузишь все — нажми /pdf"
    )


async def do_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE, text=None, document=None):
    """Рассылка всем пользователям"""
    user_id = update.effective_user.id
    sent = 0
    failed = 0
    
    for uid in users_data.keys():
        if uid == ADMIN_ID:
            continue
        try:
            if document:
                await context.bot.send_document(uid, document.file_id)
            elif text:
                await context.bot.send_message(uid, text)
            sent += 1
        except:
            failed += 1
    
    set_user_state(user_id, "normal")
    await update.message.reply_text(f"📢 Рассылка завершена!\n✅ Отправлено: {sent}\n❌ Ошибок: {failed}")


# ============ CALLBACK ОБРАБОТЧИКИ ============

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка кнопок"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    data = query.data
    
    if data == "make_pdf":
        files = get_user_files(user_id)
        
        if not files:
            await query.edit_message_text("❌ Нет файлов")
            return
        
        await query.edit_message_text("⏳ Создаю PDF...")
        
        try:
            pdf_path = create_pdf_from_images(files, user_id)
            
            with open(pdf_path, "rb") as f:
                await context.bot.send_document(
                    chat_id=user_id,
                    document=InputFile(f, filename=f"photos_{datetime.now().strftime('%Y%m%d')}.pdf"),
                    caption=f"📄 PDF из {len(files)} фото"
                )
            
            os.remove(pdf_path)
            
            # Спрашиваем, удалить ли файлы
            await context.bot.send_message(
                user_id,
                "Удалить загруженные фото?",
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("🗑 Да, удалить", callback_data="clear_files"),
                        InlineKeyboardButton("📁 Оставить", callback_data="keep_files"),
                    ]
                ])
            )
            
        except Exception as e:
            logger.error(f"Ошибка PDF: {e}")
            await context.bot.send_message(user_id, f"❌ Ошибка: {e}")
    
    elif data == "clear_files":
        clear_user_files(user_id)
        await query.edit_message_text("🗑 Все фото удалены!")
    
    elif data == "keep_files":
        await query.edit_message_text("📁 Фото сохранены. Можешь добавить ещё и снова сделать PDF.")


# ============ MAIN ============

def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        print("❌ Установи TELEGRAM_BOT_TOKEN")
        print("   export TELEGRAM_BOT_TOKEN='токен'")
        return
    
    if not ADMIN_ID:
        print("⚠️  ADMIN_ID не установлен. Админ-функции недоступны.")
        print("   export ADMIN_ID='твой_telegram_id'")
    
    app = Application.builder().token(token).build()
    
    # Команды пользователя
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("pdf", pdf_command))
    app.add_handler(CommandHandler("files", my_files_command))
    app.add_handler(CommandHandler("clear", clear_command))
    
    # Команды админа
    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(CommandHandler("send", send_command))
    app.add_handler(CommandHandler("broadcast", broadcast_command))
    app.add_handler(CommandHandler("cancel", cancel_command))
    
    # Сообщения
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    # Кнопки
    app.add_handler(CallbackQueryHandler(callback_handler))
    
    print("🚀 Бот запущен!")
    if ADMIN_ID:
        print(f"👑 Админ ID: {ADMIN_ID}")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
