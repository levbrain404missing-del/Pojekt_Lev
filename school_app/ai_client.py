"""Локальная нейросеть Qwen через llama-cpp-python, как в задании.

Модель скачивается с Hugging Face при первом запуске и дальше берётся из кэша.
Модель загружается один раз; запросы обрабатываются по очереди.
"""
import threading
from pathlib import Path

SYSTEM_PROMPT = 'Ты полезный ассистент. Отвечай кратко и по-русски.'

_llm = None
_load_error = None
_lock = threading.Lock()


class AIError(Exception):
    pass


def _load(config):
    global _llm, _load_error
    if _llm is not None:
        return _llm
    try:
        from llama_cpp import Llama
    except ImportError:
        raise AIError('Не установлен llama-cpp-python. Выполните установку из README.') from None
    path = config.get('MODEL_PATH')
    try:
        if path and Path(path).is_file():
            print(f'Загрузка модели из файла {path}...')
            _llm = Llama(model_path=path, n_ctx=config['MODEL_CTX'], verbose=False)
        else:
            print(f"Загрузка модели {config['MODEL_FILE']} из {config['MODEL_REPO']}...")
            _llm = Llama.from_pretrained(repo_id=config['MODEL_REPO'], filename=config['MODEL_FILE'],
                                         n_ctx=config['MODEL_CTX'], verbose=False)
    except Exception as exc:
        _load_error = str(exc)
        print(f'Не удалось загрузить модель: {exc}')
        raise AIError('Не удалось загрузить нейросеть. Подробности в окне, где запущен сайт.') from None
    _load_error = None
    print('Модель успешно загружена.')
    return _llm


def warm_up(config):
    """Загружает модель заранее, чтобы первый вопрос не ждал."""
    try:
        with _lock:
            _load(config)
    except AIError:
        pass


def ready():
    return _llm is not None


def ask(config, message):
    with _lock:
        llm = _load(config)
        try:
            output = llm.create_chat_completion(
                messages=[{'role': 'system', 'content': SYSTEM_PROMPT},
                          {'role': 'user', 'content': message}],
                max_tokens=config['MODEL_MAX_TOKENS'],
                temperature=0.7,
            )
        except Exception as exc:
            print(f'Ошибка нейросети: {exc}')
            raise AIError('Нейросеть не смогла ответить. Попробуйте ещё раз.') from None
    reply = (output['choices'][0]['message'].get('content') or '').strip()
    if not reply:
        raise AIError('Нейросеть вернула пустой ответ.')
    return reply
