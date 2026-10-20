import os
import json
from flask import Flask, request, jsonify, send_from_directory, session, redirect, url_for
from google import genai
from google.genai import types

app = Flask(__name__, static_folder='.', static_url_path='')
app.secret_key = os.environ.get("SECRET_KEY", "my-super-secret-key-123")

# --- ФАЙЛЫ ДЛЯ СОХРАНЕНИЯ ---
USERS_FILE = 'users.json'
CHATS_FILE = 'chats.json'

def load_json(filename):
    if os.path.exists(filename):
        with open(filename, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_json(filename, data):
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# --- НАСТРОЙКА GEMINI ---
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
if GEMINI_API_KEY:
    client = genai.Client(api_key=GEMINI_API_KEY)
else:
    client = None

# --- РОУТЫ ---

@app.route('/')
def index():
    if not session.get('logged_in'):
        return redirect(url_for('login_page'))
    return send_from_directory('.', 'index.html')

@app.route('/login', methods=['GET', 'POST'])
def login_page():
    if request.method == 'POST':
        user = request.form.get('username')
        pwd = request.form.get('password')
        users = load_json(USERS_FILE)
        
        if user in users and users[user] == pwd:
            session['logged_in'] = True
            session['username'] = user
            return redirect(url_for('index'))
        else:
            return send_from_directory('.', 'login.html') + "<div style='color:#ef4444; text-align:center; margin-top:10px; font-family:sans-serif;'>Неверный логин или пароль</div>"
    return send_from_directory('.', 'login.html')

@app.route('/register', methods=['POST'])
def register():
    user = request.form.get('username')
    pwd = request.form.get('password')
    users = load_json(USERS_FILE)
    
    if user in users:
        return send_from_directory('.', 'login.html') + "<div style='color:#ef4444; text-align:center; margin-top:10px; font-family:sans-serif;'>Этот логин уже занят</div>"
        
    if user and pwd:
        users[user] = pwd # Сохраняем пароль как есть (без шифрования)
        save_json(USERS_FILE, users)
        
        # Создаем пустую историю для нового пользователя
        chats = load_json(CHATS_FILE)
        chats[user] = []
        save_json(CHATS_FILE, chats)
        
        session['logged_in'] = True
        session['username'] = user
        return redirect(url_for('index'))
    return redirect(url_for('login_page'))

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    session.pop('username', None)
    return redirect(url_for('login_page'))

# --- API ДЛЯ ЧАТА ---

@app.route('/history', methods=['GET'])
def get_history():
    if not session.get('logged_in'):
        return jsonify([])
    user = session.get('username')
    chats = load_json(CHATS_FILE)
    return jsonify(chats.get(user, []))

@app.route('/chat', methods=['POST'])
def chat():
    if not session.get('logged_in'):
        return jsonify({"reply": "Доступ запрещён."}), 403

    user = session.get('username')
    user_message = (request.json or {}).get("message", "").strip()
    if not user_message:
        return jsonify({"reply": "Пожалуйста, введи вопрос."})
    
    if not client:
        return jsonify({"reply": "Ошибка: не задан GEMINI_API_KEY."})

    # Загружаем историю
    chats = load_json(CHATS_FILE)
    if user not in chats:
        chats[user] = []

    # Сохраняем сообщение пользователя
    chats[user].append({"role": "user", "text": user_message})
    save_json(CHATS_FILE, chats)

    try:
        response = client.models.generate_content(
            model="gemini-3.5-flash-lite",
            contents=user_message,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())]
            )
        )
        reply_text = response.text if response.text else "Не удалось сформулировать ответ."
        
        # Сохраняем ответ бота
        chats[user].append({"role": "bot", "text": reply_text})
        save_json(CHATS_FILE, chats)
        
        return jsonify({"reply": reply_text})
    except Exception as e:
        error_msg = f"Ошибка Gemini: {str(e)}"
        chats[user].append({"role": "bot", "text": error_msg})
        save_json(CHATS_FILE, chats)
        return jsonify({"reply": error_msg})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
