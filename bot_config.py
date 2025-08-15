import os
from dotenv import load_dotenv
from telegram import ReplyKeyboardMarkup

# Загрузка переменных окружения
load_dotenv()

# Токен бота
TOKEN = os.getenv("BOT_TOKEN")

# Настройки парсера
REQUEST_DELAY = 20  # Задержка между запросами (сек)
MAX_QUERIES = 10    # Максимальное количество запросов за одну проверку

# Регионы для отслеживания (коды Avito и читаемые названия)
REGIONS = {
    "Санкт-Петербург": "sankt-peterburg",
    "Санкт-Петербург и ЛО": "sankt_peterburg_i_lo",
    "Оба региона": "both"
}

# Кнопки для выбора региона
REGION_BUTTONS = [
    ["Санкт-Петербург", "Санкт-Петербург и ЛО"],
    ["Оба региона"]
]

# Клавиатура для выбора региона
def get_region_keyboard():
    return ReplyKeyboardMarkup(
        REGION_BUTTONS,
        one_time_keyboard=True,
        resize_keyboard=True,
        input_field_placeholder="Выберите регион"
    )

# Для удобства импорта
__all__ = [
    'TOKEN',
    'REQUEST_DELAY',
    'MAX_QUERIES',
    'REGIONS',
    'get_region_keyboard'
]