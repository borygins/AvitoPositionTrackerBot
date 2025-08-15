import requests
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
import logging
import bot_config

# Настройка логгера
logger = logging.getLogger(__name__)


def get_random_headers():
    """Генерирует случайные HTTP-заголовки"""
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


def check_ad_exists(ad_id):
    """Проверяет существование объявления по ID"""
    url = f"https://www.avito.ru/sankt-peterburg?cd=1&q={ad_id}"
    try:
        response = requests.get(
            url,
            headers=get_random_headers(),
            timeout=15
        )
        soup = BeautifulSoup(response.text, 'html.parser')

        # Проверяем наличие элементов объявления
        title_exists = bool(soup.find('div', {'data-marker': 'item-view/title'}))
        not_found = bool(soup.find('div', {'data-marker': 'error/resale'}))

        return title_exists and not not_found
    except Exception as e:
        logger.error(f"Ошибка проверки объявления: {e}")
        return False


def parse_ads(html):
    """Извлекает данные объявлений из HTML"""
    try:
        soup = BeautifulSoup(html, 'html.parser')
        ads = []

        # Метод 1: Поиск по data-item-id
        for item in soup.select('div[data-marker="item"]'):
            if ad_id := item.get('data-item-id', ''):
                ads.append({'id': ad_id})
                continue

            # Метод 2: Поиск по id с префиксом "i"
            if elem_id := item.get('id', ''):
                if elem_id.startswith('i') and elem_id[1:].isdigit():
                    ads.append({'id': elem_id[1:]})
                    continue

            # Метод 3: Извлечение из ссылки
            if link := item.select_one('a[href*="/items/"]'):
                href = link.get('href', '')
                if '/items/' in href:
                    ad_id = href.split('/items/')[-1].split('?')[0].split('/')[0]
                    if ad_id.isdigit():
                        ads.append({'id': ad_id})

        return ads
    except Exception as e:
        logger.error(f"Ошибка парсинга: {e}")
        return []


def find_ad_position(ads, target_id):
    """Ищет позицию объявления в списке"""
    logger.debug(f"Поиск {target_id} среди {len(ads)} объявлений")
    for position, ad in enumerate(ads, start=1):
        if ad['id'] == target_id:
            return position
    return "Не найдено"


def get_region_name(region_code):
    """Преобразует код региона в читаемое название"""
    names = {
        "sankt-peterburg": "Санкт-Петербург",
        "sankt_peterburg_i_lo": "Санкт-Петербург и ЛО"
    }
    return names.get(region_code, region_code)


def fetch_avito_page(query, region):
    """Получает HTML-страницу Avito"""
    # Правильные коды регионов
    region_mapping = {
        "sankt_peterburg_i_lo": "sankt_peterburg_i_lo",
        "sankt-peterburg": "sankt-peterburg"
    }
    region_code = region_mapping.get(region, region)

    # Кодируем запрос
    encoded_query = requests.utils.quote(query.encode('utf-8'))

    # Формируем URL
    url = f"https://www.avito.ru/{region_code}?cd=1&q={encoded_query}"

    try:
        response = requests.get(url, headers=get_random_headers(), timeout=25)
        response.raise_for_status()

        if "captcha" in response.text.lower():
            raise Exception("Обнаружена капча")

        return response.text
    except Exception as e:
        logger.error(f"Ошибка запроса ({region_code}): {e}")
        return None


# Для удобства импорта
__all__ = [
    'check_ad_exists',
    'parse_ads',
    'find_ad_position',
    'get_region_name',
    'fetch_avito_page'
]