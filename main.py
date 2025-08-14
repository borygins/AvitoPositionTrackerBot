# Импортируем необходимые модули
import os  # Для работы с операционной системой (переменные окружения, пути)
from dotenv import load_dotenv  # Для загрузки переменных окружения из .env файла
import requests  # Для выполнения HTTP-запросов к сайту Avito
from bs4 import BeautifulSoup  # Для парсинга HTML-страниц
from fake_useragent import UserAgent  # Для генерации случайных User-Agent
import time  # Для работы со временем (задержки)
from datetime import datetime  # Для работы с датой и временем
from telegram import Update  # Основной класс для работы с Telegram API
from telegram.ext import (  # Компоненты для создания бота
    Application,  # Главный класс приложения бота
    CommandHandler,  # Обработчик команд (начинающихся с /)
    MessageHandler,  # Обработчик обычных сообщений
    ContextTypes,  # Типы контекста для обработчиков
    filters  # Фильтры для обработки сообщений
)
import logging  # Для логирования (записи событий)

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',  # Формат сообщений
    level=logging.INFO  # Уровень логирования (INFO и выше)
)
# Создаем логгер для текущего модуля
logger = logging.getLogger(__name__)

# Загружаем переменные окружения из файла .env
load_dotenv()
# Записываем в лог факт загрузки переменных
logger.info("Загружены переменные окружения из .env файла")

# Конфигурация бота
# Получаем токен бота из переменных окружения
TOKEN = os.getenv("BOT_TOKEN")
# Проверяем, что токен установлен
if not TOKEN:
    # Если токена нет - пишем ошибку в лог
    logger.error("BOT_TOKEN не задан в .env файле")
    # И прекращаем выполнение с исключением
    raise Exception("BOT_TOKEN не задан в .env файле")

# Список регионов для поиска на Avito
REGIONS = [
    "sankt-peterburg_i_lo",  # Код региона СПб и ЛО
    "sankt-peterburg"  # Код региона только СПб
]
# Задержка между запросами к Avito (в секундах)
REQUEST_DELAY = 20
# Максимальное количество запросов за одну проверку
MAX_QUERIES = 10

# Глобальный словарь для хранения данных пользователей
# Структура: {user_id: {'ad_id': '123', 'awaiting_queries': True, 'queries': [...]}}
user_data = {}


def get_random_headers():
    """Генерирует случайные HTTP-заголовки для обхода блокировок"""
    # Создаем объект для генерации User-Agent
    ua = UserAgent()
    # Возвращаем словарь с заголовками
    return {
        'User-Agent': ua.random,  # Случайный User-Agent
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'DNT': '1',  # Do Not Track
        'Upgrade-Insecure-Requests': '1'
    }


def fetch_avito_page(query, region):
    """
    Получает HTML-страницу Avito для указанного запроса и региона
    Возвращает HTML-код страницы или None при ошибке
    """
    try:
        # Формируем URL для запроса:
        # - Кодируем поисковый запрос для URL
        # - Подставляем регион и запрос
        url = f"https://www.avito.ru/{region}?q={requests.utils.quote(query)}"

        # Выполняем GET-запрос к Avito:
        # - Используем сгенерированные заголовки
        # - Устанавливаем таймаут 25 секунд
        response = requests.get(
            url,
            headers=get_random_headers(),
            timeout=25
        )
        # Проверяем статус ответа (вызовет исключение при ошибке HTTP)
        response.raise_for_status()

        # Проверяем, не вернула ли Avito страницу с капчей
        if "captcha" in response.text.lower():
            raise Exception("Обнаружена капча")

        # Возвращаем HTML-код страницы
        return response.text
    except Exception as e:
        # Логируем ошибку с указанием региона
        logger.error(f"Ошибка запроса ({region}): {e}")
        return None


def parse_ads(html):
    """
    Анализирует HTML-код и извлекает данные объявлений
    Возвращает список словарей с данными объявлений
    """
    try:
        # Создаем объект BeautifulSoup для парсинга HTML
        soup = BeautifulSoup(html, 'html.parser')
        # Список для результатов
        ads = []

        # Ищем все элементы объявлений по CSS-селектору
        for item in soup.select('div[data-marker="item"]'):
            # Извлекаем ID объявления из атрибута data-item-id
            ad_id = item.get('data-item-id', '')
            # Ищем элемент с названием объявления
            title_elem = item.select_one('[itemprop="name"]')
            # Извлекаем текст названия, если элемент найден
            title = title_elem.text.strip() if title_elem else 'Без названия'
            # Добавляем объявление в список
            ads.append({'id': ad_id, 'title': title})

        return ads
    except Exception as e:
        # Логируем ошибку парсинга
        logger.error(f"Ошибка парсинга: {e}")
        return []


def find_ad_position(ads, target_id):
    """Ищет позицию объявления с заданным ID в списке объявлений"""
    # Перебираем объявления с индексом (начиная с 1)
    for position, ad in enumerate(ads, start=1):
        # Если ID текущего объявления совпадает с целевым
        if ad['id'] == target_id:
            # Возвращаем позицию (номер в списке)
            return position
    # Если объявление не найдено - возвращаем строку
    return "Не найдено"


def get_region_name(region_code):
    """Преобразует код региона в читаемое название"""
    # Словарь соответствия кодов и названий регионов
    names = {
        "sankt-peterburg_i_lo": "СПб и ЛО",
        "sankt-peterburg": "СПб"
    }
    # Возвращаем название или оригинальный код, если название не найдено
    return names.get(region_code, region_code)


# Асинхронная функция обработки команды /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start - приветствие и инструкция"""
    # Получаем объект пользователя, отправившего команду
    user = update.effective_user
    # Формируем текст приветствия
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
    # Отправляем ответ пользователю с HTML-форматированием
    await update.message.reply_text(help_text, parse_mode="HTML")


# Обработчик команды /set_ad_id
async def set_ad_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Устанавливает ID отслеживаемого объявления"""
    # Получаем ID пользователя в Telegram
    user_id = update.effective_user.id
    # Получаем аргументы команды (текст после /set_ad_id)
    args = context.args

    # Если аргументы не переданы
    if not args:
        # Просим пользователя указать ID объявления
        await update.message.reply_text("❌ Укажите ID объявления после команды\nПример: /set_ad_id 2140172843")
        return

    # Берем первый аргумент как ID объявления
    ad_id = args[0]
    # Сохраняем в глобальный словарь user_data
    user_data[user_id] = {'ad_id': ad_id}
    # Подтверждаем сохранение
    await update.message.reply_text(f"✅ ID объявления установлен: {ad_id}\nОтправь /check для запуска проверки")


# Обработчик команды /check
async def check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Запускает процесс проверки позиций объявления"""
    # Получаем ID пользователя
    user_id = update.effective_user.id

    # Проверяем, установлен ли ID объявления для этого пользователя
    if user_id not in user_data or 'ad_id' not in user_data[user_id]:
        # Если не установлен - просим сначала установить
        await update.message.reply_text("❌ Сначала установите ID объявления командой /set_ad_id")
        return

    # Запрашиваем у пользователя ключевые запросы
    await update.message.reply_text(
        "📝 Введите ключевые запросы для поиска (каждый с новой строки):\n"
        "• Максимум 10 запросов\n"
        "• Каждый запрос будет проверен в двух регионах\n\n"
        "Пример:\n"
        "<code>макияж и прическа\n"
        "визажист с выездом</code>",
        parse_mode="HTML"  # Разрешаем HTML-форматирование
    )

    # Устанавливаем флаг, что ожидаем запросы от пользователя
    user_data[user_id]['awaiting_queries'] = True


# Обработчик текстовых сообщений
async def handle_queries(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает введенные пользователем поисковые запросы"""
    # Получаем ID и объект пользователя
    user_id = update.effective_user.id
    user = update.effective_user

    # Проверяем, ожидаем ли мы запросы от этого пользователя
    if user_id not in user_data or not user_data[user_id].get('awaiting_queries'):
        # Если не ожидаем - игнорируем сообщение
        return

    # Получаем текст сообщения и убираем пробелы по краям
    text = update.message.text.strip()
    # Разбиваем текст на строки и очищаем каждую строку
    queries = [q.strip() for q in text.split('\n') if q.strip()]

    # Если запросов больше максимума
    if len(queries) > MAX_QUERIES:
        # Берем только первые MAX_QUERIES запросов
        queries = queries[:MAX_QUERIES]
        # Сообщаем пользователю об ограничении
        await update.message.reply_text(f"⚠️ Принято первых {MAX_QUERIES} запросов")

    # Если нет ни одного валидного запроса
    if not queries:
        # Просим ввести запросы снова
        await update.message.reply_text("❌ Не получено ни одного запроса. Попробуйте снова.")
        return

    # Сохраняем запросы для пользователя
    user_data[user_id]['queries'] = queries
    # Сбрасываем флаг ожидания
    user_data[user_id]['awaiting_queries'] = False

    # Сообщаем о начале проверки
    await update.message.reply_text(
        f"🔍 Начинаю проверку {len(queries)} запросов в 2 регионах для {user.first_name}...\n"
        f"⏱ Ориентировочное время: {len(queries) * 2 * 25 // 60} минут"
    )
    # Запускаем процесс проверки
    await process_queries(update, user_id)


# Основная функция обработки запросов
async def process_queries(update: Update, user_id):
    """Выполняет проверку позиций по всем запросам и регионам"""
    try:
        # Получаем ID отслеживаемого объявления
        target_id = user_data[user_id]['ad_id']
        # Получаем список запросов
        queries = user_data[user_id]['queries']
        # Список для сбора результатов
        results = []
        # Общее количество проверок (запросы × регионы)
        total_checks = len(queries) * len(REGIONS)
        # Счетчик текущей проверки
        current_check = 0

        # Перебираем все запросы
        for query in queries:
            # Список результатов для текущего запроса
            query_results = []

            # Перебираем все регионы для текущего запроса
            for region in REGIONS:
                # Увеличиваем счетчик проверок
                current_check += 1
                # Получаем читаемое название региона
                region_name = get_region_name(region)

                # Формируем статус текущей проверки
                status = (
                    f"🔎 Проверка {current_check}/{total_checks}\n"
                    f"• Запрос: {query}\n"
                    f"• Регион: {region_name}"
                )
                # Отправляем статус пользователю
                await update.message.reply_text(status)

                # Получаем HTML-страницу Avito
                html = fetch_avito_page(query, region)

                # Если страница не получена (ошибка)
                if not html:
                    # Добавляем сообщение об ошибке
                    query_results.append(f"❌ {region_name}: ошибка загрузки")
                    # Переходим к следующей итерации
                    continue

                # Парсим объявления из HTML
                ads = parse_ads(html)

                # Ищем позицию нашего объявления
                position = find_ad_position(ads, target_id)
                # Получаем текущее время
                check_time = datetime.now().strftime('%H:%M:%S')

                # Форматируем результат для региона
                result = f"• {region_name}: позиция {position} ({check_time})"
                query_results.append(result)

                # Пауза между запросами (кроме последнего)
                time.sleep(REQUEST_DELAY)

            # Формируем результат для текущего запроса
            results.append(
                f"🔹 *{query}*\n" +  # Жирное название запроса
                "\n".join(query_results)  # Список результатов по регионам
            )

        # Объединяем все результаты в один отчет
        report = "\n\n".join(results)
        # Формируем финальный отчет
        final_report = (
            f"📊 *Отчет по позициям*\n\n"
            f"{report}\n\n"
            f"🆔 *ID объявления:* `{target_id}`\n"
            f"⏱ *Общее время проверки:* {datetime.now().strftime('%H:%M:%S')}"
        )
        # Отправляем финальный отчет пользователю
        await update.message.reply_text(
            final_report,
            parse_mode="Markdown",  # Используем Markdown-форматирование
            disable_web_page_preview=True  # Отключаем превью ссылок
        )

    # Обработка исключений
    except Exception as e:
        # Логируем ошибку с трассировкой стека
        logger.error(f"Ошибка обработки запросов: {e}", exc_info=True)
        # Сообщаем пользователю об ошибке
        await update.message.reply_text(f"⚠️ Произошла ошибка: {str(e)}")


# Глобальный обработчик ошибок
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Перехватывает и обрабатывает все непойманные исключения"""
    # Логируем ошибку
    logger.error(f"Ошибка: {context.error}", exc_info=True)
    # Если ошибка связана с сообщением
    if isinstance(update, Update) and update.effective_message:
        # Отправляем пользователю сообщение об ошибке
        await update.effective_message.reply_text("⚠️ Произошла непредвиденная ошибка. Попробуйте позже.")


# Основная функция запуска бота
def main():
    """Создает и запускает Telegram бота"""
    # Создаем приложение бота с указанным токеном
    application = Application.builder().token(TOKEN).build()

    # Регистрируем обработчики команд:
    # - /start -> функция start()
    application.add_handler(CommandHandler("start", start))
    # - /set_ad_id -> функция set_ad_id()
    application.add_handler(CommandHandler("set_ad_id", set_ad_id))
    # - /check -> функция check()
    application.add_handler(CommandHandler("check", check))

    # Регистрируем обработчик текстовых сообщений:
    # - Обычный текст, не команда -> функция handle_queries()
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,  # Фильтр: текст, но не команда
        handle_queries
    ))

    # Регистрируем глобальный обработчик ошибок
    application.add_error_handler(error_handler)

    # Логируем запуск бота
    logger.info("🤖 Бот запущен. Режим двух регионов: СПб и СПб+ЛО")
    # Запускаем бота в режиме опроса (polling)
    application.run_polling()


# Точка входа в программу
if __name__ == "__main__":
    # При запуске файла напрямую вызываем main()
    main()