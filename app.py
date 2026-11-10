"""Орбита — сайт по заданию: Flask + MySQL из задания + локальная нейросеть Qwen."""
import os
from waitress import serve
from school_app.web import create_app

app = create_app('orbit')

if __name__ == '__main__':
    host, port = os.getenv('HOST', '127.0.0.1'), int(os.getenv('PORT', '5000'))
    print(f'Сайт запущен: http://{host}:{port}')
    serve(app, host=host, port=port, threads=4, channel_timeout=300)
