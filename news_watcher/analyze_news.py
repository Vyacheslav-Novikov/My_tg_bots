# analyze_news.py

import json
import time
import datetime
import requests
import uuid
from datetime import datetime as dt, timedelta

# НАСТРОЙКИ GIGACHAT
GIGACHAT_AUTH_KEY = "token"  # ВАШ Authorization Key (Basic ...)
GIGACHAT_TOKEN_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
GIGACHAT_API_URL = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"
GIGACHAT_MODEL = "GigaChat"  # или "GigaChat-Plus"
GIGACHAT_SCOPE = "GIGACHAT_API_PERS"

# Параметры работы
RETRIES = 3
TIMEOUT = 30  # секунд для HTTP-запроса
BACKOFF_BASE = 1.5  # фактор экспоненциального backoff
BAD_LOG_FILE = "bad_responses.log"  # куда записываем "битые" ответы для анализа

# Кэш токена GigaChat
_gigachat_token_cache = {
    "access_token": None,
    "expires_at": None
}


def _get_gigachat_token():
    """
    Получение или обновление токена GigaChat.
    Токен живет 30 минут, кэшируем его в памяти.
    """
    global _gigachat_token_cache

    # Проверяем, не истек ли токен (с запасом 5 минут)
    if (_gigachat_token_cache["access_token"] and
            _gigachat_token_cache["expires_at"] and
            dt.now() < _gigachat_token_cache["expires_at"] - timedelta(minutes=5)):
        return _gigachat_token_cache["access_token"]

    try:
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Accept': 'application/json',
            'Authorization': f'Basic {GIGACHAT_AUTH_KEY}',
            'RqUID': str(uuid.uuid4()),
        }

        data = {'scope': GIGACHAT_SCOPE}

        response = requests.post(
            GIGACHAT_TOKEN_URL,
            headers=headers,
            data=data,
            verify=False,
            timeout=10
        )

        if response.status_code == 200:
            result = response.json()
            access_token = result.get('access_token')
            expires_in = result.get('expires_in', 1800)

            # Сохраняем в кэш
            _gigachat_token_cache["access_token"] = access_token
            _gigachat_token_cache["expires_at"] = dt.now() + timedelta(seconds=expires_in)

            print(f"🔑 GigaChat токен получен (действует {expires_in // 60} мин)")
            return access_token
        else:
            print(f"❌ Ошибка получения токена GigaChat: {response.status_code}")
            return None

    except Exception as e:
        print(f"❌ Ошибка при получении токена GigaChat: {e}")
        return None


def _call_gigachat_api(payload, retries=RETRIES):
    """
    Вызов API GigaChat с обработкой ошибок и повторными попытками.
    """
    access_token = _get_gigachat_token()
    if not access_token:
        return None

    for attempt in range(1, retries + 1):
        try:
            headers = {
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'Authorization': f'Bearer {access_token}',
            }

            response = requests.post(
                GIGACHAT_API_URL,
                headers=headers,
                json=payload,
                verify=False,
                timeout=TIMEOUT
            )

            if response.status_code == 200:
                return response
            elif response.status_code == 401:
                # Токен истек, получаем новый
                print(f"🔄 Токен GigaChat истек (401), обновляю...")
                _gigachat_token_cache["access_token"] = None  # Сбрасываем кэш
                access_token = _get_gigachat_token()
                if not access_token and attempt < retries:
                    time.sleep(BACKOFF_BASE ** attempt)
                    continue
                return None
            else:
                print(f"⚠️ GigaChat API ошибка {response.status_code} (попытка {attempt}/{retries})")
                if attempt < retries:
                    time.sleep(BACKOFF_BASE ** attempt)
                    continue
                return None

        except requests.exceptions.RequestException as e:
            print(f"⚠️ Ошибка сети GigaChat (попытка {attempt}/{retries}): {e}")
            if attempt < retries:
                time.sleep(BACKOFF_BASE ** attempt)
                continue
            return None

    return None


def _balanced_json_substring(s: str):
    """
    Попытка найти первый корректно сбалансированный JSON-объект { ... } в строке.
    Возвращает подстроку или None.
    Это лучше, чем простое find/ rfind, т.к. учитывает вложенность.
    """
    if not s:
        return None
    start = s.find("{")
    if start == -1:
        return None
    stack = []
    for i in range(start, len(s)):
        ch = s[i]
        if ch == "{":
            stack.append(i)
        elif ch == "}":
            if stack:
                stack.pop()
                if not stack:
                    return s[start:i + 1]
            else:
                # встретили закрывающую без открывающей — продолжаем искать
                continue
    return None


def _extract_text_from_api_response(response):
    """
    Универсальный извлекатель текста из ответа GigaChat/OpenAI/OpenRouter-подобного формата.
    Если тело уже JSON с choices -> возвращаем content; иначе возвращаем response.text.
    """
    if response is None:
        return ""

    try:
        data = response.json()
    except Exception:
        # не JSON — вернём сырые данные (в виде строки)
        return response.text or ""

    # Формат GigaChat: {"choices": [{"message": {"content": "..."}}]}
    if isinstance(data, dict):
        # GigaChat/OpenAI style
        if "choices" in data and isinstance(data["choices"], list) and data["choices"]:
            # попробуем несколько вариантов местоположения текста
            choice = data["choices"][0]
            if isinstance(choice, dict):
                # GigaChat style: choice["message"]["content"]
                msg = choice.get("message") or choice.get("delta") or {}
                if isinstance(msg, dict) and "content" in msg:
                    return msg["content"] or ""
                # older style: choice["text"]
                if "text" in choice:
                    return choice["text"] or ""
            # fallback: dump whole JSON
            return json.dumps(data, ensure_ascii=False)
    # если структура не похожа — вернём строковое представление
    return json.dumps(data, ensure_ascii=False)


def _log_bad_response(title: str, raw_text: str, status_code: int, note: str = ""):
    """
    Логируем в файл дату, заголовок, статус и первые 2000 символов ответа.
    Это тихая запись — ничего не печатаем в консоль.
    """
    try:
        now = datetime.datetime.utcnow().isoformat() + "Z"
        with open(BAD_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"\n---\n{now}\nTitle: {title}\nStatus: {status_code}\nNote: {note}\n")
            f.write(raw_text[:2000] + "\n")
    except Exception:
        # не ломаем основную логику в случае проблем с логом
        pass


def analyze_news_by_title(title: str, retries: int = RETRIES):
    """
    Анализирует новость Binance и возвращает dict с ключами:
    impact_score, urgency, reasoning, coin, take_profit, stop_loss, trade_duration
    """
    system_msg = (
        "You are a professional crypto market analyst. Given a Binance news headline, "
        "analyze the event and produce ONLY a single JSON object — no explanations or text outside of it. "
        "Determine what trading action you recommend: which coin to buy, under what conditions to sell, "
        "and how long to hold the position if neither take profit nor stop loss is reached. "
        "All reasoning and explanations must be written in Russian. "
        "The JSON must include exactly the following keys:\n"
        "{\n"
        "  \"impact_score\": <int 0-100>,                  // numeric evaluation of market impact\n"
        "  \"urgency\": \"low|medium|high\",               // how urgent this event is\n"
        "  \"reasoning\": \"short explanation in Russian\", // why this event matters\n"
        "  \"coin\": \"which coin to buy (e.g. BTC, ETH, BNB)\",\n"
        "  \"take_profit\": \"target price or condition, e.g. +12% or 2.50 USDT\",\n"
        "  \"stop_loss\": \"stop level or condition, e.g. -5% or 1.80 USDT\",\n"
        "  \"trade_duration\": \"expected holding time if TP/SL not hit, e.g. '2-5 days' or '1 month'\"\n"
        "}\n"
        "Rank 'impact_score' by likely market influence "
        "(exchange listings, token burns, major partnerships => high impact). "
        "Make sure the response is valid JSON and contains only the object above."
    )

    payload = {
        "model": GIGACHAT_MODEL,
        "messages": [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": f"Analyze this Binance headline: {title}"}
        ],
        "temperature": 0.30,
        "max_tokens": 300
    }

    last_raw = ""
    last_status = None

    for attempt in range(1, retries + 1):
        try:
            # Используем GigaChat API вместо OpenRouter
            resp = _call_gigachat_api(payload, retries=1)  # retries обрабатываем сами

            if resp is None:
                print(f"⚠️ GigaChat API не ответил (попытка {attempt}/{retries})")
                if attempt < retries:
                    time.sleep(BACKOFF_BASE ** attempt)
                    continue
                _log_bad_response(title, "GigaChat API не ответил", 0, "no response")
                return _default_analysis("GigaChat API не ответил")

            last_status = resp.status_code
            raw_text = _extract_text_from_api_response(resp).strip()
            last_raw = raw_text

            if not raw_text:
                print(f"⚠️ Пустой ответ от GigaChat (попытка {attempt}/{retries}) — status {last_status}")
                if attempt < retries:
                    time.sleep(BACKOFF_BASE ** attempt)
                    continue
                _log_bad_response(title, raw_text, last_status, "empty response")
                return _default_analysis("Пустой ответ")

            json_sub = _balanced_json_substring(raw_text)
            if json_sub:
                try:
                    parsed = json.loads(json_sub)

                    # 🧠 Собираем полный ответ с новыми ключами
                    result = {
                        "impact_score": int(parsed.get("impact_score", 0)),
                        "urgency": str(parsed.get("urgency", "low")).lower(),
                        "reasoning": parsed.get("reasoning", "Нет описания"),
                        "coin": parsed.get("coin", "Не указано"),
                        "take_profit": parsed.get("take_profit", "Не указано"),
                        "stop_loss": parsed.get("stop_loss", "Не указано"),
                        "trade_duration": parsed.get("trade_duration", "Не указано")
                    }

                    return result

                except Exception as e:
                    print(f"⚠️ Ошибка парсинга JSON от GigaChat (попытка {attempt}/{retries}): {e}")
                    if attempt < retries:
                        time.sleep(BACKOFF_BASE ** attempt)
                        continue
                    _log_bad_response(title, raw_text, last_status, "invalid json parse")
                    return _default_analysis("Ошибка JSON")

            print(f"⚠️ В ответе GigaChat нет JSON (попытка {attempt}/{retries})")
            if attempt < retries:
                time.sleep(BACKOFF_BASE ** attempt)
                continue
            _log_bad_response(title, raw_text, last_status, "no json object")
            return _default_analysis("Нет JSON")

        except Exception as e:
            print(f"⚠️ Неожиданная ошибка GigaChat (попытка {attempt}/{retries}): {e}")
            last_raw = str(e)
            last_status = 0
            if attempt < retries:
                time.sleep(BACKOFF_BASE ** attempt)
                continue
            _log_bad_response(title, last_raw, last_status, "unexpected exception")
            return _default_analysis("Неожиданная ошибка")

    _log_bad_response(title, last_raw or "", last_status or 0, "unknown fallback")
    return _default_analysis("Неизвестная ошибка")


def _default_analysis(reason):
    """Возвращает дефолтный ответ при ошибке"""
    return {
        "impact_score": 0,
        "urgency": "low",
        "reasoning": f"Ошибка анализа: {reason}",
        "coin": "Не указано",
        "take_profit": "Не указано",
        "stop_loss": "Не указано",
        "trade_duration": "Не указано"
    }


