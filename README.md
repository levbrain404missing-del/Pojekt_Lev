# Орбита — школьный ИИ-помощник

Учебный сайт на Python и Flask по заданию учителя ([alexeykamalin/arch](https://github.com/alexeykamalin/arch)).
Внешний вид — свой дизайн «Орбита», логика — как в задании.

## Что умеет (как в задании)

| Адрес | Что делает |
|---|---|
| `/` | регистрация |
| `/login` | вход |
| `/profile` | личный кабинет: баланс, имя, email, чат с нейронкой, кнопки «Транзакции» и «Выйти» |
| `/transactions` | список транзакций пользователя |
| `/logout` | выход |
| `/api/user_register`, `/api/login`, `/api/chat` | те же действия в формате JSON |

- База данных — **MySQL из задания** (`sch688_vvedenie`), таблицы `users` и `transactions`. Сайт не создаёт своих таблиц.
- Нейросеть — **Qwen, работает прямо на компьютере** через `llama-cpp-python`. Интернет нужен только для первой загрузки модели.
- Страницы работают без JavaScript, пароли хранятся хешем.

## Запуск на компьютере (Windows)

Нужен **Python 3.12** с [python.org](https://www.python.org/downloads/) (при установке отметить «Add python.exe to PATH»).

```powershell
git clone https://github.com/levbrain404missing-del/Pojekt_Lev.git
cd Pojekt_Lev
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install llama-cpp-python --prefer-binary --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu
.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
notepad .env
```

В `.env` впишите `DB_PASSWORD` — пароль от базы из `app.py` задания. Сохраните файл и запустите сайт:

```powershell
.venv\Scripts\python.exe app.py
```

Откройте http://127.0.0.1:5000.

При первом запуске скачивается модель (~1 ГБ, несколько минут). В окне PowerShell появится «Модель успешно загружена.» — после этого чат отвечает.

### Если что-то не так

- **`llama-cpp-python` начинает компилироваться и падает с ошибкой** — готовой сборки для вашей версии Python нет. Либо поставьте Python 3.12, либо установите [Visual Studio Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/) с компонентом «Разработка классических приложений на C++» и повторите установку.
- **«Нет связи с базой данных»** — проверьте интернет и `DB_PASSWORD` в `.env`. Некоторые сети (школьный Wi-Fi) закрывают порт 3306 — попробуйте другую сеть.
- **Компьютер слабый (меньше 8 ГБ памяти)** — в `.env` поставьте модель из задания:
  ```
  MODEL_REPO=bartowski/Qwen2.5-0.5B-Instruct-GGUF
  MODEL_FILE=Qwen2.5-0.5B-Instruct-Q4_K_M.gguf
  ```
- **Хочется умнее** (16 ГБ памяти и больше): `bartowski/Qwen2.5-3B-Instruct-GGUF` и `Qwen2.5-3B-Instruct-Q4_K_M.gguf`.

## Структура

- `app.py` — запуск сайта;
- `school_app/web.py` — страницы и API;
- `school_app/database.py` — подключение к MySQL;
- `school_app/ai_client.py` — нейросеть Qwen;
- `school_app/templates` — HTML;
- `school_app/static` — оформление.
