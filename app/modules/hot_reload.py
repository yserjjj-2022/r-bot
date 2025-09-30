# app/modules/hot_reload.py
"""
Модуль автоматического обновления сценария без перезапуска приложения.
Отслеживает изменения файла graph_data и обновляет глобальные переменные.
"""

import os
import json
import threading
import time
from typing import Optional, Callable

# Глобальные переменные для сценария (будут обновляться автоматически)
graph_data: Optional[dict] = None
current_graph_path: Optional[str] = None

def load_graph_from_file(filepath: str) -> dict:
    """Загружает JSON-сценарий из файла."""
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)

def reload_graph_data(filepath: str):
    """
    Обновляет глобальную переменную graph_data из файла.
    В случае ошибки сохраняет предыдущую версию.
    """
    global graph_data
    try:
        new_graph = load_graph_from_file(filepath)
        graph_data = new_graph
        print(f"[HOT-RELOAD] ✅ Сценарий успешно обновлен из {filepath}")
        print(f"[HOT-RELOAD] Загружено узлов: {len(graph_data) if graph_data else 0}")
    except Exception as e:
        print(f"[HOT-RELOAD] ❌ Ошибка обновления сценария: {e}")
        print(f"[HOT-RELOAD] Сохраняется предыдущая версия сценария.")

def watch_graph_file(filepath: str, poll_interval: int = 30):
    """
    Фоновый мониторинг файла сценария.
    Проверяет изменения каждые poll_interval секунд.
    """
    try:
        last_mtime = os.path.getmtime(filepath)
        print(f"[HOT-RELOAD] Начальное время модификации файла: {last_mtime}")
    except FileNotFoundError:
        print(f"[HOT-RELOAD] ⚠️ Файл {filepath} не найден при запуске watcher")
        last_mtime = 0

    while True:
        time.sleep(poll_interval)
        try:
            current_mtime = os.path.getmtime(filepath)
            if current_mtime > last_mtime:
                print(f"[HOT-RELOAD] 🔄 Обнаружено изменение файла! Время: {current_mtime}")
                reload_graph_data(filepath)
                last_mtime = current_mtime
        except FileNotFoundError:
            print(f"[HOT-RELOAD] ⚠️ Файл {filepath} исчез из системы")
        except Exception as e:
            print(f"[HOT-RELOAD] ❌ Ошибка мониторинга: {e}")

def start_hot_reload(filepath: str, poll_interval: int = 30) -> threading.Thread:
    """
    Запускает систему автообновления сценария:
    1. Загружает сценарий сразу при старте
    2. Запускает фоновый watcher для отслеживания изменений
    
    Args:
        filepath: путь к файлу сценария
        poll_interval: интервал проверки в секундах (по умолчанию 30)
    
    Returns:
        threading.Thread: объект потока watcher (для отладки)
    """
    global current_graph_path
    current_graph_path = filepath
    
    print(f"[HOT-RELOAD] 🚀 Запуск системы автообновления сценария")
    print(f"[HOT-RELOAD] Файл: {filepath}")
    print(f"[HOT-RELOAD] Интервал проверки: {poll_interval} секунд")
    
    # Первичная загрузка
    reload_graph_data(filepath)
    
    # Запуск фонового мониторинга
    watcher_thread = threading.Thread(
        target=watch_graph_file,
        args=(filepath, poll_interval),
        daemon=True,
        name="GraphDataWatcher"
    )
    watcher_thread.start()
    
    print(f"[HOT-RELOAD] ✅ Watcher запущен в фоновом режиме")
    return watcher_thread

def get_current_graph() -> Optional[dict]:
    """Возвращает актуальную версию graph_data."""
    return graph_data
