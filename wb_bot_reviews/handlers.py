# handlers.py

import logging
import uuid
from aiogram import Router, F, types
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InputMediaPhoto
from aiogram.filters import Command, Filter
import re
from collections import Counter, defaultdict
import asyncio
import requests
from aiogram.filters import StateFilter
from datetime import datetime


# keyboards (твоя реализация)
from keyboards import (
    menu_kb,
    stores_kb,
    reviews_star_kb,
    review_answer_kb,
    next_page_kb,
    ai_result_kb,
    templates_kb,
    template_detail_kb,
    templates_select_kb,
    send_template_kb,
    delete_store_kb,
    automation_method_kb,
    automation_stars_kb,
    analyze_kb,
    new_token_kb,
    question_answer_kb,
    next_page_questions_kb,
    templates_select_question_kb,
    send_template_question_kb,
    ai_result_kb_question
)


# storage и wb_api
import storage
from wb_api import (
    get_reviews,
    get_reviews_by_stars,
    send_reply,  # legacy (через API) — fallback
    send_reply_with_profile,
    get_supplier_id_by_key,
    get_last_reviews_with_profile,
    get_unanswered_questions,
    send_question_answer,
    mark_question_as_viewed
)


from ai import generate_ai_answer, analyze_reviews_summary, generate_ai_question_answer

router = Router()
logging.basicConfig(level=logging.INFO)


# -------------------------
# FSM
# -------------------------

class Form(StatesGroup):
    waiting_for_token = State()
    waiting_for_supplier = State()
    waiting_for_name = State()
    wait_manual_text = State()
    wait_ai_edit = State()
    wait_template_name = State()
    wait_template_text = State()
    wait_edit_template_name = State()
    wait_edit_template_text = State()
    await_new_authorize_v3 = State()
    wait_manual_question_text = State()
    wait_ai_edit_question = State()


class Competitor(Form):
    waiting_for_article = State()
    paging = State()


class AnalyzeArticleFSM(StatesGroup):
    waiting_for_article = State()

# -------------------------
# Start / Menu
# -------------------------

@router.message(F.text == "/start")
async def start_cmd(msg: Message, state: FSMContext):
    await state.clear()
    await msg.answer(
        "Добро пожаловать 👋\nЭтот бот отвечает на отзывы WB.\n\n"
        "➕ Чтобы добавить магазин — нажмите кнопку ниже.",
        reply_markup=menu_kb()
    )


@router.callback_query(F.data == "menu")
async def cb_menu(call: CallbackQuery):
    await call.message.edit_text("<b>Главное меню:</b>\n"
                                 "Выберите действие", reply_markup=menu_kb())


# -------------------------
# Авторизация (WebApp) — оставляем как есть, веб окно может не использоваться
# -------------------------

@router.callback_query(F.data == "auth_wb")
async def open_webapp(call: CallbackQuery):
    token = storage.get_current_token(call.from_user.id)
    if not token:
        return await call.message.answer("⚠️ Сначала добавьте магазин.", reply_markup=menu_kb())

    # строим url если нужно (временно - может не использоваться)
    WEBAPP_BASE = "https://usa-socket-depending-pour.trycloudflare.com"
    user_id = call.from_user.id

    kb = types.InlineKeyboardMarkup(inline_keyboard=[[
        types.InlineKeyboardButton(
            text="🔓 Открыть WebApp для авторизации",
            web_app=types.WebAppInfo(url=f"{WEBAPP_BASE}/webapp?user_id={user_id}&token={token}")
        )
    ]])

    await call.message.answer("Откройте WebApp для авторизации в Wildberries:", reply_markup=kb)


# -------------------------
# Добавить магазин — NEW flow: API key -> Supplier ID (user input) -> name
# -------------------------


@router.callback_query(F.data == "add_store")
async def add_store_btn(call: types.CallbackQuery, state: FSMContext):
    await state.set_state(Form.waiting_for_token)

    text = (
        "Для добавления магазина необходимо ввести API-ключ от вашего кабинета WB Partners\n"
        "Ниже подробная инструкция по созданию этого API-ключа\n\n"
        "1. Переходим в настройки магазина\n"
        "2. Выбираем вкладку 'Доступ к API'\n"
        "3. Вводим произвольное имя ключа\n"
        "4. Выбираем метод API 'Вопросы и отзывы'\n"
        "5. Нажимаем на кнопку 'Создать токен'\n"
        "6. Нажимаем на кнопку 'Скопировать'\n"
        "7. Вставляем API ключ в бот"
    )

    media = [
        InputMediaPhoto(
            media=types.FSInputFile("api_1.jpg")
        ),
        InputMediaPhoto(
            media=types.FSInputFile("api_2.jpg")
        ),
        InputMediaPhoto(
            media=types.FSInputFile("api_3.jpg"),
            caption=text
        )
    ]

    await call.message.answer_media_group(media)


# ШАГ 1 — API-ключ
@router.message(Form.waiting_for_token)
async def add_store_token(message: types.Message, state: FSMContext):
    api_key = message.text.strip()

    if len(api_key) < 20:
        await message.answer("❌ API-ключ слишком короткий. Попробуйте снова.")
        return

    await state.update_data(api_key=api_key)
    await state.set_state(Form.waiting_for_supplier)

    await message.answer("✅ API-ключ сохранён!\nТеперь введите ID аккаунта\n"
                         "Он находятся рядом с ИНН и состоит из 6-ти цифр:")


# ШАГ 2 — supplier_id
@router.message(Form.waiting_for_supplier)
async def add_store_supplier(message: types.Message, state: FSMContext):
    supplier_id = message.text.strip()

    if not supplier_id.isdigit():
        await message.answer("❌ ID должен быть числом. Попробуйте снова.")
        return

    profile_name = storage.get_profile_by_supplier(supplier_id)

    if profile_name is None:
        await message.answer(
            f"❌ Аккаунт с ID <b>{supplier_id}</b> не найден в системе.\n"
            f"Убедитесь, что ID введён правильно."
        )
        return

    await state.update_data(supplier_id=supplier_id, profile_name=profile_name)
    await state.set_state(Form.waiting_for_name)

    await message.answer(
        f"ID найден и принадлежит профилю <b>{profile_name}</b>.\n\n"
        "Введите название магазина (любое слово, чтобы вам было удобно):"
    )


# ШАГ 3 — имя магазина
@router.message(Form.waiting_for_name)
async def add_store_name(message: types.Message, state: FSMContext):
    store_name = message.text.strip()

    if " " in store_name:
        await message.answer("❌ Имя магазина не должно содержать пробелов.")
        return

    data = await state.get_data()
    api_key = data["api_key"]
    supplier_id = data["supplier_id"]
    profile_name = data["profile_name"]
    user_id = message.from_user.id

    # Сохраняем
    storage.save_store_token(
        user_id=user_id,
        store_name=store_name,
        token=api_key,
        supplier_id=supplier_id,
        seller_profile=profile_name
    )

    await state.clear()

    await message.answer(
        f"✅ Магазин <b>{store_name}</b> успешно добавлен!\n"
        f"ID: <b>{supplier_id}</b>\n"
        f"Профиль: <b>{profile_name}</b>",
        reply_markup=menu_kb()
    )


@router.callback_query(F.data == "new_token")
async def start_update_token(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.answer("Введите новый токен authorize_v3:")
    await state.set_state(Form.await_new_authorize_v3)


@router.message(Form.await_new_authorize_v3)
async def save_new_token(message: Message, state: FSMContext):
    new_token = message.text.strip()

    user_id = message.from_user.id
    store = storage.get_current_store(user_id)
    if not store:
        await message.answer("❌ Магазин не выбран.")
        return

    profile = storage.get_store_profile_for_user(user_id, store)
    if not profile:
        await message.answer("❌ У магазина нет привязанного профиля.")
        return

    ok = storage.update_profile_authorize_v3(profile, new_token)
    await state.clear()

    if not ok:
        await message.answer("❌ Не удалось обновить токен.")
        return

    await message.answer("✅ Токен успешно обновлён!")


# --- Анализ отзывов
def _get_article_from_review(r):
    # 1. Прямые ключи (на случай если WB вернёт в разных схемах)
    for key in ("nmId", "nmid", "nm", "offerId", "productNmId",
                "product_id", "imtId", "nomenclatureArticle"):
        if key in r and r.get(key):
            return str(r[key])

    # 2. productInfo — ТУТ ЛЕЖИТ ОСНОВНОЙ АРТИКУЛ WB
    pi = r.get("productInfo")
    if isinstance(pi, dict):
        if pi.get("wbArticle"):
            return str(pi.get("wbArticle"))

        # иногда WB отдаёт supplierArticle как строковый артикул
        if pi.get("supplierArticle"):
            return str(pi.get("supplierArticle"))

    # 3. productDetails (альтернативная схема WB)
    pd = r.get("productDetails")
    if isinstance(pd, dict):
        for key in ("nmId", "nmid", "id", "imtId"):
            if key in pd and pd.get(key):
                return str(pd[key])

    # 4. product (альтернативная схема)
    p = r.get("product")
    if isinstance(p, dict):
        for key in ("nmId", "id", "nmid", "imtId"):
            if key in p and p.get(key):
                return str(p[key])

    # 5. nomenclature
    nom = r.get("nomenclature")
    if isinstance(nom, dict) and nom.get("nmId"):
        return str(nom["nmId"])

    # 6. item
    item = r.get("item")
    if isinstance(item, dict):
        for key in ("nmId", "nmid"):
            if item.get(key):
                return str(item[key])

    # 7. details
    det = r.get("details")
    if isinstance(det, dict):
        for key in ("nmId", "nmid"):
            if det.get(key):
                return str(det[key])

    return "unknown"


# фильтр слов — убираем стоп-слова, цифры, короткие и пунктуацию
_RU_STOPWORDS = {
    "и","в","во","не","что","он","на","я","с","со","как","а","то","все","это","бы","но",
    "за","так","от","себя","к","у","же","ну","вот","или","е","же","же","по","для","его",
    "ее","ее","очень","такой","также","того","там","при","из","по","поэтому","свой","нам",
    "вам","были","была","были","есть","быть","чтобы","уже","ещё","ещё","через","наш","может",
    "что-то","что","очень"
}
_word_re = re.compile(r"[^\wа-яё]+", flags=re.IGNORECASE)


def _extract_keywords(texts, top_n=5):
    if not texts:
        return []
    joined = " ".join(texts).lower()
    # убрать пунктуацию, заменить на пробелы
    cleaned = _word_re.sub(" ", joined)
    tokens = [t.strip() for t in cleaned.split() if t.strip()]
    filtered = [
        t for t in tokens
        if t not in _RU_STOPWORDS and len(t) > 2 and not t.isdigit()
    ]
    cnt = Counter(filtered)
    return cnt.most_common(top_n)


def split_message(text, limit=4000):
    parts = []
    while len(text) > limit:
        split_at = text.rfind("\n", 0, limit)
        if split_at == -1:
            split_at = limit
        parts.append(text[:split_at])
        text = text[split_at:]
    parts.append(text)
    return parts


async def analyze_reviews_logic(reviews, target_article=None):
    """
    Анализ отзывов с использованием AI для качественной выжимки
    """
    if not reviews:
        return "❌ Нет отзывов для анализа."

    # подготовим список отзывов с определёнными артикулами
    by_article = defaultdict(list)
    for r in reviews:
        art = _get_article_from_review(r)
        by_article[art].append(r)

    # если хотим анализ по одному артикулу — фильтруем
    if target_article:
        target_article = str(target_article)
        matched = {a: lst for a, lst in by_article.items() if a == target_article}
        if not matched:
            try:
                matched = {a: lst for a, lst in by_article.items()
                           if str(int(a)) == str(int(target_article))}
            except:
                pass
        if not matched:
            return f"❌ Для артикула {target_article} нет отзывов."
        by_article = matched

    # формируем отчёт по каждому артикулу
    out_lines = []
    for article, items in by_article.items():
        last = items[:100]  # Ограничиваем для AI анализа
        cnt = len(last)

        # Статистика оценок
        scores = []
        for r in last:
            val = r.get("productValuation") or r.get("valuation") or 0
            try:
                scores.append(float(str(val).replace(",", ".")))
            except:
                scores.append(0.0)

        avg = round(sum(scores) / cnt, 1) if cnt else 0.0
        positive = sum(1 for v in scores if v >= 4)
        negative = sum(1 for v in scores if v <= 3)

        # 🔥 Собираем отзывы с текстом для AI анализа
        reviews_for_ai = []

        for r in last:
            # Получаем feedbackInfo
            feedback_info = r.get("feedbackInfo", {})

            # Основные текстовые поля
            main_text = feedback_info.get("feedbackText", "")
            pros_text = feedback_info.get("feedbackTextPros", "")
            cons_text = feedback_info.get("feedbackTextCons", "")

            # Объединяем все текстовые поля
            all_text_parts = []
            for text in [main_text, pros_text, cons_text]:
                if text and str(text).strip() and str(text).strip().lower() not in ["нет", "не указано", "null", "none",
                                                                                    ""]:
                    all_text_parts.append(str(text).strip())

            # Если есть хоть один текст - добавляем в анализ
            if all_text_parts:
                full_text = " | ".join(all_text_parts)
                rating = r.get("productValuation") or r.get("valuation") or 0
                try:
                    rating = int(rating)
                except:
                    rating = 5

                reviews_for_ai.append({
                    "text": full_text,
                    "rating": rating
                })

        # Формируем базовую статистику
        out_lines.append(
            f"📦 Артикул: {article}\n"
            f"📝 Кол-во отзывов: {cnt}\n"
            f"⭐️ Средняя оценка: {avg}\n"
            f"😊 Позитивных: {positive}\n"
            f"😡 Негативных: {negative}\n"
        )

        # 🔥 AI АНАЛИЗ если есть отзывы с текстом
        if reviews_for_ai:
            out_lines.append(f"\n🔍 Проанализировано отзывов с текстом: {len(reviews_for_ai)}\n")

            try:
                # Создаем промпт для AI анализа
                ai_prompt = f"ОТЗЫВЫ НА ТОВАР {article}:\n\n"

                # Добавляем отзывы в промпт
                for i, review_data in enumerate(reviews_for_ai[:15]):  # Ограничиваем количество
                    ai_prompt += f'⭐ {review_data["rating"]}/5: {review_data["text"]}\n\n'

                # 🔥 ИСПОЛЬЗУЕМ НОВУЮ ФУНКЦИЮ ДЛЯ АНАЛИЗА
                ai_analysis = await analyze_reviews_summary(ai_prompt)
                out_lines.append("🤖 AI-анализ отзывов:\n")
                out_lines.append(ai_analysis + "\n")

            except Exception as e:
                print(f"Ошибка AI анализа для артикула {article}: {e}")
                out_lines.append("🤖 AI-анализ: Не удалось выполнить анализ\n")
        else:
            out_lines.append("\n📊 Анализ текста: В отзывах нет текстового содержимого для анализа\n")

        out_lines.append("\n" + "\n")

    return "\n".join(out_lines)


# Главное меню анализа
@router.callback_query(F.data == "analyze")
async def analyze_menu(call: CallbackQuery):
    await call.message.answer(
        "Выберите тип анализа:",
        reply_markup=analyze_kb()
    )


# Общий анализ
@router.callback_query(F.data == "full_analyze")
async def full_analyze_start(call: CallbackQuery, state: FSMContext):
    await call.message.answer("🔍 Собираю последние отзывы... \n"
                              "Анализ может занять до 2х минут ")

    user_id = call.from_user.id
    data = await state.get_data()

    store = storage.get_current_store(user_id)

    # Если в состоянии тоже есть магазин - используем его (для обратной совместимости)
    state_data = await state.get_data()
    store_from_state = state_data.get("store")
    if not store and store_from_state:
        store = store_from_state

    await state.set_state(None)

    if not store:
        return await call.message.answer("❌ Активный магазин не выбран.")

    profile_name = storage.get_store_profile_for_user(user_id, store)
    if not profile_name:
        return await call.message.answer("❌ Профиль не найден. Перезагрузите магазин.")

    status, resp = get_last_reviews_with_profile(profile_name, max_reviews=1000)

    if status != 200 or resp.get("error"):
        return await call.message.answer("❌ Не удалось получить отзывы.")

    reviews = resp.get("data", {}).get("feedbacks", [])
    if not reviews:
        return await call.message.answer("❌ Нет отзывов для анализа.")

    result = await analyze_reviews_logic(reviews)

    for part in split_message(result):
        await call.message.answer(part, reply_markup=menu_kb())


# Анализ по артикулу
@router.callback_query(F.data == "individual_analyze")
async def analyze_by_article_start(call: CallbackQuery, state: FSMContext):
    await state.set_state(AnalyzeArticleFSM.waiting_for_article)
    await call.message.answer("Введите артикул товара ⬇️")


@router.message(AnalyzeArticleFSM.waiting_for_article)
async def analyze_by_article_result(message: types.Message, state: FSMContext):
    article = message.text.strip()
    user_id = message.from_user.id
    store = storage.get_current_store(user_id)
    state_data = await state.get_data()
    store_from_state = state_data.get("store")
    if not store and store_from_state:
        store = store_from_state

    await state.set_state(None)

    if not store:
        return await message.answer("❌ Активный магазин не выбран.")

    profile_name = storage.get_store_profile_for_user(user_id, store)
    if not profile_name:
        return await message.answer("❌ Профиль не найден.")

    status, resp = get_last_reviews_with_profile(profile_name, max_reviews=1000)
    if status != 200 or resp.get("error"):
        return await message.answer("❌ Не удалось получить отзывы.")

    all_reviews = resp.get("data", {}).get("feedbacks", [])
    if not all_reviews:
        return await message.answer("❌ Нет отзывов для анализа.")

    filtered = [r for r in all_reviews if str(_get_article_from_review(r)) == str(article)]
    if not filtered:
        return await message.answer(f"❌ Для артикула {article} нет отзывов.")

    filtered = filtered[:500]

    result = await analyze_reviews_logic(filtered, target_article=article)

    for part in split_message(result):
        await message.answer(part, reply_markup=menu_kb())


# Автоматизация: главное меню автоматизации
@router.callback_query(F.data == "automation_settings")
async def automation_settings_menu(call: CallbackQuery):
    user_id = call.from_user.id
    stores = storage.get_store_tokens(user_id)
    if not stores:
        return await call.message.answer("⚠️ У вас нет магазинов. Добавьте через меню.", reply_markup=menu_kb())
    # если у пользователя несколько магазинов — пока используем активный
    store = storage.get_current_store(user_id)
    user_settings = storage.get_auto_settings_for_user(user_id).get(store, {})
    await call.message.answer("Выберите категорию звёзд для автоматической отправки:", reply_markup=automation_stars_kb(store, user_settings))


# toggle on/off for a specific store & stars
@router.callback_query(F.data.startswith("autotoggle_"))
async def autotoggle(call: CallbackQuery):
    _, store, stars_s = call.data.split("_", 2)
    stars = int(stars_s)
    user_id = call.from_user.id
    cur = storage.get_auto_setting(user_id, store, stars) or {"enabled": False}
    new_state = not bool(cur.get("enabled", False))
    storage.set_auto_toggle(user_id, store, stars, new_state)
    # after enabling, ask method choice if turning on
    if new_state:
        await call.message.answer(f"Включена автоматизация для {stars}⭐. Выберите способ ответа:", reply_markup=automation_method_kb(store, stars))
    else:
        await call.message.answer(f"Выключена автоматизация для {stars}⭐.", reply_markup=automation_stars_kb(store, storage.get_auto_settings_for_user(user_id).get(store, {})))


@router.callback_query(F.data.startswith("automethod_"))
async def automethod(call: CallbackQuery):
    # format: automethod_{store}_{stars}_{method}
    _, store, stars_s, method = call.data.split("_", 3)
    stars = int(stars_s)
    user_id = call.from_user.id

    if method == "ai":
        storage.set_auto_method(user_id, store, stars, "ai", template_id=None)
        await call.message.answer(f"Автоматические ответы для {stars}⭐ будут через AI.", reply_markup=automation_stars_kb(store, storage.get_auto_settings_for_user(user_id).get(store, {})))
        return

    templates = storage.list_user_templates(user_id)
    if not templates:
        await call.message.answer("У вас нет шаблонов. Сначала добавьте шаблон.", reply_markup=templates_kb(templates))
        return

    kb = InlineKeyboardBuilder()
    for tid, info in sorted(templates.items(), key=lambda x: x[1]["name"]):
        kb.button(text=info["name"], callback_data=f"select_autotpl_{store}_{stars}|{tid}")
    kb.button(text="⬅ Настройки автоматизации", callback_data="automation_settings")
    kb.adjust(1)
    await call.message.answer("Выберите шаблон для автоматических ответов:", reply_markup=kb.as_markup())


@router.callback_query(F.data.startswith("select_autotpl_"))
async def select_autotpl(call: CallbackQuery):
    raw = call.data.removeprefix("select_autotpl_")
    # raw = {store}_{stars}|{tid}
    if "|" in raw:
        left, tid = raw.split("|", 1)
        try:
            store, stars_s = left.split("_", 1)
            stars = int(stars_s)
        except Exception:
            return await call.message.answer("⚠️ Неправильный формат.")
    else:
        return await call.message.answer("⚠️ Неправильный формат.")

    user_id = call.from_user.id
    storage.set_auto_method(user_id, store, stars, "template", template_id=tid)
    await call.message.answer(f"Автоматические ответы для {stars}⭐ будут отправляться шаблоном.", reply_markup=automation_stars_kb(store, storage.get_auto_settings_for_user(user_id).get(store, {})))


# Сменить магазин / список магазинов

@router.callback_query(F.data == "switch_store")
async def switch_store(call: CallbackQuery):
    stores = storage.get_store_tokens(call.from_user.id)
    if not stores:
        return await call.message.answer("⚠️ У вас нет магазинов. Добавьте через меню.", reply_markup=menu_kb())

    await call.message.answer("Выберите магазин:", reply_markup=stores_kb(stores))


@router.callback_query(F.data.startswith("store_"))
async def store_selected(call: CallbackQuery, state: FSMContext):
    user_id = call.from_user.id
    store_name = call.data.replace("store_", "")

    # Ставим активный магазин в storage
    storage.set_active_store(user_id, store_name)

    # Достаём данные магазина из storage
    token = storage.get_current_token(user_id)
    profile_name = storage.get_store_profile_for_user(user_id, store_name)

    supplier_id = None
    authorize_v3 = None
    cookies = None

    # Берём все нужные данные ИМЕННО из SELLER_PROFILES
    if profile_name:
        profile_data = storage.get_profile_data(profile_name)
        if profile_data:
            supplier_id = profile_data.get("supplier_id")
            authorize_v3 = profile_data.get("authorize_v3")
            cookies = profile_data.get("cookies")

    # Сохраняем в FSM все данные для ANALYSIS / REVIEW API
    await state.update_data(
        store=store_name,
        token=token,
        supplier_id=supplier_id,
        profile=profile_name,
        authorize_v3=authorize_v3,
        cookies=cookies
    )

    await call.message.answer(
        f"✅ Активный магазин: <b>{store_name}</b>",
        reply_markup=menu_kb()
    )


# Получить отзывы — основной обработчик (вытягиваем через API-key)
@router.callback_query(F.data == "get_reviews")
async def get_reviews_menu(call: CallbackQuery):
    token = storage.get_current_token(call.from_user.id)
    if not token:
        return await call.message.answer("⚠️ Сначала добавьте магазин.", reply_markup=menu_kb())

    status, data = get_reviews(token)
    if status != 200:
        return await call.message.answer(f"Ошибка WB:\n{data}", reply_markup=menu_kb())

    fb = data.get("data", {}).get("feedbacks", [])
    if not fb:
        return await call.message.answer("✅ Новых отзывов нет.", reply_markup=menu_kb())

    # считаем по звёздам
    counts = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    for r in fb:
        s = r.get("productValuation") or 0
        if s in counts:
            counts[s] += 1

    # сохраняем все отзывы в кэш (под user_id, store, stars)
    store = storage.get_current_store(call.from_user.id)

    # save for "all stars" as key 0
    storage.set_user_page(call.from_user.id, store, 0, 0, fb)

    await call.message.answer("Выберите рейтинг отзывов:", reply_markup=reviews_star_kb(counts))


# Показ отзывов по звёздам
@router.callback_query(F.data.startswith("stars_"))
async def show_star_reviews(call: CallbackQuery):
    stars = int(call.data.replace("stars_", ""))

    token = storage.get_current_token(call.from_user.id)
    store = storage.get_current_store(call.from_user.id)

    status, reviews = get_reviews_by_stars(token, stars)
    if status != 200:
        return await call.message.answer(f"Ошибка:\n{reviews}")

    if not reviews:
        return await call.message.answer("✅ Нет отзывов с такой оценкой")

    # сохраняем страницу 0 (первые 10)
    storage.set_user_page(call.from_user.id, store, stars, 0, reviews)

    await send_reviews_page(call.message, reviews, 0, store, stars)


async def send_reviews_page(message: Message, reviews, page, store, stars):
    start = page * 10
    end = start + 10
    chunk = reviews[start:end]

    for r in chunk:
        # ⭐ Оценка
        stars = r.get("productValuation", "?")

        # 👤 Имя покупателя
        name = (
            r.get("userName")
            or r.get("wbUserDetails", {}).get("name")
            or "Покупатель"
        )

        # 🔢 Артикул товара
        article = (
            r.get("nmId")
            or r.get("productId")
            or r.get("source", {}).get("nmId")
            or r.get("productDetails", {}).get("nmId")
            or "—"
        )

        # Текстовые поля
        pros = r.get("pros") or ""
        cons = r.get("cons") or ""
        comment = r.get("text") or ""

        # Формирование текста сообщения
        text_parts = [
            f"🔢 <b>Артикул:</b> {article}",
            f"⭐️ <b>{stars}</b>",
            f"👤 <b>{name}</b>",
        ]

        if pros:
            text_parts.append(f"\n<b>Достоинства:</b> {pros}")
        if cons:
            text_parts.append(f"<b>Недостатки:</b> {cons}")
        if comment:
            text_parts.append(f"<b>Комментарий:</b> {comment}")

        if not (pros or cons or comment):
            text_parts.append("(без комментария)")

        text = "\n".join(text_parts)

        await message.answer(text, reply_markup=review_answer_kb(str(r.get('id'))))

    if end < len(reviews):
        await message.answer(
            f"Показано {end} из {len(reviews)}",
            reply_markup=next_page_kb(store, stars, page + 1)
        )


@router.callback_query(F.data.startswith("next_"))
async def next_page(call: CallbackQuery):
    try:
        _, store, stars_s, page_s = call.data.split("_")
        stars = int(stars_s)
        page = int(page_s)
    except Exception:
        return await call.message.answer("⚠️ Неправильные параметры страницы.")

    page_data = storage.get_page_for(call.from_user.id, store, stars)
    if not page_data:
        return await call.message.answer("⚠️ Страница не найдена.")

    reviews = page_data["reviews"]
    storage.set_user_page(call.from_user.id, store, stars, page, reviews)

    await send_reviews_page(call.message, reviews, page, store, stars)


# Ручной ответ (начало)

@router.callback_query(F.data.startswith("manual_"))
async def manual_start(call: CallbackQuery, state: FSMContext):
    review_id = call.data.replace("manual_", "")
    await state.update_data(review_id=review_id)
    await state.set_state(Form.wait_manual_text)
    await call.message.answer("✍ Напишите ответ:")


@router.message(Form.wait_manual_text)
async def manual_send(msg: Message, state: FSMContext):
    data = await state.get_data()
    review_id = data.get("review_id")
    if not review_id:
        await state.clear()
        return await msg.answer("⚠️ Ошибка: ID отзыва потерян.")

    user_id = msg.from_user.id
    store = storage.get_current_store(user_id)
    if not store:
        await state.clear()
        return await msg.answer("⚠️ Активный магазин не найден.")

    profile_name = storage.get_store_profile_for_user(user_id, store)

    # приоритет: отправляем через профиль (authorize_v3 + cookies)
    if profile_name:
        status, res = send_reply_with_profile(profile_name, review_id, msg.text.strip())
        if status == -1:  # токен истёк
            await msg.answer(
                "❗ Ваш токен авторизации истёк.\n"
                "Нажмите кнопку ниже, чтобы обновить его.",
                reply_markup=new_token_kb()
            )
            return
    else:
        # fallback — попробуем отправить через API-token (legacy)
        token = storage.get_current_token(user_id)
        status, res = send_reply(token, review_id, msg.text.strip())

    await state.clear()

    if status in (200, 201):
        await msg.answer("✅ Ответ отправлен!", reply_markup=menu_kb())
    else:
        await msg.answer(f"Ошибка при отправке: {res}", reply_markup=menu_kb())


# AI: SEND

@router.callback_query(F.data.startswith("ai_send_"))
async def ai_send(call: CallbackQuery):
    draft_id = call.data.replace("ai_send_", "")
    draft = storage.get_ai_draft(draft_id)

    if not draft:
        return await call.message.answer("⚠️ Черновик не найден.")

    user_id = call.from_user.id
    store = storage.get_current_store(user_id)
    profile_name = storage.get_store_profile_for_user(user_id, store)
    text = draft["text"]

    # отправляем
    if profile_name:
        status, res = send_reply_with_profile(profile_name, draft["review_id"], text)
        if status == -1:  # токен истёк
            await call.message.answer(
                "❗ Ваш токен авторизации истёк.\n"
                "Нажмите кнопку ниже, чтобы обновить его.",
                reply_markup=new_token_kb()
            )
            return
    else:
        token = storage.get_current_token(user_id)
        status, res = send_reply(token, draft["review_id"], text)

    storage.delete_ai_draft(draft_id)

    if status in (200, 201):
        await call.message.answer("✅ Ответ отправлен!", reply_markup=menu_kb())
    else:
        await call.message.answer(f"Ошибка при отправке: {res}", reply_markup=menu_kb())


# templates menu
@router.callback_query(F.data == "templates")
async def cb_templates(call: CallbackQuery):
    user_id = call.from_user.id
    templates = storage.list_user_templates(user_id)
    # если нет шаблонов — покажем только кнопку Добавить
    await call.message.edit_text("Ваши шаблоны:", reply_markup=templates_kb(templates))


# добавить шаблон (начало) — / из menu или из списка отзывов
@router.callback_query(F.data == "add_template")
async def cb_add_template(call: CallbackQuery, state: FSMContext):
    await state.set_state(Form.wait_template_name)
    await call.message.answer("Введите название шаблона (короткое, будет на кнопке):")


@router.callback_query(F.data.startswith("add_template_from_review_"))
async def cb_add_template_from_review(call: CallbackQuery, state: FSMContext):
    # формат: add_template_from_review_{review_id}
    review_id = call.data.replace("add_template_from_review_", "")
    await state.update_data(from_review_id=review_id)
    await state.set_state(Form.wait_template_name)
    await call.message.answer("Введите название шаблона (короткое, будет на кнопке):")


@router.message(Form.wait_template_name)
async def handle_template_name(msg: Message, state: FSMContext):
    name = msg.text.strip()
    if not name:
        return await msg.answer("Название не может быть пустым. Попробуйте снова.")
    await state.update_data(template_name=name)
    await state.set_state(Form.wait_template_text)
    await msg.answer("Отлично — теперь введите содержание шаблона (текст, который будет отправляться):")


@router.message(Form.wait_template_text)
async def handle_template_text(msg: Message, state: FSMContext):
    data = await state.get_data()
    name = data.get("template_name")
    text = msg.text.strip()
    user_id = msg.from_user.id

    tid = storage.save_template(user_id, name, text)

    # если начали из ревью — предложим сразу использовать (но не обязательно)
    from_review = data.get("from_review_id")
    await state.clear()

    await msg.answer("✅ Шаблон успешно сохранён!", reply_markup=menu_kb())


# Просмотр списка шаблонов — handled by templates_kb (callback template_{id})
@router.callback_query(F.data.startswith("template_"))
async def template_view(call: CallbackQuery):
    tid = call.data.replace("template_", "")
    user_id = call.from_user.id
    tpl = storage.get_template(user_id, tid)
    if not tpl:
        return await call.message.answer("⚠️ Шаблон не найден.", reply_markup=menu_kb())
    text = f"📄 <b>{tpl['name']}</b>\n\n{tpl['text']}"
    await call.message.answer(text, reply_markup=template_detail_kb(tid))


@router.callback_query(F.data.startswith("delete_template_"))
async def template_delete(call: CallbackQuery):
    tid = call.data.replace("delete_template_", "")
    user_id = call.from_user.id
    ok = storage.delete_template(user_id, tid)
    if ok:
        await call.message.answer("🗑 Шаблон удалён.", reply_markup=menu_kb())
    else:
        await call.message.answer("⚠️ Ошибка при удалении.", reply_markup=menu_kb())


@router.callback_query(F.data.startswith("edit_template_"))
async def template_edit_start(call: CallbackQuery, state: FSMContext):
    tid = call.data.replace("edit_template_", "")
    user_id = call.from_user.id
    tpl = storage.get_template(user_id, tid)
    if not tpl:
        return await call.message.answer("⚠️ Шаблон не найден.", reply_markup=menu_kb())
    # сохранём id и текущ name/text
    await state.update_data(edit_template_id=tid)
    await state.set_state(Form.wait_edit_template_name)
    await call.message.answer("Введите новое название шаблона (или отправьте текущее ещё раз):")


@router.message(Form.wait_edit_template_name)
async def template_edit_name(msg: Message, state: FSMContext):
    name = msg.text.strip()
    if not name:
        return await msg.answer("Название не может быть пустым.")
    await state.update_data(edit_template_name=name)
    await state.set_state(Form.wait_edit_template_text)
    await msg.answer("Теперь введите новое содержание шаблона:")


@router.message(Form.wait_edit_template_text)
async def template_edit_text(msg: Message, state: FSMContext):
    data = await state.get_data()
    tid = data.get("edit_template_id")
    name = data.get("edit_template_name")
    text = msg.text.strip()
    user_id = msg.from_user.id

    if not tid or not name:
        await state.clear()
        return await msg.answer("⚠️ Ошибка при редактировании. Попробуйте снова.", reply_markup=menu_kb())

    storage.save_template(user_id, name, text, template_id=tid)
    await state.clear()
    await msg.answer("✅ Шаблон обновлён.", reply_markup=menu_kb())


# Добавил кнопку "Ответ шаблоном" — поток выбора шаблона и отправки
@router.callback_query(F.data.startswith("temprep_"))
async def template_reply_start(call: CallbackQuery):
    review_id = call.data.replace("temprep_", "")
    user_id = call.from_user.id
    templates = storage.list_user_templates(user_id)

    if not templates:
        kb = templates_select_kb({}, review_id=review_id)
        return await call.message.answer("У вас ещё нет шаблонов. Добавьте первый:", reply_markup=kb)

    kb = templates_select_kb(templates, review_id=review_id)
    await call.message.answer("Выберите шаблон для отправки:", reply_markup=kb)


@router.callback_query(F.data.startswith("selecttpl_"))
async def select_template(call: CallbackQuery):
    raw = call.data.removeprefix("selecttpl_")

    if "|" in raw:
        tid, review_id = raw.split("|", 1)
    else:
        tid, review_id = raw, None

    user_id = call.from_user.id
    tpl = storage.get_template(user_id, tid)

    if not tpl:
        return await call.message.answer("⚠️ Шаблон не найден.", reply_markup=menu_kb())

    text = f"📄 <b>{tpl['name']}</b>\n\n{tpl['text']}"
    await call.message.answer(text, reply_markup=send_template_kb(tid, review_id))


@router.callback_query(F.data.startswith("sendtpl_"))
async def send_template(call: CallbackQuery):
    raw = call.data.removeprefix("sendtpl_")

    if "|" in raw:
        tid, review_id = raw.split("|", 1)
    else:
        tid, review_id = raw, None

    user_id = call.from_user.id
    tpl = storage.get_template(user_id, tid)

    if not tpl:
        return await call.message.answer("⚠️ Шаблон не найден.", reply_markup=menu_kb())

    text = tpl["text"]

    if review_id:
        store = storage.get_current_store(user_id)
        profile_name = storage.get_store_profile_for_user(user_id, store)
        if profile_name:
            status, res = send_reply_with_profile(profile_name, review_id, text)
            if status == -1:  # токен истёк
                await call.message.answer(
                    "❗ Ваш токен авторизации истёк.\n"
                    "Нажмите кнопку ниже, чтобы обновить его.",
                    reply_markup=new_token_kb()
                )
                return
        else:
            token = storage.get_current_token(user_id)
            status, res = send_reply(token, review_id, text)

        if status in (200, 201):
            await call.message.answer("✅ Ответ отправлен!", reply_markup=menu_kb())
        else:
            await call.message.answer(f"Ошибка при отправке: {res}", reply_markup=menu_kb())
    else:
        await call.message.answer("Шаблон выбран.", reply_markup=menu_kb())


# AI: EDIT

@router.callback_query(F.data.startswith("ai_edit_"))
async def ai_edit(call: CallbackQuery, state: FSMContext):
    draft_id = call.data.replace("ai_edit_", "")
    draft = storage.get_ai_draft(draft_id)

    if not draft:
        return await call.message.answer("⚠️ Черновик не найден.")

    await state.set_state(Form.wait_ai_edit)
    await state.update_data(draft_id=draft_id)

    await call.message.answer("✏️ Отредактируйте текст:")
    await call.message.answer(draft["text"])


@router.message(Form.wait_ai_edit)
async def ai_edit_text(msg: Message, state: FSMContext):
    data = await state.get_data()
    draft_id = data.get("draft_id")
    draft = storage.get_ai_draft(draft_id)

    if not draft:
        await state.clear()
        return await msg.answer("⚠️ Черновик не найден.")

    draft["text"] = msg.text.strip()
    await state.clear()

    await msg.answer(
        f"Обновлённый текст:\n\n<b>{draft['text']}</b>",
        reply_markup=ai_result_kb(draft["review_id"], draft_id)
    )


# AI: GENERATE

@router.callback_query(F.data.startswith("ai_GEN_"))
async def ai_generate(call: CallbackQuery):
    review_id = call.data.replace("ai_GEN_", "")
    user_id = call.from_user.id
    store = storage.get_current_store(user_id)

    # --- ищем отзыв только в RAM-кэше ---
    found = None
    pages = storage._user_pages.get(user_id, {}).get(store, {})

    for stars, page in pages.items():
        for r in page["reviews"]:
            if str(r["id"]) == review_id:
                found = r
                break
        if found:
            break

    if not found:
        return await call.message.answer("⚠️ Отзыв не найден.")

    text = found.get("text") or ""
    stars = found.get("productValuation") or 5

    ai_text = await generate_ai_answer(text, stars)

    draft_id = str(uuid.uuid4())
    storage.save_ai_draft(draft_id, user_id, review_id, ai_text)

    await call.message.answer(
        f"🤖 Предложенный ответ:\n\n<b>{ai_text}</b>",
        reply_markup=ai_result_kb(review_id, draft_id)
    )


# Удаление магазина (через меню)

@router.callback_query(F.data == "delete_store")
async def delete_store_menu(call: CallbackQuery):
    stores = storage.get_store_tokens(call.from_user.id)

    if not stores:
        return await call.message.answer("❗ У вас нет сохранённых магазинов", reply_markup=menu_kb())

    await call.message.answer("Выберите магазин для удаления:", reply_markup=delete_store_kb(stores))


@router.callback_query(F.data.startswith("delstore_"))
async def delete_selected(call: CallbackQuery):
    store_name = call.data.replace("delstore_", "")
    ok = storage.delete_store(call.from_user.id, store_name)

    if ok:
        await call.message.answer(f"✅ Магазин <b>{store_name}</b> удалён.", reply_markup=menu_kb())
    else:
        await call.message.answer("⚠ Ошибка при удалении магазина.", reply_markup=menu_kb())


# ОБРАБОТЧИКИ ВОПРОСОВ
# Добавь эти обработчики в конец файла handlers.py (перед _auto_worker_loop)

@router.callback_query(F.data == "get_question")
async def get_questions_menu(call: CallbackQuery):
    """
    Получение неотвеченных вопросов
    """
    user_id = call.from_user.id
    store = storage.get_current_store(user_id)

    if not store:
        return await call.message.answer("⚠️ Сначала выберите магазин.", reply_markup=menu_kb())

    profile_name = storage.get_store_profile_for_user(user_id, store)
    if not profile_name:
        return await call.message.answer("❌ Профиль не найден. Перезагрузите магазин.", reply_markup=menu_kb())

    await call.message.answer("🔍 Загружаю вопросы...")

    status, data = get_unanswered_questions(profile_name)

    if not status:
        return await call.message.answer(f"❌ Ошибка получения вопросов:\n{data}", reply_markup=menu_kb())

    questions = data.get("questions", [])

    if not questions:
        return await call.message.answer("✅ Новых вопросов нет.", reply_markup=menu_kb())

    # Сохраняем в кэш
    storage.set_user_questions_page(user_id, store, 0, questions)

    await call.message.answer(f"📨 Найдено вопросов: {len(questions)}")
    await send_questions_page(call.message, questions, 0, store)


async def send_questions_page(message: Message, questions, page, store):
    start = page * 10
    end = start + 10
    chunk = questions[start:end]

    for q in chunk:
        q_id = q.get("id", "?")

        # Текст вопроса
        question_text = q.get("questionInfo", {}).get("text") or "Без текста"

        # Артикул WB
        article_wb = q.get("productInfo", {}).get("wbArticle") or "—"

        # Артикул продавца
        article_sup = q.get("productInfo", {}).get("supplierArticle") or "—"

        # Название товара
        product_name = q.get("productInfo", {}).get("name") or "—"

        # Имя пользователя
        name = q.get("questionInfo", {}).get("userName") or "Покупатель"

        # Дата
        created_at = q.get("createdDate")
        if created_at:
            try:
                date = datetime.utcfromtimestamp(created_at / 1000).strftime("%d.%m.%Y %H:%M")
            except:
                date = "—"
        else:
            date = "—"

        text = (
            f"📦 <b>{product_name}</b>\n"
            f"🔢 Артикул WB: {article_wb}\n"
            f"🏷 Арт. продавца: {article_sup}\n"
            f"👤 {name}\n"
            f"📅 {date}\n\n"
            f"<b>Вопрос:</b> {question_text}"
        )

        await message.answer(text, reply_markup=question_answer_kb(str(q_id)))

    # Пагинация
    if end < len(questions):
        await message.answer(
            f"Показано {end} из {len(questions)}",
            reply_markup=next_page_questions_kb(store, page + 1)
        )


@router.callback_query(F.data.startswith("next_questions_"))
async def next_questions_page(call: CallbackQuery):
    """
    Следующая страница вопросов
    """
    try:
        _, _, store, page_s = call.data.split("_")
        page = int(page_s)
    except Exception:
        return await call.message.answer("⚠️ Неправильные параметры страницы.")

    page_data = storage.get_questions_page_for(call.from_user.id, store)
    if not page_data:
        return await call.message.answer("⚠️ Страница не найдена.")

    questions = page_data["questions"]
    storage.set_user_questions_page(call.from_user.id, store, page, questions)

    await send_questions_page(call.message, questions, page, store)


# РУЧНОЙ ОТВЕТ НА ВОПРОС

@router.callback_query(F.data.startswith("q_manual_"))
async def manual_question_start(call: CallbackQuery, state: FSMContext):
    """
    Начало ручного ответа на вопрос
    """
    question_id = call.data.replace("q_manual_", "")
    await state.update_data(question_id=question_id)
    await state.set_state(Form.wait_manual_question_text)
    await call.message.answer("✍ Напишите ответ на вопрос:")


@router.message(Form.wait_manual_question_text)
async def manual_question_send(msg: Message, state: FSMContext):
    """
    Отправка ручного ответа на вопрос
    """
    data = await state.get_data()
    question_id = data.get("question_id")

    if not question_id:
        await state.clear()
        return await msg.answer("⚠️ Ошибка: ID вопроса потерян.")

    user_id = msg.from_user.id
    store = storage.get_current_store(user_id)

    if not store:
        await state.clear()
        return await msg.answer("⚠️ Активный магазин не найден.")

    profile_name = storage.get_store_profile_for_user(user_id, store)

    if not profile_name:
        await state.clear()
        return await msg.answer("❌ Профиль не найден.")

    # Отправляем ответ
    status, res = send_question_answer(profile_name, question_id, msg.text.strip())

    await state.clear()

    if status == -1:
        await msg.answer(
            "❗ Ваш токен авторизации истёк.\n"
            "Нажмите кнопку ниже, чтобы обновить его.",
            reply_markup=new_token_kb()
        )
        return

    if status in (200, 201):
        await msg.answer("✅ Ответ на вопрос отправлен!", reply_markup=menu_kb())
    else:
        await msg.answer(f"❌ Ошибка при отправке: {res}", reply_markup=menu_kb())


# AI ОТВЕТ НА ВОПРОС

@router.callback_query(F.data.startswith("ai_q_GEN_"))
async def ai_generate_question(call: CallbackQuery):
    """
    Генерация AI ответа на вопрос
    """
    question_id = call.data.replace("ai_q_GEN_", "")
    user_id = call.from_user.id
    store = storage.get_current_store(user_id)

    # Ищем вопрос в кэше
    found = None
    page_data = storage.get_questions_page_for(user_id, store)

    if page_data:
        for q in page_data.get("questions", []):
            if str(q["id"]) == question_id:
                found = q
                break

    if not found:
        return await call.message.answer("⚠️ Вопрос не найден.")

    question_text = found.get("text")

    # Генерируем ответ через AI
    ai_text = await generate_ai_question_answer(question_text)  # используем 5 звёзд для вопросов

    draft_id = str(uuid.uuid4())
    storage.save_ai_question_draft(draft_id, user_id, question_id, ai_text)

    await call.message.answer(
        f"🤖 Предложенный ответ на вопрос:\n\n<b>{ai_text}</b>",
        reply_markup=ai_result_kb_question(question_id, draft_id)
    )


@router.callback_query(F.data.startswith("ai_q_send_"))
async def ai_send_question(call: CallbackQuery):
    """
    Отправка AI ответа на вопрос
    """
    draft_id = call.data.replace("ai_q_send_", "")
    draft = storage.get_ai_question_draft(draft_id)

    if not draft:
        return await call.message.answer("⚠️ Черновик не найден.")

    user_id = call.from_user.id
    store = storage.get_current_store(user_id)
    profile_name = storage.get_store_profile_for_user(user_id, store)
    text = draft["text"]

    status, res = send_question_answer(profile_name, draft["question_id"], text)

    storage.delete_ai_question_draft(draft_id)

    if status == -1:
        await call.message.answer(
            "❗ Ваш токен авторизации истёк.\n"
            "Нажмите кнопку ниже, чтобы обновить его.",
            reply_markup=new_token_kb()
        )
        return

    if status in (200, 201):
        await call.message.answer("✅ Ответ на вопрос отправлен!", reply_markup=menu_kb())
    else:
        await call.message.answer(f"❌ Ошибка при отправке: {res}", reply_markup=menu_kb())


@router.callback_query(F.data.startswith("ai_q_edit_"))
async def ai_edit_question(call: CallbackQuery, state: FSMContext):
    """
    Редактирование AI ответа на вопрос
    """
    draft_id = call.data.replace("ai_q_edit_", "")
    draft = storage.get_ai_question_draft(draft_id)

    if not draft:
        return await call.message.answer("⚠️ Черновик не найден.")

    await state.set_state(Form.wait_ai_edit_question)
    await state.update_data(draft_id_question=draft_id)

    await call.message.answer("✏️ Отредактируйте текст ответа:")
    await call.message.answer(draft["text"])


@router.message(Form.wait_ai_edit_question)
async def ai_edit_question_text(msg: Message, state: FSMContext):
    """
    Сохранение отредактированного AI ответа на вопрос
    """
    data = await state.get_data()
    draft_id = data.get("draft_id_question")
    draft = storage.get_ai_question_draft(draft_id)

    if not draft:
        await state.clear()
        return await msg.answer("⚠️ Черновик не найден.")

    draft["text"] = msg.text.strip()
    await state.clear()

    await msg.answer(
        f"Обновлённый текст:\n\n<b>{draft['text']}</b>",
        reply_markup=ai_result_kb_question(draft["question_id"], draft_id)
    )


# ОТВЕТ ШАБЛОНОМ НА ВОПРОС

@router.callback_query(F.data.startswith("tempr_q_"))
async def template_reply_question_start(call: CallbackQuery):
    """
    Выбор шаблона для ответа на вопрос
    """
    question_id = call.data.replace("tempr_q_", "")
    user_id = call.from_user.id
    templates = storage.list_user_templates(user_id)

    if not templates:
        kb = templates_select_kb({}, review_id=question_id)
        return await call.message.answer("У вас ещё нет шаблонов. Добавьте первый:", reply_markup=kb)

    kb = templates_select_question_kb(templates, question_id=question_id)
    await call.message.answer("Выберите шаблон для ответа на вопрос:", reply_markup=kb)


@router.callback_query(F.data.startswith("selectt_q_"))
async def select_template_question(call: CallbackQuery):
    """
    Просмотр выбранного шаблона для вопроса
    """
    raw = call.data.removeprefix("selectt_q_")

    if "|" in raw:
        tid, question_id = raw.split("|", 1)
    else:
        tid, question_id = raw, None

    user_id = call.from_user.id
    tpl = storage.get_template(user_id, tid)

    if not tpl:
        return await call.message.answer("⚠️ Шаблон не найден.", reply_markup=menu_kb())

    text = f"📄 <b>{tpl['name']}</b>\n\n{tpl['text']}"
    await call.message.answer(text, reply_markup=send_template_question_kb(tid, question_id))


@router.callback_query(F.data.startswith("sendt_q_"))
async def send_template_question(call: CallbackQuery):
    """
    Отправка шаблона как ответа на вопрос
    """
    raw = call.data.removeprefix("sendt_q_")

    if "|" in raw:
        tid, question_id = raw.split("|", 1)
    else:
        return await call.message.answer("⚠️ Неправильный формат.", reply_markup=menu_kb())

    user_id = call.from_user.id
    tpl = storage.get_template(user_id, tid)

    if not tpl:
        return await call.message.answer("⚠️ Шаблон не найден.", reply_markup=menu_kb())

    text = tpl["text"]
    store = storage.get_current_store(user_id)
    profile_name = storage.get_store_profile_for_user(user_id, store)

    if not profile_name:
        return await call.message.answer("❌ Профиль не найден.", reply_markup=menu_kb())

    status, res = send_question_answer(profile_name, question_id, text)

    if status == -1:
        await call.message.answer(
            "❗ Ваш токен авторизации истёк.\n"
            "Нажмите кнопку ниже, чтобы обновить его.",
            reply_markup=new_token_kb()
        )
        return

    if status in (200, 201):
        await call.message.answer("✅ Ответ на вопрос отправлен!", reply_markup=menu_kb())
    else:
        await call.message.answer(f"❌ Ошибка при отправке: {res}", reply_markup=menu_kb())


async def _auto_worker_loop(stop_event: asyncio.Event):
    """
    Фоновая петля: каждые 60 минут проверяет для всех пользователей их настройки
    и отвечает на новые отзывы по заданным правилам.
    """
    INTERVAL = 20 * 60  # сек (60 минут)
    while not stop_event.is_set():
        # перебираем всех пользователей, у которых есть автонстройки
        users = list(storage.get_auto_settings_for_user.__self__._auto_settings.keys()) if False else None
        # простая реализация: проходим по всем юзерам, которые есть в БД
        try:
            db = storage._load_file()
            user_ids = [k for k in db.keys() if k.isdigit()]
        except Exception:
            user_ids = []

        for uid in user_ids:
            try:
                uid_i = int(uid)
            except:
                continue
            auto = storage.get_auto_settings_for_user(uid_i)
            if not auto:
                continue
            # для каждого магазина в настройках
            for store_name, stars_map in auto.items():
                token = storage.get_store_tokens(uid_i).get(store_name)
                if not token:
                    continue
                for stars, cfg in stars_map.items():
                    if not cfg.get("enabled"):
                        continue
                    # получить отзывы по звезде
                    status, reviews = get_reviews_by_stars(token, int(stars))
                    if status != 200 or not reviews:
                        continue
                    for r in reviews:
                        rid = str(r.get("id"))
                        # пропускаем, если уже обработан
                        if storage.is_review_processed(uid_i, store_name, rid):
                            continue
                        # формируем ответ
                        if cfg.get("method") == "template":
                            tpl = storage.get_template(uid_i, cfg.get("template_id") or "")
                            if not tpl:
                                # не найден шаблон — пропустить
                                continue
                            answer_text = tpl["text"]
                        else:
                            # AI
                            text = r.get("text") or ""
                            stars_val = r.get("productValuation") or 5
                            answer_text = await generate_ai_answer(text, stars_val)

                        # отправляем через профиль если есть
                        profile = storage.get_store_profile_for_user(uid_i, store_name)
                        if profile:
                            status_send, res = send_reply_with_profile(profile, rid, answer_text)
                            if status == -1:  # токен истёк
                                await stop_event.message.answer(
                                    "❗ Ваш токен авторизации истёк.\n"
                                    "Нажмите кнопку ниже, чтобы обновить его.",
                                    reply_markup=new_token_kb()
                                )
                                return

                        else:
                            # fallback to token send via legacy API (оставляем send_reply)
                            status_send, res = send_reply(token, rid, answer_text)

                        if status_send in (200, 201):
                            # пометить как отправленное
                            storage.mark_review_processed(uid_i, store_name, rid)
                            # убрать из RAM-кэша, если он там есть
                            pages = storage.get_all_pages_for(uid_i, store_name)
                            for s_key, page in (pages or {}).items():
                                page_reviews = page.get("reviews", [])
                                page["reviews"] = [x for x in page_reviews if str(x.get("id")) != rid]
                        # иначе — оставляем на следующую итерацию
        # ждем интервал или стоп
        await asyncio.wait([asyncio.create_task(asyncio.sleep(INTERVAL)) , stop_event.wait()], return_when=asyncio.FIRST_COMPLETED)
