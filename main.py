import requests
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
import time
from datetime import datetime
from telegram import Bot, Update
from telegram.ext import CommandHandler, Updater, MessageHandler, Filters
import logging

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Конфигурация
TOKEN = "ВАШ_TELEGRAM_BOT_TOKEN"  # Замените на свой токен
REGIONS = [
    "sankt-peterburg_i_lo",  # СПб и ЛО
    "sankt-peterburg"  # Только СПб
]
REQUEST_DELAY = 20  # Задержка между запросами
MAX_QUERIES = 10  # Максимум запросов за раз

# Глобальное хранилище данных пользователя
user_data = {}


def get_random_headers():
    """Генерирует случайные заголовки для обхода блокировок"""
    ua = UserAgent()
    return {
        'User-Agent': ua.random,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'DNT': '1',
        'Upgrade-Insecure-Requests': '1'
    }


def fetch_avito_page(query, region):
    """
    Получает HTML-страницу для указанного запроса и региона
    Возвращает HTML или None при ошибке
    """
    try:
        # Формируем URL с учетом региона и запроса
        url = f"https://www.avito.ru/{region}?q={requests.utils.quote(query)}"

        # Выполняем запрос со случайными заголовками
        response = requests.get(
            url,
            headers=get_random_headers(),
            timeout=25  # Увеличенный таймаут
        )
        response.raise_for_status()

        # Проверка на капчу
        if "captcha" in response.text.lower():
            raise Exception("Обнаружена капча")

        return response.text
    except Exception as e:
        logger.error(f"Ошибка запроса ({region}): {e}")
        return None


def parse_ads(html):
    """
    Извлекает данные объявлений из HTML
    Возвращает список словарей: [{'id': '123', 'title': '...'}, ...]
    """
    try:
        soup = BeautifulSoup(html, 'html.parser')
        ads = []

        # Ищем все блоки объявлений
        for item in soup.select('div[data-marker="item"]'):
            ad_id = item.get('data-item-id', '')
            title_elem = item.select_one('[itemprop="name"]')
            title = title_elem.text.strip() if title_elem else 'Без названия'
            ads.append({'id': ad_id, 'title': title})

        return ads
    except Exception as e:
        logger.error(f"Ошибка парсинга: {e}")
        return []


def find_ad_position(ads, target_id):
    """Ищет позицию объявления в списке"""
    for position, ad in enumerate(ads, start=1):
        if ad['id'] == target_id:
            return position
    return "Не найдено"


def get_region_name(region_code):
    """Возвращает читаемое название региона по коду"""
    names = {
        "sankt-peterburg_i_lo": "СПб и ЛО",
        "sankt-peterburg": "СПб"
    }
    return names.get(region_code, region_code)


def start(update: Update, context):
    """Обработчик команды /start"""
    user = update.effective_user
    help_text = (
        f"Привет, {user.first_name}! Я AvitoPositionProbe 🤖\n\n"
        "Я отслеживаю позиции объявлений на Авито в двух регионах:\n"
        "- Санкт-Петербург и ЛО\n"
        "- Только Санкт-Петербург\n\n"
        "📌 Как использовать:\n"
        "1. Установи ID объявления: /set_ad_id [ID]\n"
        "2. Запусти проверку: /check\n"
        "3. Введи ключевые запросы (каждый с новой строки)\n\n"
        "Пример:\n"
        "<code>макияж и прическа\n"
        "визажист с выездом</code>"
    )
    update.message.reply_text(help_text, parse_mode="HTML")


def set_ad_id(update: Update, context):
    """Устанавливает ID объявления для пользователя"""
    user_id = update.effective_user.id
    args = context.args

    if not args:
        update.message.reply_text("❌ Укажите ID объявления после команды\nПример: /set_ad_id 2140172843")
        return

    ad_id = args[0]
    user_data[user_id] = {'ad_id': ad_id}
    update.message.reply_text(f"✅ ID объявления установлен: {ad_id}\nОтправь /check для запуска проверки")


def check(update: Update, context):
    """Начинает процесс проверки позиций"""
    user_id = update.effective_user.id

    # Проверка установки ID объявления
    if user_id not in user_data or 'ad_id' not in user_data[user_id]:
        update.message.reply_text("❌ Сначала установите ID объявления командой /set_ad_id")
        return

    update.message.reply_text(
        "📝 Введите ключевые запросы для поиска (каждый с новой строки):\n"
        "• Максимум 10 запросов\n"
        "• Каждый запрос будет проверен в двух регионах\n\n"
        "Пример:\n"
        "<code>макияж и прическа\n"
        "визажист с выездом</code>",
        parse_mode="HTML"
    )

    # Устанавливаем флаг ожидания запросов
    user_data[user_id]['awaiting_queries'] = True


def handle_queries(update: Update, context):
    """Обрабатывает введенные пользователем запросы"""
    user_id = update.effective_user.id
    user = update.effective_user

    # Проверяем, ожидает ли бот запросы
    if user_id not in user_data or not user_data[user_id].get('awaiting_queries'):
        return

    text = update.message.text.strip()
    queries = [q.strip() for q in text.split('\n') if q.strip()]

    # Ограничиваем количество запросов
    if len(queries) > MAX_QUERIES:
        queries = queries[:MAX_QUERIES]
        update.message.reply_text(f"⚠️ Принято первых {MAX_QUERIES} запросов")

    if not queries:
        update.message.reply_text("❌ Не получено ни одного запроса. Попробуйте снова.")
        return

    # Сохраняем запросы и сбрасываем флаг
    user_data[user_id]['queries'] = queries
    user_data[user_id]['awaiting_queries'] = False

    # Начинаем проверку
    update.message.reply_text(
        f"🔍 Начинаю проверку {len(queries)} запросов в 2 регионах для {user.first_name}...\n"
        f"⏱ Ориентировочное время: {len(queries) * 2 * 25 // 60} минут"
    )
    process_queries(update, user_id)


def process_queries(update: Update, user_id):
    """Обрабатывает все запросы пользователя с задержками"""
    try:
        target_id = user_data[user_id]['ad_id']
        queries = user_data[user_id]['queries']
        results = []
        total_checks = len(queries) * len(REGIONS)
        current_check = 0

        for query in queries:
            query_results = []

            for region in REGIONS:
                current_check += 1
                region_name = get_region_name(region)

                # Статус проверки
                status = (
                    f"🔎 Проверка {current_check}/{total_checks}\n"
                    f"• Запрос: {query}\n"
                    f"• Регион: {region_name}"
                )
                update.message.reply_text(status)

                # Получаем страницу
                html = fetch_avito_page(query, region)

                if not html:
                    query_results.append(f"❌ {region_name}: ошибка загрузки")
                    continue

                # Парсим объявления
                ads = parse_ads(html)

                # Ищем позицию
                position = find_ad_position(ads, target_id)
                check_time = datetime.now().strftime('%H:%M:%S')

                # Форматируем результат
                result = f"• {region_name}: позиция {position} ({check_time})"
                query_results.append(result)

                # Задержка перед следующим запросом
                time.sleep(REQUEST_DELAY)

            # Формируем результат для запроса
            results.append(
                f"🔹 *{query}*\n" +
                "\n".join(query_results)
            )

        # Формируем финальный отчет
        report = "\n\n".join(results)
        final_report = (
            f"📊 *Отчет по позициям*\n\n"
            f"{report}\n\n"
            f"🆔 *ID объявления:* `{target_id}`\n"
            f"⏱ *Общее время проверки:* {datetime.now().strftime('%H:%M:%S')}"
        )
        update.message.reply_text(
            final_report,
            parse_mode="Markdown",
            disable_web_page_preview=True
        )

    except Exception as e:
        logger.error(f"Ошибка обработки запросов: {e}", exc_info=True)
        update.message.reply_text(f"⚠️ Произошла ошибка: {str(e)}")


def error_handler(update: Update, context):
    """Обработчик ошибок"""
    logger.error(f"Ошибка: {context.error}", exc_info=True)
    if update.effective_message:
        update.effective_message.reply_text("⚠️ Произошла непредвиденная ошибка. Попробуйте позже.")


def main():
    """Запуск бота"""
    bot = Bot(token=TOKEN)
    updater = Updater(bot=bot, use_context=True)
    dp = updater.dispatcher

    # Регистрация обработчиков
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("set_ad_id", set_ad_id, pass_args=True))
    dp.add_handler(CommandHandler("check", check))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_queries))
    dp.add_error_handler(error_handler)

    # Запуск
    logger.info("🤖 Бот запущен. Режим двух регионов: СПб и СПб+ЛО")
    updater.start_polling()
    updater.idle()


if __name__ == "__main__":
    main()