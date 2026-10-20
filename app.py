import os
import requests
from flask import Flask, request, jsonify, send_from_directory

app = Flask(__name__, static_folder='.', static_url_path='')

DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY")
SEARCH_URL = "https://api.deepseek.com/v1/tools/search"
CHAT_URL = "https://api.deepseek.com/chat/completions"


def search_web(query):
    """Ищет информацию в интернете через DeepSeek Search API"""
    if not DEEPSEEK_API_KEY:
        return None, "Ошибка: не задан DEEPSEEK_API_KEY в переменных окружения."

    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "query": query,
        "count": 5,
        "need_content": True
    }

    try:
        r = requests.post(SEARCH_URL, headers=headers, json=payload, timeout=15)
        r.raise_for_status()
        data = r.json()
        results = data.get("results", [])
        if not results:
            return None, "По запросу ничего не найдено."

        context = ""
        for item in results:
            title = item.get("title", "Без названия")
            content = item.get("content") or item.get("summary") or ""
            url = item.get("url", "")
            context += f"[{title}]({url})\n{content}\n\n"
        return context, None
    except Exception as e:
        return None, f"Ошибка поиска: {e}"


def generate_answer(question, context):
    """Отдаёт найденный контекст модели, чтобы она сформулировала ответ"""
    if not DEEPSEEK_API_KEY:
        return "Ошибка: не задан DEEPSEEK_API_KEY."

    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "deepseek-chat",
        "messages": [
            {
                "role": "system",
                "content": (
                    "Ты — полезный ассистент. Отвечай на вопрос пользователя, "
                    "используя предоставленный контекст из интернета. "
                    "Если в контексте нет ответа — честно скажи об этом. "
                    "Отвечай кратко и по делу, на русском языке."
                )
            },
            {
                "role": "user",
                "content": f"Контекст из интернета:\n{context}\n\nВопрос: {question}"
            }
        ]
    }

    try:
        r = requests.post(CHAT_URL, headers=headers, json=payload, timeout=30)
        r.raise_for_status()
        data = r.json()
        return data["choices"][0]["message"]["content"]
    except Exception as e:
        return f"Ошибка генерации ответа: {e}"


@app.route('/')
def index():
    return send_from_directory('.', 'index.html')


@app.route('/chat', methods=['POST'])
def chat():
    user_message = (request.json or {}).get("message", "").strip()
    if not user_message:
        return jsonify({"reply": "Пожалуйста, введи вопрос."})

    context, error = search_web(user_message)
    if error:
        return jsonify({"reply": error})

    answer = generate_answer(user_message, context)
    return jsonify({"reply": answer})


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
