"""Проверка связи с базой: python check_db.py — показывает колонки users и transactions."""
import sys
from dotenv import dotenv_values
import os
import mysql.connector

env = {**dotenv_values('.env'), **os.environ}
try:
    cnx = mysql.connector.connect(
        host=env.get('DB_HOST', '185.114.247.43'), port=int(env.get('DB_PORT') or 3306),
        database=env.get('DB_NAME', 'sch688_vvedenie'), user=env.get('DB_USER', 'sch688_vvedenie'),
        password=env.get('DB_PASSWORD', ''), connection_timeout=10)
except Exception as exc:
    print('НЕТ СВЯЗИ С БАЗОЙ:', exc)
    sys.exit(1)
print('Связь с базой есть.\n')
cur = cnx.cursor()
for table in ('users', 'transactions'):
    print(f'== {table}')
    try:
        cur.execute(f'SHOW CREATE TABLE `{table}`')
        print(cur.fetchone()[1], '\n')
    except Exception as exc:
        print('  ошибка:', exc, '\n')
cnx.close()
