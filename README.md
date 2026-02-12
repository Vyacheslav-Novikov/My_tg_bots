# Telegram-бот для автоматизации работы с отзывами Wildberries

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![aiogram](https://img.shields.io/badge/aiogram-3.5.0-blue.svg)](https://github.com/aiogram/aiogram)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

Полнофункциональный Telegram-бот для автоматизации работы продавцов с отзывами и вопросами покупателей на маркетплейсе Wildberries. Интегрирован с AI (DeepSeek) для генерации естественных ответов и включает систему аналитики отзывов.

## Содержание

- [Возможности](#возможности)
- [Технологии](#технологии)
- [Установка](#установка)
- [Настройка](#настройка)
- [Использование](#использование)
- [Структура проекта](#структура-проекта)
- [API Endpoints](#api-endpoints)

## Возможности

### Работа с отзывами
- Получение отзывов с фильтрацией по рейтингу (1-5 звезд)
- Три способа ответа:
  - Ручной ввод
  - AI-генерация (DeepSeek)
  - Готовые шаблоны
- Пагинация — удобный просмотр по 10 отзывов
- Редактирование AI-ответов перед отправкой

### Автоматизация
- Фоновая обработка — автоматические ответы каждые 20 минут
- Гибкие настройки — отдельные правила для каждого рейтинга (1-5 звезд)
- Два режима:
  - AI-генерация для персонализированных ответов
  - Шаблоны для типовых ситуаций
- Защита от дублей — отслеживание уже обработанных отзывов

### Работа с вопросами покупателей
- Получение вопросов — автоматическая загрузка неотвеченных
- Контекст товара — артикулы, название, данные покупателя
- AI-ответы — специальные промпты для вопросов
- Все способы ответа — как для отзывов (ручной/AI/шаблон)

### Аналитика и инсайты
- AI-анализ отзывов — автоматическое выявление:
  - Что хвалят покупатели
  - На что жалуются
  - Рекомендации для улучшения товара
- Анализ по артикулу — детальная статистика конкретного товара
- Статистика — средний рейтинг, соотношение позитивных/негативных

### Управление
- Несколько магазинов — неограниченное количество на пользователя
- Быстрое переключение между магазинами
- Система шаблонов — создание, редактирование, удаление
- Безопасное хранение API-ключей и JWT-токенов

## Технологии

| Компонент | Технология | Версия | Назначение |
|-----------|-----------|--------|------------|
| **Фреймворк бота** | [aiogram](https://github.com/aiogram/aiogram) | 3.5.0 | Асинхронная работа с Telegram Bot API |
| **HTTP-клиент** | [requests](https://github.com/psf/requests) | 2.31.0 | Взаимодействие с WB API |
| **AI модель** | [DeepSeek](https://platform.deepseek.com/) | latest | Генерация естественных ответов |
| **AI Gateway** | [OpenRouter](https://openrouter.ai/) | v1 | Доступ к DeepSeek API |
| **Язык** | Python | 3.10+ | Основной язык разработки |
| **Хранилище** | JSON + RAM | - | Гибридная модель данных |


### Гибридная модель хранения

**Постоянное хранилище (JSON)**:
- Профили пользователей и магазинов
- API-ключи и JWT-токены
- Шаблоны ответов
- Конфигурация профилей продавцов

**Оперативное хранилище (RAM)**:
- Кэш страниц отзывов (пагинация)
- Временные AI-черновики
- Настройки автоматизации
- ID обработанных отзывов

## Установка

### Предварительные требования

- Python 3.10 или выше
- pip (менеджер пакетов Python)
- Telegram аккаунт
- API-ключ Wildberries
- API-ключ OpenRouter (для AI)

### Шаг 1: Клонирование репозитория

```bash
git clone https://github.com/YOUR_USERNAME/wb-reviews-bot.git
cd wb-reviews-bot
```

### Шаг 2: Установка зависимостей

```bash
pip install -r requirements.txt
```

**requirements.txt**:
```
aiogram==3.5.0
requests==2.31.0
```

### Шаг 3: Создание Telegram бота

1. Найдите [@BotFather](https://t.me/botfather) в Telegram
2. Отправьте команду `/newbot`
3. Следуйте инструкциям для создания бота
4. Сохраните полученный токен (формат: `123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11`)

### Шаг 4: Получение API-ключа OpenRouter

1. Зарегистрируйтесь на [OpenRouter](https://openrouter.ai/)
2. Перейдите в раздел [API Keys](https://openrouter.ai/keys)
3. Создайте новый ключ
4. Сохраните ключ (формат: `sk-or-v1-...`)

## Настройка

### 1. Конфигурация бота

Откройте файл `bot.py` и замените токен бота:

```python
BOT_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"
```

**Рекомендация**: Используйте переменные окружения для безопасности:

```python
import os
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
```

Создайте файл `.env`:
```env
BOT_TOKEN=123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11
OPENROUTER_API_KEY=sk-or-v1-...
```

### 2. Конфигурация AI

Откройте файл `ai.py` и замените API-ключ:

```python
API_KEY = "YOUR_OPENROUTER_API_KEY"
```

### 3. Настройка профилей продавцов

В файле `storage.py` настройте `SELLER_PROFILES`:

```python
SELLER_PROFILES = {
    "Имя продавца 1": {
        "supplier_id": "123456",
        "authorize_v3": "JWT_TOKEN",
        "cookies": {
            "external-locale": "ru",
            "x-supplier-id-external": "uuid-here",
            "wbx-validation-key": "uuid-here"
        }
    },
    # Добавьте свои профили
}
```

#### Как получить `authorize_v3` и cookies:

1. Откройте [seller.wildberries.ru](https://seller.wildberries.ru/) в браузере
2. Откройте DevTools (F12) → вкладка Network
3. Обновите страницу
4. Найдите любой запрос к `seller-services.wildberries.ru`
5. Скопируйте из заголовков:
   - `AuthorizeV3` → `authorize_v3`
   - Cookies → `cookies`

## Использование

### Запуск бота

```bash
python bot.py
```

Вы должны увидеть:
```
✅ Бот запущен!
INFO:aiogram:Polling started
```

### Первоначальная настройка в Telegram

1. **Запустите бота** — отправьте `/start`
2. **Добавьте магазин**:
   - Нажмите "➕ Добавить магазин"
   - Введите API-ключ от WB Partners
   - Введите Supplier ID (6-9 цифр)
   - Придумайте название магазина (без пробелов)
3. **Готово!** Магазин добавлен

### Основные сценарии использования

#### Ответ на отзыв

```
1. Главное меню → "Получить отзывы"
2. Выберите рейтинг (например, "5 звезд (157)")
3. Просмотрите отзыв
4. Выберите способ ответа:
   - Ручной ввод
   - AI-генерация (рекомендуется)
   - Выбрать шаблон
5. Проверьте и отправьте
```

#### Настройка автоматизации

```
1. Главное меню → "Настройки автоматизации"
2. Выберите рейтинг (например, 5 звезд)
3. Включите автоматизацию
4. Выберите метод:
   - AI (персонализированные ответы)
   - Шаблон (выберите из списка)
5. Готово! Бот будет отвечать автоматически каждые 20 минут
```

#### Анализ отзывов

```
1. Главное меню → "Анализ отзывов"
2. Выберите тип:
   - "Общий анализ" — все товары
   - "Анализ по артикулу" — конкретный товар
3. Дождитесь результата (10-60 секунд)
4. Получите AI-отчет с рекомендациями
```

#### Ответ на вопрос покупателя

```
1. Главное меню → "Получить вопросы"
2. Просмотрите вопрос с контекстом товара
3. Выберите способ ответа (ручной/AI/шаблон)
4. Отправьте ответ
```

#### Создание шаблона

```
1. Главное меню → "Шаблоны"
2. Нажмите "Добавить шаблон"
3. Введите название (например, "5 звезд")
4. Введите текст ответа
5. Шаблон сохранён и доступен для использования
```

## Структура проекта

```
wb-reviews-bot/
├── bot.py                  # Точка входа, инициализация бота
├── handlers.py             # Обработчики команд и callback'ов
├── keyboards.py            # Inline-клавиатуры интерфейса
├── storage.py              # Слой работы с данными
├── wb_api.py              # API Wildberries
├── ai.py                  # AI-генерация и анализ
├── db.json                # База данных (создаётся автоматически)
├── requirements.txt        # Зависимости Python
├── README.md              # Документация
├── .env.example           # Пример файла окружения
└── .gitignore             # Игнорируемые файлы
```

### Описание модулей

| Файл | Строки | Функций | Описание |
|------|--------|---------|----------|
| `bot.py` | ~40 | 1 | Инициализация бота, запуск polling и фонового процесса |
| `handlers.py` | ~1700 | 58 | Обработка всех команд, callback'ов и FSM-состояний |
| `storage.py` | ~480 | 35 | CRUD операции с JSON и RAM-кэшем |
| `wb_api.py` | ~430 | 9 | Интеграция с Wildberries API |
| `ai.py` | ~170 | 3 | Генерация ответов и анализ через DeepSeek |
| `keyboards.py` | ~240 | 17 | Генерация inline-клавиатур |

## API Endpoints

### Wildberries API

#### Получение отзывов (публичное API)

```http
GET https://feedbacks-api.wildberries.ru/api/v1/feedbacks
Authorization: Bearer {API_KEY}
Query Params:
  - isAnswered: "false"
  - take: 200
  - skip: 0
```

#### Получение отзывов через профиль (расширенное)

```http
GET https://seller-services.wildberries.ru/ns/fa-seller-api/reviews-ext-seller-portal/api/v2/feedbacks
Headers:
  - AuthorizeV3: {JWT_TOKEN}
  - Cookie: {...}
Query Params:
  - cursor: ""
  - isAnswered: "false"
  - limit: 100
  - sortOrder: "dateDesc"
  - valuations: [1,2,3,4,5]
```

#### Отправка ответа на отзыв

```http
POST https://seller-services.wildberries.ru/ns/fa-seller-api/reviews-ext-seller-portal/api/v2/feedbacks/answer
Headers:
  - AuthorizeV3: {JWT_TOKEN}
  - Content-Type: application/json
  - X-Supplier-Id: {SUPPLIER_UUID}
Body:
  {
    "answerText": "Текст ответа",
    "feedbackId": "review_id"
  }
```

#### Получение вопросов

```http
GET https://seller-services.wildberries.ru/ns/fa-seller-api/reviews-ext-seller-portal/api/v1/questions
Headers:
  - AuthorizeV3: {JWT_TOKEN}
Query Params:
  - cursor: ""
  - isAnswered: "false"
  - limit: 50
  - sortOrder: "dateDesc"
```

#### Ответ на вопрос

```http
PATCH https://seller-services.wildberries.ru/ns/fa-seller-api/reviews-ext-seller-portal/api/v1/questions/answer
Headers:
  - AuthorizeV3: {JWT_TOKEN}
  - Content-Type: application/json
Body:
  {
    "answerText": "Текст ответа",
    "questionId": "question_id"
  }
```

### OpenRouter API (DeepSeek)

```http
POST https://openrouter.ai/api/v1/chat/completions
Headers:
  - Authorization: Bearer {OPENROUTER_API_KEY}
  - Content-Type: application/json
Body:
  {
    "model": "deepseek/deepseek-chat",
    "max_tokens": 300,
    "messages": [
      {"role": "system", "content": "Ты менеджер Wildberries"},
      {"role": "user", "content": "Промпт с контекстом"}
    ]
  }
```

