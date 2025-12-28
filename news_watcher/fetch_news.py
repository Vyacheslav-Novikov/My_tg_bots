import requests


def fetch_binance_news():
    url = "https://www.binance.com/bapi/composite/v1/public/cms/article/list/query?type=1&pageNo=1&pageSize=10"
    try:
        response = requests.get(url, timeout=30)
        data = response.json()
        articles = []

        # Проверяем разные варианты структуры
        if 'data' in data:
            d = data['data']

            # Вариант 1: articles прямо в data
            if isinstance(d, dict) and 'articles' in d and d['articles']:
                articles = d['articles']

            # Вариант 2: data.catalogs[0].articles
            elif 'catalogs' in d and isinstance(d['catalogs'], list) and len(d['catalogs']) > 0:
                catalog = d['catalogs'][0]
                if 'articles' in catalog:
                    articles = catalog['articles']

        # Если ничего не нашли — выводим структуру для отладки
        if not articles:
            print("⚠️ Не найдены статьи. Структура ответа Binance изменилась:")
            print(data)

        return articles

    except Exception as e:
        print(f"Ошибка при получении новостей: {e}")
        return []


def get_article_url(article_code):
    return f"https://www.binance.com/ru/support/announcement/{article_code}"
