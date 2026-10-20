import os
import sqlite3
from flask import Flask, request, jsonify, send_from_directory, session, redirect, url_for
from google import genai
from google.genai import types

app = Flask(__name__, static_folder='.', static_url_path='')
app.secret_key = os.environ.get("SECRET_KEY", "my-super-secret-key-123")

# --- БАЗА ДАННЫХ SQLITE ---
def init_db():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    # Таблица пользователей
    c.execute('''CREATE TABLE IF NOT EXISTS users 
                 (username TEXT PRIMARY KEY, password TEXT)''')
    # Таблица истории чатов
    c.execute('''CREATE TABLE IF NOT EXISTS messages 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, role TEXT, text TEXT)''')
    conn.commit()
    conn.close()

init_db()

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
        
        conn = sqlite3.connect('database.db')
        c = conn.cursor()
        c.execute("SELECT password FROM users WHERE username=?", (user,))
        result = c.fetchone()
        conn.close()
        
        if result and result[0] == pwd:
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
    
    if not user or not pwd:
        return "Логин и пароль обязательны", 400

    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    try:
        c.execute("INSERT INTO users (username, password) VALUES (?, ?)", (user, pwd))
        conn.commit()
        conn.close()
        
        session['logged_in'] = True
        session['username'] = user
        return redirect(url_for('index'))
    except sqlite3.IntegrityError:
        conn.close()
        return send_from_directory('.', 'login.html') + "<div style='color:#ef4444; text-align:center; margin-top:10px; font-family:sans-serif;'>Этот логин уже занят</div>"

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
    
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("SELECT role, text FROM messages WHERE username=? ORDER BY id ASC", (user,))
    rows = c.fetchall()
    conn.close()
    
    history = [{"role": row[0], "text": row[1]} for row in rows]
    return jsonify(history)

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

    # Сохраняем сообщение пользователя в БД
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("INSERT INTO messages (username, role, text) VALUES (?, ?, ?)", (user, 'user', user_message))
    conn.commit()
    conn.close()

    try:
        response = client.models.generate_content(
            model="gemini-3.5-flash-lite",
            contents=user_message,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())]
            )
        )
        reply_text = response.text if response.text else "Не удалось сформулировать ответ."
        
        # Сохраняем ответ бота в БД
        conn = sqlite3.connect('database.db')
        c = conn.cursor()
        c.execute("INSERT INTO messages (username, role, text) VALUES (?, ?, ?)", (user, 'bot', reply_text))
        conn.commit()
        conn.close()
        
        return jsonify({"reply": reply_text})
    except Exception as e:
        error_msg = f"Ошибка Gemini: {str(e)}"
        return jsonify({"reply": error_msg})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
