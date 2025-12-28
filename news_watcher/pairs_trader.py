import requests
import sqlite3
import time
import json
import numpy as np
from datetime import datetime, timedelta
from pairs_config import *
from telegram_alert import send_pairs_alert
from telegram_alert import _send_message


# ИНИЦИАЛИЗАЦИЯ БД
def init_pairs_db():
    conn = sqlite3.connect("news.db")
    cur = conn.cursor()

    # Таблица активных позиций
    cur.execute("""
        CREATE TABLE IF NOT EXISTS pairs_positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pair TEXT NOT NULL,
            asset_a TEXT NOT NULL,
            asset_b TEXT NOT NULL,
            direction TEXT NOT NULL,
            entry_ratio REAL NOT NULL,
            entry_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            target_ratio REAL NOT NULL,
            stop_loss_ratio REAL NOT NULL,
            deal_id_a INTEGER,
            deal_id_b INTEGER,
            status TEXT DEFAULT 'active',
            exit_ratio REAL,
            exit_date TIMESTAMP,
            pnl_percent REAL
        )
    """)

    # Таблица истории сигналов
    cur.execute("""
        CREATE TABLE IF NOT EXISTS pairs_signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pair TEXT NOT NULL,
            check_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            current_ratio REAL,
            mean_ratio REAL,
            std_dev REAL,
            upper_band REAL,
            lower_band REAL,
            signal_type TEXT,
            was_opened INTEGER DEFAULT 0
        )
    """)

    conn.commit()
    conn.close()
    print("✅ База данных pairs trading инициализирована")


# ПОЛУЧЕНИЕ ИСТОРИЧЕСКИХ ДАННЫХ
def get_historical_prices(symbol, days=30):
    try:
        end_time = int(time.time() * 1000)
        start_time = end_time - (days * 24 * 60 * 60 * 1000)

        url = f"{BINANCE_API_BASE}{BINANCE_KLINES_ENDPOINT}"
        params = {
            "symbol": symbol,
            "interval": "1d",  # Дневные свечи
            "startTime": start_time,
            "endTime": end_time,
            "limit": days + 5  # Запас на случай неполных дней
        }

        response = requests.get(url, params=params, timeout=HTTP_TIMEOUT)
        response.raise_for_status()

        klines = response.json()
        # Извлекаем цены закрытия (индекс 4 в каждой свече)
        closes = [float(k[4]) for k in klines]

        if len(closes) < MIN_DAYS_OF_DATA:
            print(f"⚠️ Недостаточно данных для {symbol}: {len(closes)} дней")
            return None

        return closes[-days:]  # Возвращаем ровно нужное количество дней

    except Exception as e:
        print(f"⚠️ Ошибка получения истории для {symbol}: {e}")
        return None


def get_current_price(symbol):
    """Получает текущую цену актива"""
    try:
        url = f"{BINANCE_API_BASE}{BINANCE_PRICE_ENDPOINT}"
        params = {"symbol": symbol}

        response = requests.get(url, params=params, timeout=HTTP_TIMEOUT)
        response.raise_for_status()

        price = float(response.json()["price"])
        return price

    except Exception as e:
        print(f"⚠️ Ошибка получения цены {symbol}: {e}")
        return None


# СТАТИСТИЧЕСКИЙ АНАЛИЗ
def calculate_statistics(prices_a, prices_b):
    try:
        # Рассчитываем отношение B/A для каждого дня
        ratios = np.array(prices_b) / np.array(prices_a)

        # Статистика
        mean = np.mean(ratios)
        std_dev = np.std(ratios)

        # Торговые полосы
        upper_band = mean + (ENTRY_THRESHOLD_SIGMA * std_dev)
        lower_band = mean - (ENTRY_THRESHOLD_SIGMA * std_dev)

        # Стоп-лоссы
        stop_loss_upper = mean + (STOP_LOSS_THRESHOLD_SIGMA * std_dev)
        stop_loss_lower = mean - (STOP_LOSS_THRESHOLD_SIGMA * std_dev)

        return {
            "ratios": ratios.tolist(),
            "mean": float(mean),
            "std_dev": float(std_dev),
            "upper_band": float(upper_band),
            "lower_band": float(lower_band),
            "stop_loss_upper": float(stop_loss_upper),
            "stop_loss_lower": float(stop_loss_lower),
            "current_ratio": float(ratios[-1])
        }

    except Exception as e:
        print(f"⚠️ Ошибка расчета статистики: {e}")
        return None


def detect_signal(stats):
    current_ratio = stats["current_ratio"]
    upper_band = stats["upper_band"]
    lower_band = stats["lower_band"]

    if current_ratio >= upper_band:
        return "SELL_B_BUY_A"  # B переоценен относительно A
    elif current_ratio <= lower_band:
        return "BUY_B_SELL_A"  # B недооценен относительно A
    else:
        return "HOLD"


# УПРАВЛЕНИЕ ПОЗИЦИЯМИ 
def is_position_open(pair):
    """Проверяет, есть ли активная позиция по паре"""
    try:
        conn = sqlite3.connect("news.db")
        cur = conn.cursor()

        cur.execute("""
            SELECT id FROM pairs_positions 
            WHERE pair = ? AND status = 'active'
        """, (pair,))

        result = cur.fetchone()
        conn.close()

        return result is not None

    except Exception as e:
        print(f"⚠️ Ошибка проверки позиции: {e}")
        return False


def open_pairs_position(pair, asset_a, asset_b, direction, stats):
    """
    Открывает хедж-позицию через Apitter

    Args:
        pair: Название пары (например, "BTC/ETH")
        asset_a: Актив A (например, "BTC")
        asset_b: Актив B (например, "ETH")
        direction: "SELL_B_BUY_A" или "BUY_B_SELL_A"
        stats: Статистика с торговыми уровнями
    """
    try:
        # Получаем текущие цены
        price_a = get_current_price(f"{asset_a}USDT")
        price_b = get_current_price(f"{asset_b}USDT")

        if not price_a or not price_b:
            print(f"⚠️ Не удалось получить цены для {pair}")
            return False

        # Применяем slippage 1%
        slippage = 1.01
        price_a_with_slippage = price_a * slippage
        price_b_with_slippage = price_b * slippage

        # Рассчитываем количество
        qty_a = round(ALLOCATE_USDT_PER_PAIR / price_a_with_slippage, 8)
        qty_b = round(ALLOCATE_USDT_PER_PAIR / price_b_with_slippage, 8)

        print(f"🔄 Открываю позицию {pair}:")
        print(f"   Направление: {direction}")
        print(f"   {asset_a}: {qty_a} по {price_a_with_slippage}")
        print(f"   {asset_b}: {qty_b} по {price_b_with_slippage}")

        if DRY_RUN_PAIRS:
            print("🚀 [DRY RUN] Позиция не открыта (тестовый режим)")
            return False

        # Определяем направления сделок
        if direction == "SELL_B_BUY_A":
            side_a = "buy"
            side_b = "sell"
            target_ratio = stats["mean"]
            stop_loss_ratio = stats["stop_loss_upper"]
        else:  # BUY_B_SELL_A
            side_a = "sell"
            side_b = "buy"
            target_ratio = stats["mean"]
            stop_loss_ratio = stats["stop_loss_lower"]

        # Создаем ордера через Apitter (2 отдельные сделки)
        deal_id_a = create_apitter_order(asset_a, side_a, qty_a, price_a_with_slippage)
        deal_id_b = create_apitter_order(asset_b, side_b, qty_b, price_b_with_slippage)

        if not deal_id_a or not deal_id_b:
            print(f"⚠️ Не удалось создать ордера для {pair}")
            return False

        # Сохраняем позицию в БД
        conn = sqlite3.connect("news.db")
        cur = conn.cursor()

        cur.execute("""
            INSERT INTO pairs_positions 
            (pair, asset_a, asset_b, direction, entry_ratio, target_ratio, 
             stop_loss_ratio, deal_id_a, deal_id_b, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'active')
        """, (
            pair, asset_a, asset_b, direction,
            stats["current_ratio"], target_ratio, stop_loss_ratio,
            deal_id_a, deal_id_b
        ))

        conn.commit()
        position_id = cur.lastrowid
        conn.close()

        # Отправляем уведомление
        from telegram_alert import send_pairs_alert
        send_pairs_alert(
            f"✅ Открыта позиция #{position_id}: {pair}",
            pair, direction, stats["current_ratio"], target_ratio, stop_loss_ratio
        )

        print(f"✅ Позиция {pair} открыта (ID: {position_id})")
        return True

    except Exception as e:
        print(f"⚠️ Ошибка открытия позиции {pair}: {e}")
        return False


def create_apitter_order(asset, side, qty, price):
    """Создает один ордер через Apitter API"""
    try:
        pair = f"{asset}USDT"

        payload = [{
            "stock": "binance_spot",
            "type": "limit",
            "side": side,
            "positionSide": "long",
            "pair": pair,
            "data": {"qty": qty, "price": price}
        }]

        params = {
            "token": APITTER_TOKEN,
            "sync": "",
            "action": "create",
            "stock": "binance_spot",
            "mode": "json",
            "tag": json.dumps({"tag": "pairs_trade", "asset": asset})
        }

        resp = requests.post(APITTER_URL, params=params, json=payload, timeout=HTTP_TIMEOUT)
        resp.raise_for_status()

        result = resp.json()
        deal_id = result.get("data", {}).get("deal")

        return deal_id

    except Exception as e:
        print(f"⚠️ Ошибка создания ордера {asset}: {e}")
        return None


def check_exit_conditions():
    """Проверяет условия выхода для всех активных позиций"""
    try:
        conn = sqlite3.connect("news.db")
        cur = conn.cursor()

        cur.execute("""
            SELECT id, pair, asset_a, asset_b, direction, entry_ratio, 
                   target_ratio, stop_loss_ratio, deal_id_a, deal_id_b
            FROM pairs_positions 
            WHERE status = 'active'
        """)

        positions = cur.fetchall()

        for pos in positions:
            pos_id, pair, asset_a, asset_b, direction, entry_ratio, target_ratio, stop_loss_ratio, deal_a, deal_b = pos

            # Получаем текущее отношение
            price_a = get_current_price(f"{asset_a}USDT")
            price_b = get_current_price(f"{asset_b}USDT")

            if not price_a or not price_b:
                continue

            current_ratio = price_b / price_a

            # Проверяем условия выхода
            should_exit = False
            exit_reason = ""

            if direction == "SELL_B_BUY_A":
                # Выход при достижении цели (отношение упало к mean)
                if current_ratio <= target_ratio:
                    should_exit = True
                    exit_reason = "🎯 Тейк-профит"
                # Стоп-лосс (отношение выросло еще больше)
                elif current_ratio >= stop_loss_ratio:
                    should_exit = True
                    exit_reason = "🛑 Стоп-лосс"
            else:  # BUY_B_SELL_A
                # Выход при достижении цели (отношение выросло к mean)
                if current_ratio >= target_ratio:
                    should_exit = True
                    exit_reason = "🎯 Тейк-профит"
                # Стоп-лосс (отношение упало еще больше)
                elif current_ratio <= stop_loss_ratio:
                    should_exit = True
                    exit_reason = "🛑 Стоп-лосс"

            if should_exit:
                # Рассчитываем P&L
                pnl_percent = ((current_ratio - entry_ratio) / entry_ratio) * 100
                if direction == "SELL_B_BUY_A":
                    pnl_percent = -pnl_percent  # Инвертируем для short позиции

                # Закрываем позицию в БД
                cur.execute("""
                    UPDATE pairs_positions 
                    SET status = 'closed', exit_ratio = ?, exit_date = CURRENT_TIMESTAMP, pnl_percent = ?
                    WHERE id = ?
                """, (current_ratio, pnl_percent, pos_id))

                conn.commit()

                # Уведомление

                send_pairs_alert(
                    f"{exit_reason} Позиция #{pos_id}: {pair} закрыта",
                    pair, direction, current_ratio, target_ratio, stop_loss_ratio, pnl_percent
                )

                print(f"✅ Позиция {pair} закрыта: {exit_reason}, P&L: {pnl_percent:.2f}%")

        conn.close()

    except Exception as e:
        print(f"⚠️ Ошибка проверки выходов: {e}")


# ОСНОВНОЙ ЦИКЛ 
def check_all_pairs():
    """Проверяет все пары на торговые сигналы"""
    print(f"\n{'=' * 60}")
    print(f"🔍 Проверка pairs trading: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'=' * 60}")

    conn = sqlite3.connect("news.db")
    cur = conn.cursor()

    for pair_str in TRADING_PAIRS:
        try:
            asset_a, asset_b = pair_str.split("/")
            print(f"\n📊 Анализ пары {pair_str}...")

            # Проверяем, есть ли активная позиция
            if is_position_open(pair_str):
                print(f"   ⏩ Позиция уже открыта, пропускаем")
                continue

            # Получаем исторические данные
            prices_a = get_historical_prices(f"{asset_a}USDT", LOOKBACK_PERIOD)
            prices_b = get_historical_prices(f"{asset_b}USDT", LOOKBACK_PERIOD)

            if not prices_a or not prices_b:
                print(f"   ⚠️ Недостаточно данных")
                continue

            stats = calculate_statistics(prices_a, prices_b)

            if not stats:
                print(f"   ⚠️ Ошибка расчета статистики")
                continue

            signal = detect_signal(stats)

            # Сохраняем результат в БД
            cur.execute("""
                INSERT INTO pairs_signals 
                (pair, current_ratio, mean_ratio, std_dev, upper_band, lower_band, signal_type)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                pair_str, stats["current_ratio"], stats["mean"], stats["std_dev"],
                stats["upper_band"], stats["lower_band"], signal
            ))

            # Выводим результаты
            print(f"   📈 Текущее отношение: {stats['current_ratio']:.6f}")
            print(f"   📊 Среднее: {stats['mean']:.6f}")
            print(f"   📉 Ст. откл: {stats['std_dev']:.6f}")
            print(f"   🔺 Верхняя полоса: {stats['upper_band']:.6f}")
            print(f"   🔻 Нижняя полоса: {stats['lower_band']:.6f}")
            print(f"   🎯 Сигнал: {signal}")
            USER_CHAT_ID = 541412708
            USER_CHAT_ID_E = 827140170
            messagee = (
                f"\n📊 Анализ пары {pair_str}...\n"
                f"📈 Текущее отношение: {stats['current_ratio']:.6f}\n"
                f"   📊 Среднее: {stats['mean']:.6f}\n"
                f"   📉 Ст. откл: {stats['std_dev']:.6f}\n"
                f"   🔺 Верхняя полоса: {stats['upper_band']:.6f}\n"
                f"   🔻 Нижняя полоса: {stats['lower_band']:.6f}\n"
                f"   🎯 Сигнал: {signal}")
            _send_message(USER_CHAT_ID, messagee)
            _send_message(USER_CHAT_ID_E, messagee)


            # Если есть сигнал - открываем позицию
            if signal != "HOLD":
                print(f"   🚀 Обнаружен сигнал! Открываем позицию...")
                success = open_pairs_position(pair_str, asset_a, asset_b, signal, stats)

                if success:
                    cur.execute("""
                        UPDATE pairs_signals 
                        SET was_opened = 1 
                        WHERE id = (SELECT MAX(id) FROM pairs_signals WHERE pair = ?)
                    """, (pair_str,))
            else:
                print(f"   ⏸️ Позиция в пределах нормы")

        except Exception as e:
            print(f"⚠️ Ошибка обработки пары {pair_str}: {e}")

    conn.commit()
    conn.close()

    # Проверяем условия выхода
    check_exit_conditions()

    print(f"\n{'=' * 60}")
    print(f"✅ Проверка завершена")
    print(f"{'=' * 60}\n")


def pairs_trading_loop():
    """Основной цикл pairs trading - запускается в отдельном потоке"""
    print("🚀 Pairs Trading запущен!")

    # Инициализируем БД
    init_pairs_db()

    # Даем боту время загрузиться
    time.sleep(60)

    while True:
        try:
            check_all_pairs()
        except Exception as e:
            print(f"⚠️ Ошибка в цикле pairs trading: {e}")

        # Ждем следующей проверки
        print(f"⏳ Следующая проверка через {CHECK_INTERVAL // 60} минут...")
        time.sleep(CHECK_INTERVAL)
