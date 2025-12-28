ALLOCATE_USDT_PER_PAIR = 5  # Сколько USDT выделить на КАЖДУЮ сторону пары
CHECK_INTERVAL = 3600

# ТОРГОВЫЕ ПАРЫ
TRADING_PAIRS = [
    "BTC/ETH",
    "BTC/BNB",
    "ETH/SOL",
    "BNB/MATIC",
    "BNB/ADA"
]

# СТАТИСТИЧЕСКИЕ ПАРАМЕТРЫ
LOOKBACK_PERIOD = 30  # Период расчета среднего и стандартного отклонения (дней)
ENTRY_THRESHOLD_SIGMA = 2.0  # Порог входа: Mean ± 2σ
EXIT_THRESHOLD_SIGMA = 0.0  # Выход при возврате к среднему
STOP_LOSS_THRESHOLD_SIGMA = 3.0  # Стоп-лосс на 3σ

APITTER_TOKEN = "токен"
APITTER_URL = "ссылка на cpyptogate"
APITTER_VIEW_URL = "view ссылка на cpyptogate"

DRY_RUN_PAIRS = False  

# BINANCE API
BINANCE_API_BASE = "https://api.binance.com"
BINANCE_KLINES_ENDPOINT = "/api/v3/klines"  # Для получения исторических данных
BINANCE_PRICE_ENDPOINT = "/api/v3/ticker/price"  # Для текущих цен

# НАСТРОЙКИ УВЕДОМЛЕНИЙ
NOTIFY_ON_SIGNAL_DETECTED = True  # Уведомление при обнаружении сигнала
NOTIFY_ON_POSITION_OPENED = True  # Уведомление при открытии позиции
NOTIFY_ON_POSITION_CLOSED = True  # Уведомление при закрытии позиции
NOTIFY_ANALYSIS_RESULTS = True  # Отправлять результаты анализа всех пар

# МИНИМАЛЬНЫЕ ТРЕБОВАНИЯ
MIN_DAYS_OF_DATA = 30  # Минимум дней истории для расчета
MIN_TRADE_AMOUNT = 5  # Минимальная сумма сделки в USDT

# ТАЙМАУТЫ И RETRY
HTTP_TIMEOUT = 30  # Таймаут HTTP запросов
MAX_RETRIES = 3  # Максимум попыток при ошибках API
RETRY_DELAY = 2  # Задержка между попытками (секунды)
