"""Подключение к MySQL из задания: база sch688_vvedenie, таблицы users и transactions.

Свои таблицы сайт не создаёт: все запросы идут только к этим двум таблицам.
"""
import mysql.connector
from flask import current_app, g


def connect():
    """То же подключение, что в задании, но параметры берутся из .env."""
    c = current_app.config
    return mysql.connector.connect(
        host=c['DB_HOST'],
        port=c['DB_PORT'],
        database=c['DB_NAME'],
        user=c['DB_USER'],
        password=c['DB_PASSWORD'],
        connection_timeout=10,
    )


def get_db():
    if 'db' not in g:
        g.db = connect()
    return g.db


def query_one(sql, params=()):
    cur = get_db().cursor(dictionary=True)
    try:
        cur.execute(sql, params)
        return cur.fetchone()
    finally:
        cur.close()


def query_all(sql, params=()):
    cur = get_db().cursor(dictionary=True)
    try:
        cur.execute(sql, params)
        return cur.fetchall()
    finally:
        cur.close()


def execute(sql, params=()):
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute(sql, params)
        db.commit()
        return cur.lastrowid
    finally:
        cur.close()


def init_db(app):
    @app.teardown_appcontext
    def close_db(error=None):
        db = g.pop('db', None)
        if db is not None:
            db.close()
