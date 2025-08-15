import logging
from datetime import datetime
import asyncio
from telegram import Update, ReplyKeyboardRemove
from telegram.ext import ContextTypes, ConversationHandler
import states
from avito_parser import check_ad_exists, parse_ads, find_ad_position, get_region_name, fetch_avito_page
from bot_config import REGIONS, get_region_keyboard, MAX_QUERIES, REQUEST_DELAY

logger = logging.getLogger(__name__)

# Состояния
SET_AD_ID = states.SET_AD_ID
CHOOSE_REGION = states.CHOOSE_REGION
AWAIT_QUERIES = states.AWAIT_QUERIES


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    user = update.effective_user
    help_text = (
        f"Привет, {user.first_name}! Я AvitoPositionProbe 🤖\n\n"
        "Я отслеживаю позиции объявлений на Авито в выбранных регионах\n\n"
        "📌 Как использовать:\n"
        "1. Установи ID объявления: /set_ad_id\n"
        "2. Выбери регион для отслеживания\n"
        "3. Запусти проверку: /check\n"
        "4. Введи ключевые запросы (каждый с новой строки)\n\n"
        "ℹ️ Ты всегда можешь изменить регион командой /change_region"
    )
    await update.message.reply_text(help_text, parse_mode="HTML")
    return ConversationHandler.END


async def set_ad_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало установки ID объявления"""
    await update.message.reply_text(
        "🔢 Введите ID объявления:\n"
        "• Чтобы отменить операцию, введите /cancel\n\n"
        "Как найти ID:\n"
        "1. Откройте ваше объявление на Avito\n"
        "2. Посмотрите цифры в конце URL после последнего слеша\n"
        "Пример: https://www.avito.ru/.../2140172843 → ID = 2140172843"
    )
    return SET_AD_ID


async def receive_ad_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка введённого ID объявления"""
    text = update.message.text.strip()

    if text.isdigit() and len(text) >= 5:
        if check_ad_exists(text):
            context.user_data['ad_id'] = text
            await update.message.reply_text(f"✅ ID объявления установлен: {text}")
            return await choose_location(update, context)
        else:
            await update.message.reply_text("❌ Объявление не найдено! Введите другой ID или /cancel")
            return SET_AD_ID
    else:
        await update.message.reply_text("❌ Неверный формат ID! Введите только цифры (минимум 5) или /cancel")
        return SET_AD_ID


async def choose_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Предлагает выбор региона через кнопки"""
    await update.message.reply_text(
        "📍 Выберите регион для отслеживания позиций:",
        reply_markup=get_region_keyboard()
    )
    return CHOOSE_REGION


async def handle_region_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает выбор региона"""
    choice = update.message.text

    if choice in REGIONS:
        region_code = REGIONS[choice]

        # Сохраняем выбранные регионы
        if region_code == "both":
            context.user_data['regions'] = [
                "sankt-peterburg",
                "sankt_peterburg_i_lo"
            ]
        else:
            context.user_data['regions'] = [region_code]

        await update.message.reply_text(
            f"✅ Регион установлен: {choice}\n"
            f"Теперь можете запустить проверку командой /check",
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END
    else:
        await update.message.reply_text(
            "❌ Пожалуйста, выберите регион из предложенных вариантов",
            reply_markup=ReplyKeyboardRemove()
        )
        return await choose_location(update, context)


async def change_region(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Позволяет изменить выбранный регион"""
    if 'ad_id' not in context.user_data:
        await update.message.reply_text("❌ Сначала установите ID объявления командой /set_ad_id")
        return ConversationHandler.END

    return await choose_location(update, context)


async def check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Запускает процесс проверки позиций"""
    # Проверяем наличие ID объявления
    if 'ad_id' not in context.user_data:
        await update.message.reply_text("❌ Сначала установите ID объявления командой /set_ad_id")
        return ConversationHandler.END

    # Проверяем наличие выбранного региона
    if 'regions' not in context.user_data:
        await update.message.reply_text("❌ Сначала выберите регион командой /set_ad_id")
        return ConversationHandler.END

    await update.message.reply_text(
        "📝 Введите ключевые запросы для поиска (каждый с новой строки):\n"
        f"• Максимум {MAX_QUERIES} запросов\n"
        "• Чтобы отменить операцию, введите /cancel\n\n"
        "Пример:\n"
        "<code>макияж и прическа\nвизажист с выездом</code>",
        parse_mode="HTML"
    )
    return AWAIT_QUERIES


async def receive_queries(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает введённые поисковые запросы"""
    text = update.message.text.strip()
    queries = [q.strip() for q in text.split('\n') if q.strip()]

    if not queries:
        await update.message.reply_text("❌ Не получено ни одного запроса. Попробуйте снова или /cancel")
        return AWAIT_QUERIES

    # Сохраняем запросы
    context.user_data['queries'] = queries[:MAX_QUERIES]

    # Запускаем проверку
    await process_queries(update, context)
    return ConversationHandler.END


async def process_queries(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выполняет проверку позиций"""
    try:
        # Получаем данные из контекста
        target_id = context.user_data['ad_id']
        regions = context.user_data['regions']
        queries = context.user_data['queries']

        results = []
        total_checks = len(queries) * len(regions)
        current_check = 0

        for query in queries:
            query_results = []

            for region in regions:
                current_check += 1
                region_name = get_region_name(region)

                # Отправляем статус
                status_msg = await update.message.reply_text(
                    f"🔎 Проверка {current_check}/{total_checks}\n"
                    f"• Запрос: {query}\n"
                    f"• Регион: {region_name}\n"
                    f"⏱ Ожидайте..."
                )

                # Получаем страницу
                html = fetch_avito_page(query, region)

                if not html:
                    query_results.append(f"❌ {region_name}: ошибка загрузки")
                    continue

                # Парсим и ищем позицию
                ads = parse_ads(html)
                position = find_ad_position(ads, target_id)
                check_time = datetime.now().strftime('%H:%M:%S')

                # Формируем результат
                result = f"• {region_name}: позиция {position} ({check_time})"
                query_results.append(result)

                # Удаляем статусное сообщение
                await context.bot.delete_message(
                    chat_id=update.effective_chat.id,
                    message_id=status_msg.message_id
                )

                # Задержка между запросами
                await asyncio.sleep(REQUEST_DELAY)

            results.append(f"🔹 *{query}*\n" + "\n".join(query_results))

        # Формируем и отправляем отчёт
        report = "\n\n".join(results)
        final_report = (
            f"📊 *Отчет по позициям*\n\n{report}\n\n"
            f"🆔 *ID объявления:* `{target_id}`"
        )
        await update.message.reply_text(final_report, parse_mode="Markdown")

    except Exception as e:
        logger.error(f"Ошибка обработки запросов: {e}", exc_info=True)
        await update.message.reply_text("⚠️ Произошла ошибка при обработке запроса")


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отменяет текущую операцию"""
    await update.message.reply_text(
        "❌ Операция отменена",
        reply_markup=ReplyKeyboardRemove()
    )
    return ConversationHandler.END


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает ошибки"""
    logger.error(f"Ошибка: {context.error}", exc_info=True)
    if isinstance(update, Update) and update.effective_message:
        await update.effective_message.reply_text("⚠️ Произошла непредвиденная ошибка. Попробуйте позже.")
    return ConversationHandler.END


# Для удобства импорта
__all__ = [
    'start',
    'set_ad_id',
    'receive_ad_id',
    'choose_location',
    'handle_region_choice',
    'change_region',
    'check',
    'receive_queries',
    'process_queries',
    'cancel',
    'error_handler'
]