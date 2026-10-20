import os
from flask import Flask, request, jsonify, send_from_directory
from google import genai
from google.genai import types

# Настраиваем Flask (разрешаем отдавать index.html из этой же папки)
app = Flask(__name__, static_folder='.', static_url_path='')

# Читаем ключ Gemini из переменных окружения SnapDeploy
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# Инициализируем клиент Gemini
if GEMINI_API_KEY:
    client = genai.Client(api_key=GEMINI_API_KEY)
else:
    client = None

@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

@app.route('/chat', methods=['POST'])
def chat():
    user_message = (request.json or {}).get("message", "").strip()
    if not user_message:
        return jsonify({"reply": "Пожалуйста, введи вопрос."})
    
    if not client:
        return jsonify({"reply": "Ошибка: не задан GEMINI_API_KEY в переменных окружения SnapDeploy."})

    try:
        # Вызываем Gemini с включенным инструментом Google Search (поиск в интернете)
        response = client.models.generate_content(
            model="gemini-2.5-flash-lite", # Бесплатная и быстрая модель
            contents=user_message,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())]
            )
        )
        
        # Извлекаем текст ответа
        reply_text = response.text if response.text else "Не удалось сформулировать ответ."
        
        return jsonify({"reply": reply_text})
        
    except Exception as e:
        return jsonify({"reply": f"Ошибка Gemini: {str(e)}"})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
