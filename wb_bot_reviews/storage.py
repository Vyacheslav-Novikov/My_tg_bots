# storage.py
import json
import os
import uuid
from typing import Any, Dict, List, Optional, Tuple

FILE = "db.json"

SELLER_PROFILES: Dict[str, Dict[str, Any]] = {
    "Имя магазина": {
        "supplier_id": "47...",
        "authorize_v3": "токен",
        "cookies": {
            "external-locale": "ru",
            "x-supplier-id-external": "f2...",
            "wbx-validation-key": "fc..."
        }
    }
}




def _load_file() -> Dict[str, Any]:
    if not os.path.exists(FILE):
        return {}
    try:
        with open(FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

# Загружаем SELLER_PROFILES из db.json если они там есть
db_init = _load_file()
if "SELLER_PROFILES" in db_init:
    SELLER_PROFILES.update(db_init["SELLER_PROFILES"])


def _save_file(data: Dict[str, Any]):
    with open(FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ---------------------------
# User stores and API keys
# ---------------------------
def save_store_token(user_id: int, store_name: str, token: str,
                     supplier_id: Optional[str] = None,
                     seller_profile: Optional[str] = None) -> None:
    token = token.strip()
    db = _load_file()
    uid = str(user_id)
    user = db.get(uid, {})
    stores = user.get("stores", {})
    stores[store_name] = {
        "token": token,
        "supplier_id": supplier_id,
        "seller_profile": seller_profile,
        "api_keys": [token],
    }
    user["stores"] = stores
    user["active_store"] = store_name
    db[uid] = user
    _save_file(db)


def add_api_key_to_store(user_id: int, store_name: str, api_key: str) -> None:
    db = _load_file()
    uid = str(user_id)
    user = db.get(uid, {})
    stores = user.get("stores", {})
    store = stores.get(store_name, {})
    keys = store.get("api_keys", [])
    if api_key not in keys:
        keys.append(api_key)
    store["api_keys"] = keys
    stores[store_name] = store
    user["stores"] = stores
    db[uid] = user
    _save_file(db)


def get_store_tokens(user_id: int) -> Dict[str, str]:
    db = _load_file()
    user = db.get(str(user_id))
    if not user:
        return {}
    stores = user.get("stores", {})
    out = {}
    for name, info in stores.items():
        token = info.get("token") or (info.get("api_keys") or [None])[0]
        out[name] = token
    return out


def get_current_store(user_id: int) -> Optional[str]:
    db = _load_file()
    user = db.get(str(user_id))
    if not user:
        return None
    return user.get("active_store")


def get_current_token(user_id: int) -> Optional[str]:
    store = get_current_store(user_id)
    if not store:
        return None
    return get_store_tokens(user_id).get(store)


def set_active_store(user_id: int, store_name: str):
    db = _load_file()
    uid = str(user_id)
    if uid not in db:
        return
    if store_name in db[uid].get("stores", {}):
        db[uid]["active_store"] = store_name
        _save_file(db)


# ====== CACHE ДЛЯ ОТЗЫВОВ (ТОЛЬКО RAM, БЕЗ JSON) ======
_user_pages: Dict[int, Dict[str, Dict[int, Dict[str, Any]]]] = {}


# Добавь эти переменные и функции после _user_pages в storage.py

# ====== CACHE ДЛЯ ВОПРОСОВ (RAM) ======
_user_questions: Dict[int, Dict[str, Dict[str, Any]]] = {}


def set_user_questions_page(user_id, store, page, questions):
    """
    Сохраняет страницу вопросов в RAM-кэш
    """
    _user_questions.setdefault(user_id, {}).setdefault(store, {})
    _user_questions[user_id][store] = {
        "page": page,
        "questions": questions
    }


def get_questions_page_for(user_id, store):
    """
    Получает сохранённую страницу вопросов
    """
    return _user_questions.get(user_id, {}).get(store)


def get_all_questions_for(user_id, store):
    """
    Получает все вопросы для магазина
    """
    return _user_questions.get(user_id, {}).get(store, {})


# ====== DRAFT AI ДЛЯ ВОПРОСОВ ======
_ai_question_drafts: Dict[str, Dict[str, Any]] = {}


def save_ai_question_draft(draft_id, user_id, question_id, text):
    _ai_question_drafts[draft_id] = {
        "user_id": user_id,
        "question_id": question_id,
        "text": text
    }


def get_ai_question_draft(draft_id):
    return _ai_question_drafts.get(draft_id)


def delete_ai_question_draft(draft_id):
    _ai_question_drafts.pop(draft_id, None)


def set_user_page(user_id, store, stars, page, reviews):
    _user_pages.setdefault(user_id, {}).setdefault(store, {})
    _user_pages[user_id][store][stars] = {
        "page": page,
        "reviews": reviews
    }


def get_page_for(user_id, store, stars):
    return _user_pages.get(user_id, {}).get(store, {}).get(stars)


def get_all_pages_for(user_id, store):
    return _user_pages.get(user_id, {}).get(store, {})


# ====== DRAFT AI ======
_ai_drafts: Dict[str, Dict[str, Any]] = {}


def save_ai_draft(draft_id, user_id, review_id, text):
    _ai_drafts[draft_id] = {"user_id": user_id, "review_id": review_id, "text": text}


def get_ai_draft(draft_id):
    return _ai_drafts.get(draft_id)


def delete_ai_draft(draft_id):
    _ai_drafts.pop(draft_id, None)


def delete_store(user_id: int, store_name: str):
    db = _load_file()
    uid = str(user_id)
    user = db.get(uid)
    if not user:
        return False
    stores = user.get("stores", {})
    if store_name not in stores:
        return False
    del stores[store_name]
    user["stores"] = stores
    if user.get("active_store") == store_name:
        if stores:
            user["active_store"] = next(iter(stores))
        else:
            user["active_store"] = None
    db[uid] = user
    _save_file(db)
    return True


# ---------------------------
# AUTH DATA (legacy)
# ---------------------------
def save_auth_data(user_id: int, api_token: str, authorize_v3: str, cookies: dict):
    db = _load_file()
    uid = str(user_id)
    user = db.get(uid, {})
    stores = user.get("stores", {})
    for name, info in stores.items():
        if info.get("token") == api_token or api_token in (info.get("api_keys") or []):
            info["authorize_v3"] = authorize_v3
            info["cookies"] = cookies
            stores[name] = info
            break
    user["stores"] = stores
    db[uid] = user
    _save_file(db)


def get_auth_data(user_id: int, api_token: str):
    db = _load_file()
    user = db.get(str(user_id))
    if not user:
        return None, None
    for info in user.get("stores", {}).values():
        if info.get("token") == api_token or api_key_in_list(api_key=api_token, info=info):
            return info.get("authorize_v3"), info.get("cookies")
    return None, None


def api_key_in_list(api_key: str, info: Dict[str, Any]) -> bool:
    keys = info.get("api_keys") or []
    return api_key in keys


# ---------------------------
# Utilities for SELLER_PROFILES
# ---------------------------
def get_profile_by_supplier(supplier_id: str) -> Optional[str]:
    for name, info in SELLER_PROFILES.items():
        if str(info.get("supplier_id")) == str(supplier_id):
            return name
    return None


def get_profile_data(profile_name: str) -> Optional[Dict[str, Any]]:
    return SELLER_PROFILES.get(profile_name)


def list_profile_names() -> List[str]:
    return list(SELLER_PROFILES.keys())


def bind_profile_to_store(user_id: int, store_name: str, supplier_id: str, profile_name: str):
    db = _load_file()
    uid = str(user_id)
    user = db.get(uid, {})
    stores = user.get("stores", {})
    store = stores.get(store_name, {})
    store["supplier_id"] = supplier_id
    store["seller_profile"] = profile_name
    stores[store_name] = store
    user["stores"] = stores
    db[uid] = user
    _save_file(db)


def get_store_profile_for_user(user_id: int, store_name: str) -> Optional[str]:
    db = _load_file()
    user = db.get(str(user_id))
    if not user:
        return None
    store = user.get("stores", {}).get(store_name)
    if not store:
        return None
    return store.get("seller_profile")


def find_store_by_supplier(user_id: int, supplier_id: str) -> Optional[str]:
    db = _load_file()
    user = db.get(str(user_id), {})
    stores = user.get("stores", {})
    for name, info in stores.items():
        if str(info.get("supplier_id")) == str(supplier_id):
            return name
    return None


def get_user_api_keys(user_id: int) -> Dict[str, List[str]]:
    db = _load_file()
    user = db.get(str(user_id)) or {}
    stores = user.get("stores", {})
    return {name: info.get("api_keys", []) for name, info in stores.items()}


def set_store_profile_name(user_id: int, store_name: str, profile_name: str):
    db = _load_file()
    uid = str(user_id)
    user = db.get(uid, {})
    stores = user.get("stores", {})
    if store_name in stores:
        stores[store_name]["seller_profile"] = profile_name
        user["stores"] = stores
        db[uid] = user
        _save_file(db)


# ---------------------------
# Шаблоны пользователей (templates)
# хранятся в db.json под ключом "templates"
# структура: templates: { user_id: { template_id: {id,name,text}}}
# ---------------------------
def save_template(user_id: int, name: str, text: str, template_id: Optional[str] = None) -> str:
    """
    Сохраняет шаблон в db.json и возвращает template_id (UUID hex).
    Если template_id передан — обновляет существующий.
    """
    db = _load_file()
    templates = db.get("templates", {})
    user_key = str(user_id)
    user_templates = templates.get(user_key, {})

    if not template_id:
        template_id = uuid.uuid4().hex

    user_templates[template_id] = {"id": template_id, "name": name, "text": text}
    templates[user_key] = user_templates
    db["templates"] = templates
    _save_file(db)
    return template_id


def list_user_templates(user_id: int) -> Dict[str, Dict[str, str]]:
    """
    Возвращает словарь template_id -> {id,name,text} для пользователя.
    """
    db = _load_file()
    templates = db.get("templates", {})
    return templates.get(str(user_id), {})


def get_template(user_id, template_id):
    db = _load_file()
    templates = db.get("templates", {})

    return templates.get(str(user_id), {}).get(template_id)


def delete_template(user_id: int, template_id: str) -> bool:
    db = _load_file()
    templates = db.get("templates", {})
    user_key = str(user_id)
    user_templates = templates.get(user_key, {})
    if template_id in user_templates:
        del user_templates[template_id]
        templates[user_key] = user_templates
        db["templates"] = templates
        _save_file(db)
        return True
    return False


# ---------------------------
# Автоматизация ответов
# ---------------------------
# структура: auto_settings: { user_id: { store_name: {stars: {enabled:bool, method: "ai"|"template", template_id: Optional[str]}}}}
_auto_settings: Dict[str, Dict[str, Dict[int, Dict[str, Any]]]] = {}
# отмеченные как уже обработанные отзывы, чтобы не отвечать дважды:
_processed_reviews: Dict[str, Dict[str, set]] = {}  # user_id -> store -> set(review_id)


def set_auto_toggle(user_id: int, store: str, stars: int, enabled: bool):
    uid = str(user_id)
    _auto_settings.setdefault(uid, {}).setdefault(store, {})
    _auto_settings[uid][store].setdefault(stars, {"enabled": False, "method": "ai", "template_id": None})
    _auto_settings[uid][store][stars]["enabled"] = bool(enabled)


def set_auto_method(user_id: int, store: str, stars: int, method: str, template_id: Optional[str] = None):
    # method: "ai" or "template"
    uid = str(user_id)
    _auto_settings.setdefault(uid, {}).setdefault(store, {})
    _auto_settings[uid][store].setdefault(stars, {"enabled": False, "method": "ai", "template_id": None})
    _auto_settings[uid][store][stars]["method"] = method
    _auto_settings[uid][store][stars]["template_id"] = template_id


def get_auto_settings_for_user(user_id: int) -> Dict[str, Dict[int, Dict[str, Any]]]:
    return _auto_settings.get(str(user_id), {})


def get_auto_setting(user_id: int, store: str, stars: int) -> Optional[Dict[str, Any]]:
    return _auto_settings.get(str(user_id), {}).get(store, {}).get(stars)


def mark_review_processed(user_id: int, store: str, review_id: str):
    uid = str(user_id)
    _processed_reviews.setdefault(uid, {}).setdefault(store, set())
    _processed_reviews[uid][store].add(str(review_id))


def is_review_processed(user_id: int, store: str, review_id: str) -> bool:
    uid = str(user_id)
    return str(review_id) in _processed_reviews.get(uid, {}).get(store, set())


def get_store_cookies(user_id: int, store_name: str):
    db = _load_file()
    user = db.get(str(user_id))
    if not user:
        return None
    store = user.get("stores", {}).get(store_name)
    if not store:
        return None
    return store.get("cookies")


def update_profile_authorize_v3(profile_name: str, new_token: str):
    """
    Обновляет authorize_v3 токен внутри SELLER_PROFILES и сохраняет его в db.json.
    """
    if profile_name not in SELLER_PROFILES:
        return False

    SELLER_PROFILES[profile_name]["authorize_v3"] = new_token

    # сохраняем SELLER_PROFILES в db.json → чтобы изменения не исчезли
    db = _load_file()
    db["SELLER_PROFILES"] = SELLER_PROFILES
    _save_file(db)
    return True
