from aiogram.utils.keyboard import InlineKeyboardBuilder
from typing import Optional


def menu_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="📦 Получить отзывы", callback_data="get_reviews")
    kb.button(text="❓ Получить вопросы", callback_data="get_question")
    kb.button(text="📋 Шаблоны", callback_data="templates")
    kb.button(text="⚙ Настройки автоматизации", callback_data="automation_settings")
    kb.button(text="📊 Анализ отзывов", callback_data="analyze")
    kb.button(text="🔁 Сменить магазин", callback_data="switch_store")
    kb.button(text="➕ Добавить магазин", callback_data="add_store")
    kb.button(text="🗑 Удалить магазин", callback_data="delete_store")
    kb.adjust(1)
    return kb.as_markup()


def analyze_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="📊 Общий анализ", callback_data="full_analyze")
    kb.button(text="🏷️ Анализ по артикулу", callback_data="individual_analyze")
    kb.adjust(1)
    return kb.as_markup()


def new_token_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="Обновить токен", callback_data="new_token")
    kb.adjust(1)
    return kb.as_markup()


def stores_kb(stores: dict):
    kb = InlineKeyboardBuilder()
    for name in stores.keys():
        kb.button(text=name, callback_data=f"store_{name}")
    kb.button(text="⬅ Главное меню", callback_data="menu")
    kb.adjust(1)
    return kb.as_markup()


def reviews_star_kb(counts: dict):
    kb = InlineKeyboardBuilder()
    for s in range(5, 0, -1):
        kb.button(text=f"⭐ {s} ({counts.get(s,0)})", callback_data=f"stars_{s}")
    kb.button(text="⬅ Главное меню", callback_data="menu")
    kb.adjust(1)
    return kb.as_markup()


def review_answer_kb(review_id: str):
    kb = InlineKeyboardBuilder()
    kb.button(text="✍ Ответ вручную", callback_data=f"manual_{review_id}")
    kb.button(text="🤖 Ответ AI", callback_data=f"ai_GEN_{review_id}")
    kb.button(text="🧾 Ответ шаблоном", callback_data=f"temprep_{review_id}")
    kb.button(text="⬅ Главное меню", callback_data="menu")
    kb.adjust(1)
    return kb.as_markup()


def next_page_kb(store, stars, page):
    kb = InlineKeyboardBuilder()
    kb.button(text="➡ Следующие 10", callback_data=f"next_{store}_{stars}_{page}")
    kb.button(text="⬅ Главное меню", callback_data="menu")
    kb.adjust(1)
    return kb.as_markup()


def question_answer_kb(question_id: str):
    """
    Клавиатура для ответа на вопрос (аналог review_answer_kb)
    """
    kb = InlineKeyboardBuilder()
    kb.button(text="✍ Ответ вручную", callback_data=f"q_manual_{question_id}")
    kb.button(text="🤖 Ответ AI", callback_data=f"ai_q_GEN_{question_id}")
    kb.button(text="🧾 Ответ шаблоном", callback_data=f"tempr_q_{question_id}")
    kb.button(text="⬅ Главное меню", callback_data="menu")
    kb.adjust(1)
    return kb.as_markup()


def next_page_questions_kb(store, page):
    """
    Пагинация для вопросов
    """
    kb = InlineKeyboardBuilder()
    kb.button(text="➡ Следующие 10", callback_data=f"next_questions_{store}_{page}")
    kb.button(text="⬅ Главное меню", callback_data="menu")
    kb.adjust(1)
    return kb.as_markup()


def ai_result_kb(review_id, draft_id):
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Отправить", callback_data=f"ai_send_{draft_id}")
    kb.button(text="✏️ Редактировать", callback_data=f"ai_edit_{draft_id}")
    kb.button(text="⬅ Главное меню", callback_data="menu")
    kb.adjust(1)
    return kb.as_markup()


def ai_result_kb_question(question_id, draft_id):
    """
    Клавиатура для AI ответа на вопрос
    """
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Отправить", callback_data=f"ai_q_send_{draft_id}")
    kb.button(text="✏️ Редактировать", callback_data=f"ai_q_edit_{draft_id}")
    kb.button(text="⬅ Главное меню", callback_data="menu")
    kb.adjust(1)
    return kb.as_markup()


def delete_store_kb(stores: dict):
    kb = InlineKeyboardBuilder()
    for name in stores.keys():
        kb.button(text=name, callback_data=f"delstore_{name}")
    kb.button(text="⬅ Главное меню", callback_data="menu")
    kb.adjust(1)
    return kb.as_markup()


# Шаблоны: список / выбор / детали
# ----------------------------
def templates_kb(templates: dict):
    """
    templates: dict template_id -> {id,name,text}
    """
    kb = InlineKeyboardBuilder()
    # сортировка по name для удобства
    for tid, info in sorted(templates.items(), key=lambda x: x[1]["name"]):
        kb.button(text=info["name"], callback_data=f"template_{tid}")
    kb.button(text="➕ Добавить шаблон", callback_data="add_template")
    kb.button(text="⬅ Главное меню", callback_data="menu")
    kb.adjust(1)
    return kb.as_markup()


def template_detail_kb(template_id: str):
    kb = InlineKeyboardBuilder()
    kb.button(text="✏️ Редактировать шаблон", callback_data=f"edit_template_{template_id}")
    kb.button(text="🗑 Удалить шаблон", callback_data=f"delete_template_{template_id}")
    kb.button(text="⬅ Шаблоны", callback_data="templates")
    kb.button(text="⬅ Главное меню", callback_data="menu")
    kb.adjust(1)
    return kb.as_markup()


def templates_select_kb(templates: dict, review_id: Optional[str] = None):
    """
    Для выбора шаблона перед ответом на отзыв.
    Если review_id задан — callbacks будут вида selecttpl_{tid}_{review_id}
    Иначе selecttpl_{tid}
    """
    kb = InlineKeyboardBuilder()
    for tid, info in sorted(templates.items(), key=lambda x: x[1]["name"]):
        if review_id:
            kb.button(text=info["name"], callback_data=f"selecttpl_{tid}|{review_id}")
        else:
            kb.button(text=info["name"], callback_data=f"selecttpl_{tid}")
    # возможность добавить новый шаблон прямо отсюда
    if review_id:
        kb.button(text="➕ Добавить шаблон", callback_data=f"add_template_from_review_{review_id}")
    else:
        kb.button(text="➕ Добавить шаблон", callback_data="add_template")
    kb.button(text="⬅ Главное меню", callback_data="menu")
    kb.adjust(1)
    return kb.as_markup()


def templates_select_question_kb(templates: dict, question_id: Optional[str] = None):
    """
    Для выбора шаблона перед ответом на отзыв.
    Если review_id задан — callbacks будут вида selecttpl_{tid}_{review_id}
    Иначе selecttpl_{tid}
    """
    kb = InlineKeyboardBuilder()
    for tid, info in sorted(templates.items(), key=lambda x: x[1]["name"]):
        if question_id:
            kb.button(text=info["name"], callback_data=f"selectt_q_{tid}|{question_id}")
        else:
            kb.button(text=info["name"], callback_data=f"selectt_q_{tid}")
    # возможность добавить новый шаблон прямо отсюда
    if question_id:
        kb.button(text="➕ Добавить шаблон", callback_data=f"add_template_from_review_{question_id}")
    else:
        kb.button(text="➕ Добавить шаблон", callback_data="add_template")
    kb.button(text="⬅ Главное меню", callback_data="menu")
    kb.adjust(1)
    return kb.as_markup()


def send_template_kb(template_id: str, review_id: Optional[str] = None):
    kb = InlineKeyboardBuilder()
    if review_id:
        kb.button(text="✅ Отправить ответ", callback_data=f"sendtpl_{template_id}|{review_id}")
    else:
        kb.button(text="✅ Использовать шаблон", callback_data=f"sendtpl_{template_id}")
    kb.button(text="⬅ Шаблоны", callback_data="templates")
    kb.button(text="⬅ Главное меню", callback_data="menu")
    kb.adjust(1)
    return kb.as_markup()


def send_template_question_kb(template_id: str, question_id: Optional[str] = None):
    kb = InlineKeyboardBuilder()
    if question_id:
        kb.button(text="✅ Отправить ответ", callback_data=f"sendt_q_{template_id}|{question_id}")
    else:
        kb.button(text="✅ Использовать шаблон", callback_data=f"sendt_q_{template_id}")
    kb.button(text="⬅ Шаблоны", callback_data="templates")
    kb.button(text="⬅ Главное меню", callback_data="menu")
    kb.adjust(1)
    return kb.as_markup()


def automation_stars_kb(store: str, settings_for_store: dict):
    """
    показываем 5..1 со статусом (ON/OFF)
    settings_for_store: dict stars-> {enabled,method,template_id}
    """
    kb = InlineKeyboardBuilder()
    for s in range(5, 0, -1):
        st = settings_for_store.get(s, {"enabled": False})
        mark = "✅" if st.get("enabled") else "❌"
        kb.button(text=f"{mark} Отвечать на отзывы ⭐ {s}", callback_data=f"autotoggle_{store}_{s}")
    kb.button(text="⬅ Главное меню", callback_data="menu")
    kb.adjust(1)
    return kb.as_markup()


def automation_method_kb(store: str, stars: int):
    kb = InlineKeyboardBuilder()
    kb.button(text="🧾 Использовать шаблон", callback_data=f"automethod_{store}_{stars}_template")
    kb.button(text="🤖 Использовать AI", callback_data=f"automethod_{store}_{stars}_ai")
    kb.button(text="⬅ Настройки автоматизации", callback_data="automation_settings")
    kb.adjust(1)
    return kb.as_markup()
