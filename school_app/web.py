"""Сайт по заданию учителя (репозиторий alexeykamalin/arch), оформление «Орбита».

Как в задании:
  /                   — регистрация
  /login              — вход
  /profile            — личный кабинет: баланс, имя, email, чат с нейросетью, выход
  /transactions       — транзакции пользователя
  /logout             — выход (POST)
  /api/user_register  — регистрация (JSON)
  /api/login          — вход (JSON)
  /api/chat           — вопрос нейросети (JSON)

База — MySQL из задания (таблицы users и transactions), нейросеть — локальная Qwen.
Страницы работают без JavaScript: формы отправляются обычным POST.
"""
import os
import re
import secrets
import threading
import time
from collections import defaultdict, deque
from pathlib import Path

import mysql.connector
from dotenv import dotenv_values
from flask import Flask, abort, flash, g, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from school_app import ai_client
from school_app.database import execute, init_db, query_all, query_one

THEMES = {
    'orbit': {'BRAND': 'Орбита', 'TAGLINE': 'Большие идеи начинаются с вопроса.',
              'DESCRIPTION': 'Твой помощник в мире знаний. Разбирай сложное, находи идеи и изучай новое вместе с нейросетью.'},
    'pulse': {'BRAND': 'Пульс', 'TAGLINE': 'Дай своим идеям новый импульс.',
              'DESCRIPTION': 'Пространство для любопытства. Задавай вопросы, исследуй темы и находи свой следующий шаг.'},
}

# Модель по умолчанию. В задании — Qwen2.5-0.5B; 1.5B заметно лучше пишет по-русски.
DEFAULT_MODEL_REPO = 'bartowski/Qwen2.5-1.5B-Instruct-GGUF'
DEFAULT_MODEL_FILE = 'Qwen2.5-1.5B-Instruct-Q4_K_M.gguf'

EMAIL_RE = re.compile(r'[^\s@]+@[^\s@]+\.[^\s@]+')
HASH_PREFIXES = ('scrypt:', 'pbkdf2:')


def check_password(stored, password):
    """Пароли сайта хранятся хешем. Записи, сделанные версией из задания, хранят пароль как есть."""
    stored = stored or ''
    if stored.startswith(HASH_PREFIXES):
        return check_password_hash(stored, password)
    return secrets.compare_digest(stored.encode(), password.encode())


def create_app(theme='orbit', config=None):
    root = Path(__file__).resolve().parent
    project = root.parent
    instance = Path((config or {}).get('INSTANCE_PATH', project / 'instance'))
    instance.mkdir(parents=True, exist_ok=True)
    settings = {**dotenv_values(project / '.env'), **os.environ}
    secret = settings.get('SECRET_KEY')
    if not secret:
        secret_file = instance / 'session.key'
        try:
            with secret_file.open('x', encoding='utf-8') as stream:
                stream.write(secrets.token_hex(32))
        except FileExistsError:
            pass
        secret = secret_file.read_text(encoding='utf-8')

    app = Flask(__name__, template_folder=str(root / 'templates'), static_folder=str(root / 'static'))
    app.config.update(
        SECRET_KEY=secret, THEME=theme, MAX_CONTENT_LENGTH=32 * 1024,
        SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_NAME=f'{theme}_session',
        SESSION_COOKIE_SAMESITE='Lax', SESSION_COOKIE_SECURE=settings.get('COOKIE_SECURE') == '1',
        DB_HOST=settings.get('DB_HOST', '185.114.247.43'),
        DB_PORT=int(settings.get('DB_PORT') or '3306'),
        DB_NAME=settings.get('DB_NAME', 'sch688_vvedenie'),
        DB_USER=settings.get('DB_USER', 'sch688_vvedenie'),
        DB_PASSWORD=settings.get('DB_PASSWORD', ''),
        MODEL_REPO=settings.get('MODEL_REPO') or DEFAULT_MODEL_REPO,
        MODEL_FILE=settings.get('MODEL_FILE') or DEFAULT_MODEL_FILE,
        MODEL_PATH=settings.get('MODEL_PATH', ''),
        MODEL_CTX=int(settings.get('MODEL_CTX') or '2048'),
        MODEL_MAX_TOKENS=int(settings.get('MODEL_MAX_TOKENS') or '300'),
        PRELOAD_MODEL=settings.get('PRELOAD_MODEL', '1') == '1',
        **THEMES[theme],
    )
    if config:
        app.config.update(config)
    init_db(app)

    # Ограничение попыток и история чата хранятся в памяти: в базе задания для них нет таблиц.
    attempts = defaultdict(deque)
    histories = defaultdict(lambda: deque(maxlen=20))
    memory_lock = threading.Lock()

    def limited(key, maximum=20, seconds=900):
        now = time.time()
        with memory_lock:
            bucket = attempts[key]
            while bucket and bucket[0] < now - seconds:
                bucket.popleft()
            bucket.append(now)
            return len(bucket) > maximum

    def remember(user_id, prompt, answer):
        with memory_lock:
            histories[user_id].append({'prompt': prompt, 'answer': answer,
                                       'created_at': time.strftime('%d.%m.%Y %H:%M')})

    # ---------- общие проверки ----------

    @app.before_request
    def protect_forms():
        session.setdefault('csrf', secrets.token_urlsafe(32))
        if request.method == 'POST':
            if request.path.startswith('/api/'):
                # JSON нельзя отправить с чужого сайта без разрешения браузера.
                if not request.is_json:
                    abort(415)
            elif not secrets.compare_digest(session['csrf'].encode(), request.form.get('csrf', '').encode()):
                abort(400)
        g.user_id = session.get('user_id')

    @app.after_request
    def security_headers(response):
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'none'; style-src 'self'; img-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['Cache-Control'] = 'no-store'
        return response

    @app.context_processor
    def template_context():
        return {'brand': app.config['BRAND'], 'theme': theme,
                'tagline': app.config['TAGLINE'], 'description': app.config['DESCRIPTION']}

    # ---------- логика из задания ----------

    def register_user(name, email, password):
        """Возвращает текст ошибки или None. SQL — как в задании."""
        name, email = (name or '').strip(), (email or '').strip().lower()
        password = password or ''
        if not 2 <= len(name) <= 60:
            return 'Введите имя длиной от 2 до 60 символов.'
        if len(email) > 254 or not EMAIL_RE.fullmatch(email):
            return 'Введите корректный адрес электронной почты.'
        if not 8 <= len(password) <= 128:
            return 'Пароль должен содержать от 8 до 128 символов.'
        if query_one('SELECT id FROM users WHERE email = %s', (email,)):
            return 'пользователь с таким email уже существует'
        try:
            execute('INSERT INTO `users`(`username`, `email`, `password_hash`) VALUES (%s, %s, %s)',
                    (name, email, generate_password_hash(password, method='pbkdf2:sha256')))
        except mysql.connector.IntegrityError:
            return 'пользователь с таким email уже существует'
        return None

    def find_user(email, password):
        user = query_one('SELECT id, username, email, password_hash FROM users WHERE email = %s',
                         ((email or '').strip().lower(),))
        if not user or not check_password(user['password_hash'], password or ''):
            return None
        return user

    def start_session(user):
        session.clear()
        session.update(user_id=user['id'], username=user['username'], csrf=secrets.token_urlsafe(32))

    def current_user():
        if not g.user_id:
            return None
        return query_one('SELECT id, username, email, balance FROM users WHERE id = %s', (g.user_id,))

    def auth_page(mode, status=200):
        return render_template('auth.html', mode=mode), status

    # ---------- страницы ----------

    @app.get('/')
    def registration():
        if g.user_id:
            return redirect(url_for('profile_page'))
        return auth_page('register')

    @app.post('/user_register')
    def user_register():
        if limited('register:' + (request.remote_addr or '')):
            abort(429)
        error = None
        if request.form.get('password', '') != request.form.get('confirm_password', ''):
            error = 'Пароли не совпадают.'
        error = error or register_user(request.form.get('fullname'), request.form.get('email'),
                                       request.form.get('password'))
        if error:
            flash(error, 'error')
            return auth_page('register', 400)
        flash('Аккаунт создан. Теперь войдите.', 'success')
        return redirect(url_for('login_page'))

    @app.route('/login', methods=['GET', 'POST'])
    def login_page():
        if request.method == 'POST':
            if limited('login:' + (request.remote_addr or '')):
                abort(429)
            user = find_user(request.form.get('email'), request.form.get('password'))
            if user:
                start_session(user)
                return redirect(url_for('profile_page'))
            flash('неверный email или пароль', 'error')
            return auth_page('login', 400)
        if g.user_id:
            return redirect(url_for('profile_page'))
        return auth_page('login')

    @app.get('/profile')
    def profile_page():
        if not g.user_id:
            return redirect(url_for('login_page'))
        user = current_user()
        if not user:
            session.clear()
            return redirect(url_for('login_page'))
        with memory_lock:
            messages = list(histories[user['id']])
        return render_template('profile.html', user=user, messages=messages, model_ready=ai_client.ready())

    @app.post('/chat')
    def chat():
        if not g.user_id:
            return redirect(url_for('login_page'))
        message = request.form.get('message', '').strip()
        if not 1 <= len(message) <= 2000:
            flash('Введите вопрос длиной от 1 до 2000 символов.', 'error')
        else:
            try:
                remember(g.user_id, message, ai_client.ask(app.config, message))
            except ai_client.AIError as exc:
                flash(str(exc), 'error')
        return redirect(url_for('profile_page') + '#chat')

    @app.get('/transactions')
    def transactions_page():
        if not g.user_id:
            return redirect(url_for('login_page'))
        transactions = query_all(
            '''SELECT id, amount, type, cost, description, balance_after, created_at
               FROM transactions
               WHERE user_id = %s
               ORDER BY created_at DESC, id DESC''',
            (g.user_id,))
        return render_template('transactions.html', transactions=transactions)

    @app.post('/logout')
    def logout():
        session.clear()
        return redirect(url_for('login_page'))

    # ---------- API, как в задании ----------

    @app.post('/api/user_register')
    def api_user_register():
        if limited('register:' + (request.remote_addr or '')):
            return jsonify({'error': 'слишком много попыток'}), 429
        req = request.get_json(silent=True) or {}
        error = register_user(req.get('name'), req.get('email'), req.get('password'))
        if error:
            return jsonify({'error': error})
        return jsonify({'ok': True})

    @app.post('/api/login')
    def api_login():
        if limited('login:' + (request.remote_addr or '')):
            return jsonify({'error': 'слишком много попыток'}), 429
        req = request.get_json(silent=True) or {}
        user = find_user(req.get('email'), req.get('password'))
        if not user:
            return jsonify({'error': 'неверный email или пароль'})
        start_session(user)
        return jsonify({'id': user['id'], 'username': user['username'], 'email': user['email']})

    @app.post('/api/chat')
    def api_chat():
        if 'user_id' not in session:
            return jsonify({'error': 'не авторизован'}), 401
        req = request.get_json(silent=True) or {}
        message = (req.get('message') or '').strip()
        if not message:
            return jsonify({'error': 'пустое сообщение'}), 400
        if len(message) > 2000:
            return jsonify({'error': 'слишком длинное сообщение'}), 400
        try:
            reply = ai_client.ask(app.config, message)
        except ai_client.AIError as exc:
            return jsonify({'error': str(exc)}), 503
        remember(session['user_id'], message, reply)
        return jsonify({'reply': reply})

    # ---------- ошибки ----------

    @app.errorhandler(mysql.connector.Error)
    def database_error(error):
        app.logger.warning('Ошибка базы данных: %s', error)
        return render_template('error.html', code=503,
                               message='Нет связи с базой данных. Проверьте интернет и настройки DB_* в файле .env.'), 503

    @app.errorhandler(400)
    @app.errorhandler(404)
    @app.errorhandler(413)
    @app.errorhandler(415)
    @app.errorhandler(429)
    def error_page(error):
        descriptions = {400: 'Форма устарела. Обновите страницу и попробуйте ещё раз.', 404: 'Такой страницы нет.',
                        413: 'Отправленная форма слишком большая.', 415: 'Неверный формат запроса.',
                        429: 'Слишком много попыток. Попробуйте через 15 минут.'}
        return render_template('error.html', code=error.code, message=descriptions[error.code]), error.code

    if app.config['PRELOAD_MODEL'] and not app.testing:
        threading.Thread(target=ai_client.warm_up, args=(app.config,), daemon=True).start()

    return app
