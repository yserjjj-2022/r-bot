import asyncio
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from app.modules.telegram.telegram_handler import start, handle_message, handle_callback
from app.modules.telegram.admin_handler import admin_panel, admin_callback, admin_stats, admin_broadcast, admin_users
from app.modules.database.database import engine, Base
from app.modules.database import crud
from app.modules.scheduler.scheduler import start_scheduler
from decouple import config

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Инициализация базы данных
Base.metadata.create_all(bind=engine)

# Загрузка конфигурации
TELEGRAM_TOKEN = config("TELEGRAM_TOKEN")
# [FIX] SERVER_URL теперь опционален (default=None) для локального запуска
SERVER_URL = config("SERVER_URL", default=None)
ADMIN_ID = config("ADMIN_ID", default=None)

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Логирует ошибки."""
    logger.error(msg="Exception while handling an update:", exc_info=context.error)

def main():
    """Запуск бота."""
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # Регистрация хендлеров
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("admin", admin_panel))
    application.add_handler(CommandHandler("stats", admin_stats))
    application.add_handler(CommandHandler("broadcast", admin_broadcast))
    application.add_handler(CommandHandler("users", admin_users))
    
    application.add_handler(CallbackQueryHandler(admin_callback, pattern="^admin_"))
    application.add_handler(CallbackQueryHandler(handle_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    application.add_error_handler(error_handler)

    # Запуск планировщика задач
    start_scheduler(application)

    if SERVER_URL:
        PORT = config("PORT", default=8000, cast=int)
        logger.info(f"Starting webhook on port {PORT}, url: {SERVER_URL}")
        application.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path=TELEGRAM_TOKEN,
            webhook_url=f"{SERVER_URL}/{TELEGRAM_TOKEN}"
        )
    else:
        logger.info("Starting polling...")
        application.run_polling()

if __name__ == '__main__':
    main()
