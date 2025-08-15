import logging
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ConversationHandler
from bot_config import TOKEN
import bot_handlers
from states import SET_AD_ID, CHOOSE_REGION, AWAIT_QUERIES

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


def main():
    # Проверка токена
    if not TOKEN:
        logger.error("BOT_TOKEN не задан в .env файле")
        raise Exception("BOT_TOKEN не задан в .env файле")

    # Создаем приложение
    application = Application.builder().token(TOKEN).build()

    # Настройка ConversationHandler
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", bot_handlers.start),
            CommandHandler("set_ad_id", bot_handlers.set_ad_id),
            CommandHandler("check", bot_handlers.check),
            CommandHandler("change_region", bot_handlers.change_region)
        ],
        states={
            SET_AD_ID: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, bot_handlers.receive_ad_id)
            ],
            CHOOSE_REGION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, bot_handlers.handle_region_choice)
            ],
            AWAIT_QUERIES: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, bot_handlers.receive_queries)
            ]
        },
        fallbacks=[CommandHandler("cancel", bot_handlers.cancel)],
        allow_reentry=True
    )

    application.add_handler(conv_handler)
    application.add_error_handler(bot_handlers.error_handler)

    logger.info("🤖 Бот запущен")
    application.run_polling()


if __name__ == "__main__":
    main()