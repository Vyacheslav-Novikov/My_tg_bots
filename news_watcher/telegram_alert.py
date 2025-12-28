import requests
import time
from bs4 import BeautifulSoup
import re
import html
import json

# Токен бота
BOT_TOKEN = "токен"

# 💬 ID получателей
USER_CHAT_ID = 00000000
USER_CHAT_ID_E = 0000000
CHANNEL_CHAT_ID = -000000000

# Порог важности для отправки в канал
IMPACT_THRESHOLD = 64


def safe_html(value):
    if value is None:
        return "—"
    return str(value).replace("<", "&lt;").replace(">", "&gt;")


def parse_apitter_html(html_text, deal_id=None):
    soup = BeautifulSoup(html_text, "html.parser")
    text = soup.get_text(" ", strip=True)

    # ID сделки
    deal_id = str(deal_id or "?")
    date_match = re.search(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", text)
    created_at = date_match.group(1) if date_match else "Неизвестно"

    # Пара
    pair_match = re.search(r"\b([A-Z]{2,5})USDT\b", text)
    pair = pair_match.group(1) + "USDT" if pair_match else "Неизвестно"

    # Цена покупки
    price_match = re.search(r'"price":([0-9.]+)', text)
    buy_price = float(price_match.group(1)) if price_match else None

    # Тейк и стоп
    tp_match = re.search(r'"price":([0-9.]+),"stoploss":([0-9.]+)', text)
    if tp_match:
        take_profit = float(tp_match.group(1))
        stop_loss = float(tp_match.group(2))
    else:
        take_profit = stop_loss = None

    if "cancel" in text:
        status = "❌ Отменена вручную"

    elif "STOP_LOSS_LIMIT" in text and "FILLED" in text:
        status = "🛑 Закрыта по стоп-лоссу"

    elif "LIMIT_MAKER" in text and "FILLED" in text:
        status = "🎯 Закрыта по тейк-профиту"

    elif "EXPIRED" in text:
        status = "⌛ Закрыта по тайм-ауту"

    else:
        status = "✅ Активна"

    return {
        "deal_id": deal_id,
        "pair": pair,
        "created_at": created_at,
        "buy_price": buy_price,
        "take_profit": take_profit,
        "stop_loss": stop_loss,
        "status": status,
    }


def send_telegram_alert(article, analysis):
    article_url = (
            article.get("sourceUrl")
            or article.get("articleUrl")
            or f"https://www.binance.com/en/support/announcement/{article.get('code', '')}"
    )

    # Если это сообщение о сделке
    if article.get("code") == "trade_update":
        message = (
            f"📰 <b>{safe_html(article.get('title'))}</b>\n\n"
            f"💰 <b>Монета:</b> {safe_html(analysis.get('coin', 'Не указано'))}\n"
            f"🎯 <b>Тейк-профит:</b> {safe_html(analysis.get('take_profit', 'Не указано'))}\n"
            f"🛑 <b>Стоп-лосс:</b> {safe_html(analysis.get('stop_loss', 'Не указано'))}\n"
            f"⏳ <b>Срок сделки:</b> {safe_html(analysis.get('trade_duration', 'Не указано'))}\n\n"
        )
        _send_message(USER_CHAT_ID, message)
        _send_message(USER_CHAT_ID_E, message)
        return

    # Полный формат для новостей 
    message = (
        f"📰 <b>{safe_html(article.get('title'))}</b>\n\n"
        f"📊 <b>Влияние:</b> {safe_html(analysis.get('impact_score', 0))}/100\n"
        f"⏱️ <b>Срочность:</b> {safe_html(analysis.get('urgency', 'low')).capitalize()}\n\n"
        f"💬 <b>Комментарий:</b> {safe_html(analysis.get('reasoning', 'Нет описания'))}\n\n"
        f"💰 <b>Монета:</b> {safe_html(analysis.get('coin', 'Не указано'))}\n"
        f"🎯 <b>Тейк-профит:</b> {safe_html(analysis.get('take_profit', 'Не указано'))}\n"
        f"🛑 <b>Стоп-лосс:</b> {safe_html(analysis.get('stop_loss', 'Не указано'))}\n"
        f"⏳ <b>Срок сделки:</b> {safe_html(analysis.get('trade_duration', 'Не указано'))}\n\n"
        f"👉 <a href=\"{safe_html(article_url)}\">Читать статью на Binance</a>\n"
    )
    _send_message(USER_CHAT_ID, message)
    _send_message(USER_CHAT_ID_E, message)

    if analysis.get("impact_score", 0) >= IMPACT_THRESHOLD:
        _send_message(CHANNEL_CHAT_ID, message)


def _send_message(chat_id, message):
    try:
        is_channel = str(chat_id).startswith("-100")

        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": False,
        }

        reply_markup_obj = None
        if not is_channel:
            reply_markup_obj = {
                "keyboard": [
                    [
                        {"text": "🤖 Статус"},
                        {"text": "💼 Активные заявки"},
                        {"text": "📉 Завершенные заявки"}
                    ],
                    [
                        {"text": "📊 Пары"},
                        {"text": "💹 История пар"},
                    ]
                ],
                "resize_keyboard": True,
                "one_time_keyboard": False,
            }

        # Если есть reply_markup — превратим его в JSON-строку и отправим через data
        data_payload = payload.copy()
        if reply_markup_obj:
            data_payload["reply_markup"] = json.dumps(reply_markup_obj)

        # Отправляем form-data (data=)
        resp = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            data=data_payload,
            timeout=30,
        )

        if resp.status_code == 200 and resp.json().get("ok"):
            print(f"✅ Сообщение успешно отправлено в {chat_id}")
            return

        # Логируем ошибку от Telegram
        print(f"⚠️ Telegram ошибка при отправке в {chat_id}: {resp.text}")

        # Если парсинг HTML — отправляем fallback (plain text, экранированный)
        if resp.status_code == 400 and "can't parse entities" in resp.text:
            try:
                fallback = {
                    "chat_id": chat_id,
                    "text": html.escape(message),
                    "disable_web_page_preview": False,
                }
                if reply_markup_obj:
                    fallback["reply_markup"] = json.dumps(reply_markup_obj)
                fallback_resp = requests.post(
                    f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                    data=fallback,
                    timeout=30,
                )
                print("🔁 Отправлен fallback (plain text):", fallback_resp.status_code, fallback_resp.text)
            except Exception as e2:
                print("❌ Ошибка fallback отправки:", e2)

    except Exception as e:
        print(f"❌ Ошибка при отправке в {chat_id}: {e}")


# Отправляет уведомление о pairs trading
def send_pairs_alert(message, pair=None, direction=None, current_ratio=None, target_ratio=None, stop_loss_ratio=None,
                     pnl=None):
    try:
        msg = f"📊 <b>Pairs Trading</b>\n\n"
        msg += f"{safe_html(message)}\n\n"

        if pair:
            msg += f"💱 <b>Пара:</b> {safe_html(pair)}\n"
        if direction:
            direction_text = "📈 LONG B / SHORT A" if direction == "BUY_B_SELL_A" else "📉 SHORT B / LONG A"
            msg += f"🎯 <b>Направление:</b> {direction_text}\n"
        if current_ratio:
            msg += f"📊 <b>Текущее отношение:</b> {current_ratio:.6f}\n"
        if target_ratio:
            msg += f"🎯 <b>Целевое отношение:</b> {target_ratio:.6f}\n"
        if stop_loss_ratio:
            msg += f"🛑 <b>Стоп-лосс:</b> {stop_loss_ratio:.6f}\n"
        if pnl is not None:
            emoji = "🟢" if pnl > 0 else "🔴"
            msg += f"\n{emoji} <b>P&L:</b> {pnl:.2f}%\n"

        _send_message(USER_CHAT_ID, msg)
        _send_message(USER_CHAT_ID_E, msg)

    except Exception as e:
        print(f"⚠️ Ошибка отправки pairs alert: {e}")


def listen_for_commands():
    print("🟢 Telegram бот запущен. Ожидаю команды...")
    last_update_id = None

    while True:
        try:
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
            if last_update_id:
                url += f"?offset={last_update_id + 1}"

            response = requests.get(url, timeout=30)
            data = response.json()

            if "result" in data:
                for update in data["result"]:
                    last_update_id = update["update_id"]

                    if "message" in update:
                        chat_id = update["message"]["chat"]["id"]
                        text = update["message"].get("text", "").lower()

                        # 🤖 Проверка статуса бота
                        if text in ["/status", "🤖 статус", "проверить", "проверить бота"]:
                            _send_message(chat_id, "🤖 Бот активен и работает!")
                            print(f"✅ Ответил пользователю {chat_id}: бот активен")

                        # 💼 Активные заявки (ИСПРАВЛЕНО - проблема 2)
                        elif text in ["/active", "💼 активные заявки", "активные заявки"]:
                            try:
                                import sqlite3
                                conn = sqlite3.connect("news.db")
                                cur = conn.cursor()

                                cur.execute("""
                                    SELECT deal_id, title 
                                    FROM processed_news 
                                    WHERE deal_id IS NOT NULL 
                                    ORDER BY processed_at DESC
                                """)
                                deals = cur.fetchall()
                                conn.close()

                                if not deals:
                                    _send_message(chat_id, "❌ Нет активных сделок.")
                                    continue

                                msg = "📋 <b>Активные сделки:</b>\n\n"
                                active_count = 0

                                for (deal_id, title) in deals:
                                    try:
                                        resp = requests.get(
                                            f"https://test.apitter.com/cryptogate/view.php?token=555aaa&deal_id={deal_id}",
                                            timeout=20
                                        )
                                    except Exception as e:
                                        msg += f"⚠️ Ошибка при запросе сделки {deal_id}: {safe_html(str(e))}\n\n"
                                        continue

                                    if resp.status_code == 200:
                                        status_data = parse_apitter_html(resp.text, deal_id)
                                        if status_data.get("status") and "✅ Активна" in status_data["status"]:
                                            active_count += 1
                                            msg += (
                                                f"🆔 <b>Сделка:</b> {deal_id}\n"
                                                f"📰 <b>{safe_html(title)}</b>\n"
                                                f"📅 <b>Дата:</b> {safe_html(status_data.get('created_at'))}\n"
                                                f"💱 <b>Пара:</b> {safe_html(status_data.get('pair'))}\n"
                                                f"💰 <b>Цена входа:</b> {safe_html(status_data.get('buy_price'))}\n"
                                                f"🎯 <b>Тейк-профит:</b> {safe_html(status_data.get('take_profit'))}\n"
                                                f"🛑 <b>Стоп-лосс:</b> {safe_html(status_data.get('stop_loss'))}\n"
                                                f"📊 <b>Статус:</b> {safe_html(status_data.get('status'))}\n\n"
                                            )
                                    else:
                                        msg += f"⚠️ Ошибка по сделке {deal_id}: {resp.status_code}\n"

                                if active_count == 0:
                                    msg = "❌ Активных сделок не найдено."

                                _send_message(chat_id, msg)

                            except Exception as e:
                                _send_message(chat_id, f"⚠️ Ошибка при обработке кнопки:\n{e}")

                        # 📉 Завершённые заявки 
                        elif text in ["/closed", "📉 завершенные заявки", "завершенные заявки"]:
                            try:
                                import sqlite3
                                conn = sqlite3.connect("news.db")
                                cur = conn.cursor()
                                cur.execute("""
                                    SELECT deal_id, title 
                                    FROM processed_news 
                                    WHERE deal_id IS NOT NULL 
                                    ORDER BY processed_at DESC
                                """)
                                deals = cur.fetchall()
                                conn.close()

                                if not deals:
                                    _send_message(chat_id, "❌ Завершённых сделок нет.")
                                    continue

                                msg = "📉 <b>Завершённые сделки:</b>\n\n"
                                closed_count = 0

                                for (deal_id, title) in deals:
                                    if closed_count >= 10:
                                        break

                                    try:
                                        resp = requests.get(
                                            f"https://test.apitter.com/cryptogate/view.php?token=555aaa&deal_id={deal_id}",
                                            timeout=15
                                        )
                                    except Exception as e:
                                        msg += f"⚠️ Ошибка при запросе сделки {deal_id}: {safe_html(str(e))}\n\n"
                                        continue

                                    if resp.status_code == 200:
                                        status_data = parse_apitter_html(resp.text, deal_id)
                                        if status_data.get("status") and "✅ Активна" not in status_data["status"]:
                                            closed_count += 1
                                            msg += (
                                                f"🆔 <b>Сделка:</b> {deal_id}\n"
                                                f"📰 <b>{safe_html(title)}</b>\n"
                                                f"📅 <b>Дата:</b> {safe_html(status_data.get('created_at'))}\n"
                                                f"💱 <b>Пара:</b> {safe_html(status_data.get('pair'))}\n"
                                                f"💰 <b>Цена входа:</b> {safe_html(status_data.get('buy_price'))}\n"
                                                f"🎯 <b>Тейк-профит:</b> {safe_html(status_data.get('take_profit'))}\n"
                                                f"🛑 <b>Стоп-лосс:</b> {safe_html(status_data.get('stop_loss'))}\n"
                                                f"📊 <b>Статус:</b> {safe_html(status_data.get('status'))}\n\n"
                                            )
                                    else:
                                        msg += f"⚠️ Ошибка по сделке {deal_id}: {resp.status_code}\n"

                                if closed_count == 0:
                                    msg = "❌ Завершённых сделок не найдено."

                                _send_message(chat_id, msg)

                            except Exception as e:
                                _send_message(chat_id, f"⚠️ Ошибка при обработке кнопки:\n{e}")

                                # 📊 Активные пары
                        elif text in ["/pairs", "📊 пары", "активные пары"]:
                            try:
                                import sqlite3
                                conn = sqlite3.connect("news.db")
                                cur = conn.cursor()

                                cur.execute("""
                                                        SELECT id, pair, direction, entry_ratio, target_ratio, 
                                                               stop_loss_ratio, entry_date
                                                        FROM pairs_positions 
                                                        WHERE status = 'active'
                                                        ORDER BY entry_date DESC
                                                    """)
                                positions = cur.fetchall()
                                conn.close()

                                if not positions:
                                    _send_message(chat_id, "❌ Нет активных pairs позиций.")
                                    continue

                                msg = "📊 <b>Активные Pairs позиции:</b>\n\n"

                                for (pos_id, pair, direction, entry_ratio, target_ratio, stop_loss_ratio,
                                    entry_date) in positions:
                                    direction_text = "📈 LONG B/SHORT A" if direction == "BUY_B_SELL_A" else "📉 SHORT B/LONG A"
                                    msg += (
                                        f"🆔 <b>Позиция #{pos_id}</b>\n"
                                        f"💱 <b>Пара:</b> {safe_html(pair)}\n"
                                        f"🎯 <b>Направление:</b> {direction_text}\n"
                                        f"📅 <b>Дата открытия:</b> {safe_html(entry_date)}\n"
                                        f"📊 <b>Вход:</b> {entry_ratio:.6f}\n"
                                        f"🎯 <b>Цель:</b> {target_ratio:.6f}\n"
                                        f"🛑 <b>Стоп:</b> {stop_loss_ratio:.6f}\n\n"
                                    )

                                _send_message(chat_id, msg)

                            except Exception as e:
                                _send_message(chat_id, f"⚠️ Ошибка при обработке команды:\n{e}")

                            # 💹 История пар
                        elif text in ["/pairs_history", "💹 история пар"]:
                            try:
                                import sqlite3
                                conn = sqlite3.connect("news.db")
                                cur = conn.cursor()

                                cur.execute("""
                                                            SELECT id, pair, direction, entry_ratio, exit_ratio, 
                                                                   pnl_percent, entry_date, exit_date
                                                            FROM pairs_positions 
                                                            WHERE status = 'closed'
                                                            ORDER BY exit_date DESC
                                                            LIMIT 10
                                                        """)
                                positions = cur.fetchall()
                                conn.close()

                                if not positions:
                                    _send_message(chat_id, "❌ Нет закрытых pairs позиций.")
                                    continue

                                msg = "💹 <b>История Pairs (последние 10):</b>\n\n"

                                for (pos_id, pair, direction, entry_ratio, exit_ratio, pnl, entry_date,
                                     exit_date) in positions:
                                    emoji = "🟢" if pnl > 0 else "🔴"
                                    msg += (
                                        f"🆔 <b>#{pos_id}</b> {safe_html(pair)}\n"
                                        f"📊 Вход: {entry_ratio:.6f} → Выход: {exit_ratio:.6f}\n"
                                        f"{emoji} P&L: {pnl:.2f}%\n"
                                        f"📅 {safe_html(entry_date[:10])} - {safe_html(exit_date[:10])}\n\n"
                                    )

                                _send_message(chat_id, msg)

                            except Exception as e:
                                _send_message(chat_id, f"⚠️ Ошибка при обработке команды:\n{e}")

            time.sleep(2)

        except Exception as e:
            print("⚠️ Ошибка при опросе команд:", e)
            time.sleep(5)
