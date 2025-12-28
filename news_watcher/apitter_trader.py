import requests
import json
import sqlite3
import time
from telegram_alert import send_telegram_alert

# === НАСТРОЙКИ ===
APITTER_TOKEN = "токен"
APITTER_URL = "ссылка на cpyptogate"
APITTER_VIEW_URL = "view ссылка на cpyptogate"
ALLOCATE_USDT = 10
IMPACT_THRESHOLD = 64
DRY_RUN = False
SLIPPAGE_PERCENT = 1.0  # 🆕 Проскальзывание ±1%

OPEN_TRADES = {}  # активные сделки


def ensure_db_structure():
    """Проверяем структуру базы данных"""
    conn = sqlite3.connect("news.db")
    cur = conn.cursor()

    # Основная таблица новостей
    cur.execute("""
        CREATE TABLE IF NOT EXISTS processed_news (
            id TEXT PRIMARY KEY,
            title TEXT,
            processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            deal_id INTEGER DEFAULT NULL
        )
    """)

    # 🆕 Таблица отложенных листингов
    cur.execute("""
        CREATE TABLE IF NOT EXISTS pending_listings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            coin TEXT NOT NULL,
            pair TEXT NOT NULL,
            impact_score INTEGER,
            take_profit TEXT,
            stop_loss TEXT,
            trade_duration TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_check TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            attempts INTEGER DEFAULT 0,
            status TEXT DEFAULT 'pending'
        )
    """)

    conn.commit()
    conn.close()


ensure_db_structure()


def send_trade_alert(msg: str, pair=None, take_profit=None, stop_loss=None, duration=None):
    """Отправляет сообщение о сделке"""
    try:
        dummy_article = {"title": msg, "code": "trade_update"}
        dummy_analysis = {
            "Монета": pair or "Не указано",
            "coin": pair or "Не указано",
            "тейкпрофит": take_profit or "Не указано",
            "take_profit": take_profit or "Не указано",
            "стоплосс": stop_loss or "Не указано",
            "stop_loss": stop_loss or "Не указано",
            "срочность сделки": duration or "Не указано",
            "trade_duration": duration or "Не указано",
        }
        send_telegram_alert(dummy_article, dummy_analysis)
    except Exception as e:
        print(f"⚠️ Ошибка при отправке уведомления: {e}")


def get_coin_price(pair, max_retries=3):
    spot_url = f"https://api.binance.com/api/v3/ticker/price?symbol={pair}"
    futures_url = f"https://fapi.binance.com/fapi/v1/ticker/price?symbol={pair}"

    for attempt in range(1, max_retries + 1):
        try:
            # Сначала пробуем СПОТ (приоритет)
            r = requests.get(spot_url, timeout=10)
            if r.status_code == 200 and "price" in r.json():
                price = float(r.json()["price"])
                print(f"✅ СПОТ цена {pair}: {price}")
                return price, "spot", True

            # Если спот не работает - пробуем ФЬЮЧЕРСЫ
            r = requests.get(futures_url, timeout=10)
            if r.status_code == 200 and "price" in r.json():
                price = float(r.json()["price"])
                print(f"🟧 Цена FUTURES {pair}: {price}")
                return price, "futures", True

            raise Exception(f"Invalid symbol on both spot & futures")

        except Exception as e:
            print(f"⚠️ Попытка {attempt}/{max_retries} получить цену {pair}: {e}")
            if attempt < max_retries:
                time.sleep(2)

    return None, None, False


def add_pending_listing(coin, pair, impact_score, analysis):
    """🆕 Добавляет монету в очередь отложенных покупок"""
    try:
        conn = sqlite3.connect("news.db")
        cur = conn.cursor()

        take_profit = analysis.get("тейкпрофит") or analysis.get("take_profit") or "+20%"
        stop_loss = analysis.get("стоплосс") or analysis.get("stop_loss") or "-5%"
        duration = analysis.get("срочность сделки") or analysis.get("trade_duration") or "1 день"

        cur.execute("""
            INSERT INTO pending_listings 
            (coin, pair, impact_score, take_profit, stop_loss, trade_duration)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (coin, pair, impact_score, take_profit, stop_loss, duration))

        conn.commit()
        listing_id = cur.lastrowid
        conn.close()

        print(f"📌 Монета {coin} добавлена в очередь листингов (ID: {listing_id})")
        send_trade_alert(
            f"⏳ Монета {coin} ожидает листинга. Бот начнет проверку каждые 30 минут.",
            pair=coin,
            take_profit=take_profit,
            stop_loss=stop_loss,
            duration=duration
        )
        return True

    except Exception as e:
        print(f"⚠️ Ошибка добавления в pending_listings: {e}")
        return False


def place_trade_from_analysis(pair, impact_score, analysis=None, take_profit_pct=20, stop_loss_pct=5):
    """Создаёт сделку через Apitter с учетом slippage"""
    if impact_score < IMPACT_THRESHOLD:
        print(f"ℹ️ Пропуск {pair}: влияние {impact_score} ниже порога {IMPACT_THRESHOLD}")
        return

    import re

    # Определяем монету
    coin_name = (analysis.get("Монета") or analysis.get("coin") or pair.replace("USDT", "")).upper()
    coin_name = re.sub(r'[^A-Z0-9]', '', coin_name)

    # Нормализуем пару
    pair = pair.upper()
    pair = re.sub(r'(USDT)+$', 'USDT', pair)

    # 🆕 ИСПРАВЛЕНО: Получаем цену И тип рынка
    price, market_type, success = get_coin_price(pair, max_retries=3)

    if not success or price is None:
        print(f"⚠️ Не удалось получить цену для {pair}. Добавляем в очередь листингов...")
        add_pending_listing(coin_name, pair, impact_score, analysis)
        return

    # 🆕 ПРИМЕНЯЕМ SLIPPAGE +1% для покупки
    price_with_slippage = round(price * (1 + SLIPPAGE_PERCENT / 100), 8)
    print(f"📊 Базовая цена: {price}, с проскальзыванием (+{SLIPPAGE_PERCENT}%): {price_with_slippage}")
    print(f"📍 Рынок: {market_type.upper()}")

    # Извлекаем данные из анализа
    take_profit_field = analysis.get("тейкпрофит") or analysis.get("take_profit") or f"+{take_profit_pct}%"
    stop_loss_field = analysis.get("стоплосс") or analysis.get("stop_loss") or f"-{stop_loss_pct}%"
    duration_field = analysis.get("срочность сделки") or analysis.get("trade_duration") or "1 день"

    # Парсим длительность сделки
    duration_map = {"дн": 86400, "недел": 604800, "мес": 2592000}
    timeout_sec = 604800
    match = re.search(r"(\d+)(?:[-–](\d+))?\s*(дн|недел|мес)", duration_field)
    if match:
        low, high, unit = match.groups()
        upper = int(high or low)
        for key, val in duration_map.items():
            if unit.startswith(key):
                timeout_sec = upper * val
                break

    # Парсим тейк и стоп
    try:
        tp_val = float(take_profit_field.strip("%+")) / 100
        sl_val = float(stop_loss_field.strip("%-")) / 100
    except:
        tp_val = take_profit_pct / 100
        sl_val = stop_loss_pct / 100

    # Рассчитываем TP/SL от БАЗОВОЙ цены
    take_profit = round(price * (1 + tp_val), 6)
    stop_loss = round(price * (1 - sl_val), 6)

    # Количество покупаем по цене С ПРОСКАЛЬЗЫВАНИЕМ
    qty = round(ALLOCATE_USDT / price_with_slippage, 8)

    print(f"🚀 Создание сделки для {pair}:")
    print(f"   💰 Количество: {qty}")
    print(f"   💵 Цена покупки (с slippage): {price_with_slippage}")
    print(f"   🎯 Take Profit: {take_profit}")
    print(f"   🛑 Stop Loss: {stop_loss}")
    print(f"   🕒 Таймаут: {timeout_sec / 86400:.1f} дней")

    # 🆕 КРИТИЧЕСКОЕ ИСПРАВЛЕНИЕ: Выбираем правильный рынок
    stock_type = "binance_futures" if market_type == "futures" else "binance_spot"

    print(f"   🏦 Stock type: {stock_type}")

    payload = [
        {
            "stock": stock_type,  # 🆕 ИСПРАВЛЕНО: используем правильный рынок
            "type": "limit",
            "side": "buy",
            "positionSide": "long",
            "pair": pair,
            "data": {"qty": qty, "price": price_with_slippage}
        },
        {
            "stock": stock_type,  # 🆕 ИСПРАВЛЕНО: используем правильный рынок
            "type": "oco",
            "side": "sell",
            "positionSide": "long",
            "pair": pair,
            "data": {"qty": qty, "price": take_profit, "stoploss": stop_loss}
        },
    ]

    params = {
        "token": APITTER_TOKEN,
        "sync": "",
        "action": "create",
        "stock": stock_type,  # 🆕 ИСПРАВЛЕНО: используем правильный рынок
        "mode": "json",
        "tag": json.dumps({"tag": "news_auto_trade", "deal_timeout": timeout_sec, "market": market_type})
    }

    if DRY_RUN:
        print(f"🚀 [DRY RUN] {pair}: {params}")
        return

    try:
        resp = requests.post(APITTER_URL, params=params, json=payload, timeout=30)
        resp.raise_for_status()
        result = resp.json()
        print(f"✅ Ответ Apitter ({resp.status_code}): {result}")

        deal_id = result.get("data", {}).get("deal")

        if deal_id:
            conn = sqlite3.connect("news.db")
            cur = conn.cursor()

            # Сохраняем deal_id в последнюю обработанную новость
            cur.execute("""
                UPDATE processed_news
                SET deal_id = ?
                WHERE id = (SELECT id FROM processed_news ORDER BY processed_at DESC LIMIT 1)
            """, (deal_id,))

            conn.commit()
            conn.close()
            print(f"💾 deal_id {deal_id} сохранён в базе данных")

        send_trade_alert(
            f"💰 Создана сделка {coin_name} на {market_type.upper()} (ID: {deal_id})",
            pair=coin_name,
            take_profit=take_profit_field,
            stop_loss=stop_loss_field,
            duration=duration_field
        )

    except Exception as e:
        print(f"⚠️ Ошибка при создании сделки: {e}")


def check_pending_listings():
    """
    🆕 Проверяет отложенные листинги и пытается купить монеты
    Вызывается периодически из отдельного потока
    """
    try:
        conn = sqlite3.connect("news.db")
        cur = conn.cursor()

        # Берем все pending листинги
        cur.execute("""
            SELECT id, coin, pair, impact_score, take_profit, stop_loss, trade_duration, attempts
            FROM pending_listings
            WHERE status = 'pending'
            ORDER BY created_at ASC
        """)

        listings = cur.fetchall()

        if not listings:
            return

        print(f"\n🔍 Проверка {len(listings)} отложенных листингов...")

        for row in listings:
            listing_id, coin, pair, impact_score, tp, sl, duration, attempts = row

            print(f"📌 Проверяю {pair} (попытка {attempts + 1})...")

            # 🆕 ИСПРАВЛЕНО: Получаем цену и market_type
            price, market_type, success = get_coin_price(pair, max_retries=2)

            if success and price is not None:
                print(f"✅ Монета {pair} появилась на рынке {market_type.upper()}! Цена: {price}")

                # Создаем анализ для покупки
                analysis = {
                    "Монета": coin,
                    "coin": coin,
                    "тейкпрофит": tp,
                    "take_profit": tp,
                    "стоплосс": sl,
                    "stop_loss": sl,
                    "срочность сделки": duration,
                    "trade_duration": duration,
                }

                # Покупаем
                place_trade_from_analysis(pair, impact_score, analysis)

                # Помечаем как выполненный
                cur.execute("""
                    UPDATE pending_listings
                    SET status = 'completed', last_check = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (listing_id,))

                send_trade_alert(
                    f"🎉 Листинг {coin} завершен! Сделка создана автоматически на {market_type.upper()}."
                )
            else:
                # Увеличиваем счетчик попыток
                new_attempts = attempts + 1

                # Если больше 240 попыток (5 дней * 48 проверок) — отменяем
                if new_attempts >= 240:
                    print(f"⏸️ Листинг {pair} отменен после {new_attempts} попыток")
                    cur.execute("""
                        UPDATE pending_listings
                        SET status = 'cancelled', last_check = CURRENT_TIMESTAMP
                        WHERE id = ?
                    """, (listing_id,))
                    send_trade_alert(f"⏸️ Ожидание листинга {coin} отменено (превышен лимит времени)")
                else:
                    cur.execute("""
                        UPDATE pending_listings
                        SET attempts = ?, last_check = CURRENT_TIMESTAMP
                        WHERE id = ?
                    """, (new_attempts, listing_id))

        conn.commit()
        conn.close()

    except Exception as e:
        print(f"⚠️ Ошибка при проверке pending listings: {e}")
