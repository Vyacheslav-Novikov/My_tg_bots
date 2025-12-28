# wb_api.py
import requests
from typing import Tuple, Any, List, Optional
import json
from storage import get_profile_data, SELLER_PROFILES
import storage
import handlers
import logging


BASE = "https://feedbacks-api.wildberries.ru/api/v1/feedbacks"
TIMEOUT = 30


def _headers(token: str):
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "User-Agent": "wb-bot"
    }


def get_reviews(token: str):
    try:
        r = requests.get(
            BASE,
            headers=_headers(token),
            params={"isAnswered": "false", "take": 200, "skip": 0},
            timeout=TIMEOUT
        )
    except Exception as e:
        return 0, str(e)

    try:
        data = r.json()
    except:
        return r.status_code, r.text

    return r.status_code, data


def get_reviews_by_stars(token: str, stars: int) -> Tuple[int, List[Any]]:
    status, data = get_reviews(token)
    if status != 200:
        return status, data

    arr = data.get("data", {}).get("feedbacks", [])
    filtered = [r for r in arr if (r.get("productValuation") or 0) == stars]
    return 200, filtered


def send_reply(token: str, review_id: str, text: str):
    headers = {**_headers(token), "Content-Type": "application/json"}
    body = {"text": text}

    urls = [
        f"{BASE}/{review_id}/answer",
        f"{BASE}/{review_id}/answers",
        f"{BASE}/{review_id}/reply"
    ]

    for url in urls:
        try:
            r = requests.post(url, headers=headers, json=body, timeout=TIMEOUT)
            try:
                data = r.json()
            except:
                data = r.text

            if r.status_code in (200, 201):
                return r.status_code, data
            return r.status_code, data

        except Exception as e:
            last = str(e)

    return 0, last


# Получить supplier_id по API-ключу
def get_supplier_id_by_key(token: str) -> Tuple[int, Optional[str]]:
    url = "https://suppliers-api.wildberries.ru/api/v3/suppliers"

    try:
        r = requests.get(url, headers=_headers(token), timeout=TIMEOUT)
    except Exception as e:
        return 0, str(e)

    print("SUPPLIER DEBUG:", r.status_code, r.text)   # ← лог

    if r.status_code != 200:
        return r.status_code, None

    try:
        j = r.json()
    except:
        return r.status_code, None

    arr = j.get("data")
    if not arr or not isinstance(arr, list):
        return 200, None

    supplier_id = arr[0].get("id")
    if supplier_id:
        return 200, str(supplier_id)

    return 200, None


# Отправка ответа через seller-services используя authorize_v3 + cookies из профиля
def send_reply_with_profile(profile_name: str, review_id: str, answer_text: str) -> Tuple[int, Any]:
    profile = get_profile_data(profile_name)
    if not profile:
        return 0, f"profile {profile_name} not found"

    authorize_v3 = profile.get("authorize_v3")
    cookies = profile.get("cookies", {})

    url = "https://seller-services.wildberries.ru/ns/fa-seller-api/reviews-ext-seller-portal/api/v2/feedbacks/answer"

    headers = {
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json;charset=UTF-8",
        "AuthorizeV3": authorize_v3,
        "Origin": "https://seller.wildberries.ru",
        "Referer": "https://seller.wildberries.ru/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/142.0.0.0 Safari/537.36",
        # X-Supplier-Id может потребоваться
        "X-Supplier-Id": cookies.get("x-supplier-id-external", "")
    }

    data = {
        "answerText": answer_text,
        "feedbackId": review_id,
    }

    try:
        resp = requests.post(url, headers=headers, cookies=cookies, json=data, timeout=TIMEOUT)
        try:
            body = resp.json()
        except Exception:
            body = resp.text
        # Если токен устарел — вернём спец-метку
        if resp.status_code in (401, 403):
            return -1, "TOKEN_EXPIRED"

        return resp.status_code, body

    except Exception as e:
        return 0, str(e)


REVIEWS_URL = "https://seller.wildberries.ru/ns/suppliers-feedback-card/api/v1/feedbacks"


def get_last_reviews_with_profile(profile_name: str, max_reviews: int = 1000):
    profile = storage.get_profile_data(profile_name)
    if not profile:
        return 0, {"error": "profile not found"}

    cookies = profile.get("cookies", {})
    auth = profile.get("authorize_v3")

    if not cookies or not auth:
        return 0, {"error": "no cookies or authorize_v3"}

    url = "https://seller-services.wildberries.ru/ns/fa-seller-api/reviews-ext-seller-portal/api/v2/feedbacks"

    headers = {
        "accept": "*/*",
        "content-type": "application/json",
        "authorizev3": auth,
        "user-agent": "Mozilla/5.0"
    }

    def fetch_all(is_answered: str, max_count: int):
        items = []
        cursor = ""
        while len(items) < max_count:
            params = {
                "cursor": cursor,
                "isAnswered": is_answered,
                "limit": "100",
                "sortOrder": "dateDesc",
                "valuations": [1, 2, 3, 4, 5],
            }
            try:
                r = requests.get(url, headers=headers, cookies=cookies, params=params)
                if r.status_code != 200:
                    break

                data = r.json().get("data", {})
                batch_items = data.get("feedbacks", [])
                if not batch_items:
                    break

                items.extend(batch_items)

                # Проверяем, есть ли следующая страница
                new_cursor = data.get("cursor")
                if not new_cursor or new_cursor == cursor:
                    break
                cursor = new_cursor

                # Если достигли лимита
                if len(items) >= max_count:
                    items = items[:max_count]
                    break

            except Exception as e:
                logging.exception(f"Ошибка при запросе WB API для is_answered={is_answered}")
                break
        return items

    # Получаем отзывы обоих типов с пагинацией
    not_answered = fetch_all("false", max_reviews)
    answered = fetch_all("true", max_reviews - len(not_answered))
    all_reviews = not_answered + answered

    # Сортируем по дате (новые сначала)
    try:
        all_reviews.sort(key=lambda r: r.get("createdDate") or "", reverse=True)
    except:
        pass

    return 200, {"data": {"feedbacks": all_reviews}}


def get_all_reviews_by_article(profile_name: str, article: str = None, max_reviews: int = 1000):
    profile = storage.get_profile_data(profile_name)
    if not profile:
        return 0, {"error": "profile not found"}

    cookies = profile.get("cookies", {})
    auth = profile.get("authorize_v3")
    if not cookies or not auth:
        return 0, {"error": "no cookies or authorize_v3"}

    url = "https://seller-services.wildberries.ru/ns/fa-seller-api/reviews-ext-seller-portal/api/v2/feedbacks"
    headers = {
        "accept": "*/*",
        "content-type": "application/json",
        "authorizev3": auth,
        "user-agent": "Mozilla/5.0"
    }

    all_items = []
    cursor = ""
    while len(all_items) < max_reviews:
        params = {
            "cursor": cursor,
            "isAnswered": "all",
            "limit": "100",
            "sortOrder": "dateDesc",
            "valuations": [1,2,3,4,5],
        }
        try:
            r = requests.get(url, headers=headers, cookies=cookies, params=params)
            if r.status_code != 200:
                break

            data = r.json().get("data")
            if not data:
                break

            items = data.get("feedbacks", [])
            if not items:
                break

            all_items.extend(items)
            if len(all_items) >= max_reviews:
                all_items = all_items[:max_reviews]
                break

            new_cursor = data.get("cursor")
            if not new_cursor or new_cursor == cursor:
                break
            cursor = new_cursor
        except Exception as e:
            logging.exception("Ошибка при запросе WB API")
            break

    # Фильтруем по артикулу, если указан
    if article:
        filtered = [r for r in all_items if str(handlers._get_article_from_review(r)) == str(article)]
        all_items = filtered[:max_reviews]

    return 200, {"data": {"feedbacks": all_items}}


def get_unanswered_questions(profile_name):
    prof = SELLER_PROFILES.get(profile_name)
    if not prof:
        return False, "profile_not_found"

    authorize = prof.get("authorize_v3")
    cookies = prof.get("cookies")
    if not authorize or not cookies:
        return False, "missing_credentials"

    url = "https://seller-services.wildberries.ru/ns/fa-seller-api/reviews-ext-seller-portal/api/v1/questions"

    headers = {
        "authorizev3": authorize,
        "Content-Type": "application/json",
        "user-agent": "Mozilla/5.0"
    }

    params = {
        "cursor": "",
        "isAnswered": "false",
        "limit": "50",
        "sortOrder": "dateDesc"
    }

    try:
        r = requests.get(url, headers=headers, cookies=cookies, params=params, timeout=30)
        j = r.json()

        data = j.get("data", {})
        questions = data.get("questions", [])
        total_unanswered = data.get("totalUnanswered", len(questions))

        return True, {
            "questions": questions,
            "total_unanswered": total_unanswered
        }

    except Exception as e:
        return False, str(e)


def send_question_answer(profile_name: str, question_id: str, answer_text: str) -> Tuple[int, Any]:
    profile = get_profile_data(profile_name)
    if not profile:
        return 0, f"profile {profile_name} not found"

    authorize_v3 = profile.get("authorize_v3")
    cookies = profile.get("cookies", {})
    url = "https://seller-services.wildberries.ru/ns/fa-seller-api/reviews-ext-seller-portal/api/v1/questions/answer"

    headers = {
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json;charset=UTF-8",
        "AuthorizeV3": authorize_v3,
        "Origin": "https://seller.wildberries.ru",
        "Referer": "https://seller.wildberries.ru/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/142.0.0.0 Safari/537.36",
        "X-Supplier-Id": cookies.get("x-supplier-id-external", "")
    }

    data = {
        "answerText": answer_text,
        "questionId": question_id
    }

    try:
        resp = requests.patch(url, headers=headers, cookies=cookies, json=data, timeout=TIMEOUT)

        # Логи для отладки
        print(f"[QUESTION ANSWER] Status: {resp.status_code}")
        print(f"[QUESTION ANSWER] Request data: {data}")
        print(f"[QUESTION ANSWER] Response: {resp.text[:500]}")

        try:
            body = resp.json()
        except Exception:
            body = resp.text

        if resp.status_code in (401, 403):
            return -1, "TOKEN_EXPIRED"

        return resp.status_code, body

    except Exception as e:
        print(f"[QUESTION ANSWER] Exception: {e}")
        return 0, str(e)


def mark_question_as_viewed(profile_name: str, question_id: str) -> Tuple[int, Any]:
    profile = get_profile_data(profile_name)
    if not profile:
        return 0, f"profile {profile_name} not found"

    authorize_v3 = profile.get("authorize_v3")
    cookies = profile.get("cookies", {})

    url = "https://seller-services.wildberries.ru/ns/fa-seller-api/reviews-ext-seller-portal/api/v1/questions/viewed"

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "AuthorizeV3": authorize_v3,
        "User-Agent": "Mozilla/5.0"
    }

    data = {"id": question_id}

    try:
        resp = requests.patch(url, headers=headers, cookies=cookies, json=data, timeout=TIMEOUT)
        return resp.status_code, resp.text
    except Exception as e:
        return 0, str(e)
