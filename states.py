"""
Модуль для определения состояний бота
"""

from enum import Enum

# Состояния бота
class States(Enum):
    SET_AD_ID = 0
    CHOOSE_REGION = 1
    AWAIT_QUERIES = 2

# Для удобства использования в ConversationHandler
(
    SET_AD_ID,
    CHOOSE_REGION,
    AWAIT_QUERIES
) = range(3)

# Для импорта
__all__ = [
    'SET_AD_ID',
    'CHOOSE_REGION',
    'AWAIT_QUERIES'
]