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
    # Пользователи
    c.execute('''CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT)''')
    # Чаты (id, кто владелец, название)
    c.execute('''CREATE TABLE IF NOT EXISTS chats (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, title TEXT)''')
    # Сообщения (привязаны к chat_id)
    c.execute('''CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER, username TEXT, role TEXT, text TEXT)''')
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
        # Сразу создаем первый чат для нового пользователя
        c.execute("INSERT INTO chats (username, title) VALUES (?, ?)", (user, "Чат 1"))
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

# --- API ДЛЯ ЧАТОВ ---

@app.route('/chats', methods=['GET', 'POST'])
def handle_chats():
    if not session.get('logged_in'):
        return jsonify({"error": "Доступ запрещён"}), 403
    user = session.get('username')
    conn = sqlite3.connect('database.db')
    c = conn.cursor()

    if request.method == 'GET':
        c.execute("SELECT id, title FROM chats WHERE username=? ORDER BY id ASC", (user,))
        rows = c.fetchall()
        
        # Если у старого пользователя нет чатов, создаем ему "Чат 1"
        if not rows:
            c.execute("INSERT INTO chats (username, title) VALUES (?, ?)", (user, "Чат 1"))
            conn.commit()
            rows = [(c.lastrowid, "Чат 1")]
            
        conn.close()
        return jsonify([{"id": row[0], "title": row[1]} for row in rows])
    
    elif request.method == 'POST':
        c.execute("INSERT INTO chats (username, title) VALUES (?, ?)", (user, "Новый чат"))
        chat_id = c.lastrowid
        conn.commit()
        conn.close()
        return jsonify({"id": chat_id, "title": "Новый чат"})

@app.route('/history/<int:chat_id>', methods=['GET'])
def get_history(chat_id):
    if not session.get('logged_in'):
        return jsonify([])
    user = session.get('username')
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("SELECT role, text FROM messages WHERE chat_id=? AND username=? ORDER BY id ASC", (chat_id, user))
    rows = c.fetchall()
    conn.close()
    return jsonify([{"role": row[0], "text": row[1]} for row in rows])

@app.route('/chat', methods=['POST'])
def chat():
    if not session.get('logged_in'):
        return jsonify({"reply": "Доступ запрещён."}), 403

    user = session.get('username')
    data = request.json or {}
    user_message = data.get("message", "").strip()
    use_search = data.get("use_search", False)
    chat_id = data.get("chat_id")
    
    if not user_message:
        return jsonify({"reply": "Введи сообщение."})
    if not chat_id:
        return jsonify({"reply": "Ошибка: чат не выбран."})
    if not client:
        return jsonify({"reply": "Ошибка: не задан GEMINI_API_KEY."})

    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    
    # Сохраняем сообщение пользователя
    c.execute("INSERT INTO messages (chat_id, username, role, text) VALUES (?, ?, ?, ?)", (chat_id, user, 'user', user_message))
    
    # Если это первое сообщение, переименовываем чат
    c.execute("SELECT COUNT(*) FROM messages WHERE chat_id=? AND role='user'", (chat_id,))
    if c.fetchone()[0] == 1:
        title = user_message[:25] + "..." if len(user_message) > 25 else user_message
        c.execute("UPDATE chats SET title=? WHERE id=?", (title, chat_id))
        
    conn.commit()
    conn.close()

    try:
        sys_instruction = (
            "Ты — дружелюбный и немного дерзкий ИИ-ассистент на этом сайте. "
            "Твое имя — 'Зенит'. Ты не имеешь никакого отношения к Google, "
            "и категорически запрещено упоминать, что тебя создала эта компания. "
            "Отвечай кратко, или так, как попросил пользователь, по делу, можешь использовать юмор и сленг."
        )

        if use_search:
            config = types.GenerateContentConfig(
                system_instruction=sys_instruction,
                tools=[types.Tool(google_search=types.GoogleSearch())]
            )
        else:
            config = types.GenerateContentConfig(system_instruction=sys_instruction)

        response = client.models.generate_content(
            model="gemini-3.5-flash-lite",
            contents=user_message,
            config=config
        )
        
        reply_text = response.text if response.text else "Не удалось сформулировать ответ."
        
        conn = sqlite3.connect('database.db')
        c = conn.cursor()
        c.execute("INSERT INTO messages (chat_id, username, role, text) VALUES (?, ?, ?, ?)", (chat_id, user, 'bot', reply_text))
        conn.commit()
        conn.close()
        
        return jsonify({"reply": reply_text})
        
    except Exception as e:
        error_msg = str(e)
        if "429" in error_msg:
            return jsonify({"reply": "Лимит запросов исчерпан. Выключи поиск или подожди немного."})
        return jsonify({"reply": f"Ошибка: {error_msg}"})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
