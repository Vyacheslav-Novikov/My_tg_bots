import threading
import time
import sqlite3
import signal
import sys

from fetch_news import fetch_binance_news
from analyze_news import analyze_news_by_title
from telegram_alert import send_telegram_alert, listen_for_commands
from apitter_trader import place_trade_from_analysis, check_pending_listings
from pairs_trader import pairs_trading_loop


# 🧩 Корректное завершение
def graceful_exit(signum, frame):
    print("\n🛑 Завершение работы бота...")
    sys.exit(0)


signal.signal(signal.SIGTERM, graceful_exit)


# 🔧 Инициализация БД
def init_db():
    conn = sqlite3.connect('news.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS processed_news (
            id TEXT PRIMARY KEY,
            title TEXT,
            processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            deal_id INTEGER DEFAULT NULL
        )
    ''')
    conn.commit()
    conn.close()


# 🔍 Проверка, обработана ли новость
def is_news_processed(news_id):
    conn = sqlite3.connect('news.db')
    c = conn.cursor()
    c.execute("SELECT id FROM processed_news WHERE id = ?", (news_id,))
    result = c.fetchone()
    conn.close()
    return result is not None


# 🧩 Пометить новость как обработанную
def mark_news_as_processed(news_id, title):
    conn = sqlite3.connect('news.db')
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO processed_news (id, title) VALUES (?, ?)", (news_id, title))
    conn.commit()
    conn.close()


# 🚀 Основной цикл проверки новостей
def news_loop():
    print("📡 Бот запущен. Проверяю новости каждые 5 минут...")
    init_db()

    while True:
        try:
            print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} — Проверка новостей...")
            articles = fetch_binance_news()
            print(f"🔹 Получено новостей: {len(articles)}")

            for article in articles:
                article_id = str(article['code'])
                title = article['title']

                print(f"🔸 Проверяем статью: {title}")

                if not is_news_processed(article_id):
                    analysis = analyze_news_by_title(title)
                    print(f"🧠 Анализ: {analysis}")

                    if analysis["reasoning"] != "Ошибка":
                        if analysis["impact_score"] > -1:
                            send_telegram_alert(article, analysis)
                            if analysis.get("impact_score", 0) >= 64:
                                print(f"🚀 Влияние {analysis['impact_score']} — создаю сделку...")
                                # Передаем тикер (монету) из анализа, если есть
                                coin = analysis.get("Монета") or analysis.get("coin") or "BTC"
                                pair = f"{coin.upper()}USDT"
                                print("📦 analysis перед отправкой:", analysis)
                                place_trade_from_analysis(
                                    pair,
                                    impact_score=analysis["impact_score"],
                                    analysis=analysis
                                )

                        else:
                            print(f"ℹ️ Пропускаю: {analysis['impact_score']} / 100")

                        # 🟢 Записываем только успешные обработки
                        mark_news_as_processed(article_id, title)
                    else:
                        print(f"⚠️ Анализ не удался, не добавляю в БД: {title}")

                else:
                    print(f"⏩ Уже обработана: {title}")

        except Exception as e:
            print(f"⚠️ Ошибка при обработке новостей: {e}")

        time.sleep(300)  # каждые 5 минут


# 🆕 Поток для проверки отложенных листингов
def listings_check_loop():
    """Проверяет pending listings каждые 30 минут"""
    print("⏳ Поток проверки листингов запущен (интервал: 30 минут)")

    # Даем боту время загрузиться
    time.sleep(60)

    while True:
        try:
            check_pending_listings()
        except Exception as e:
            print(f"⚠️ Ошибка в потоке листингов: {e}")

        time.sleep(1800)  # 30 минут


# 🔊 Точка входа
if __name__ == "__main__":
    print("🚀 Бот запущен!")

    # Поток новостей
    news_thread = threading.Thread(target=news_loop, daemon=True)
    # Поток команд Telegram
    command_thread = threading.Thread(target=listen_for_commands, daemon=True)
    # 🆕 Поток проверки листингов
    listings_thread = threading.Thread(target=listings_check_loop, daemon=True)
    # 🆕 Поток pairs trading
    pairs_thread = threading.Thread(target=pairs_trading_loop, daemon=True)

    news_thread.start()
    command_thread.start()
    listings_thread.start()
    pairs_thread.start()

    news_thread.join()
    command_thread.join()
    listings_thread.join()
    pairs_thread.join()
