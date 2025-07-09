# app/modules/state_calculator.py
# Модуль для безопасного вычисления новых состояний пользователя.

import random

# Определяем "безопасное" окружение для функции eval().
# Это защита, чтобы в формулах нельзя было выполнить вредоносный код.
SAFE_GLOBALS = {
    'random': random,
    '__builtins__': {
        'abs': abs, 
        'max': max, 
        'min': min, 
        'round': round,
        'int': int,
        'float': float
    }
}

def calculate_new_state(formula: str, current_state: dict) -> any:
    """
    Безопасно выполняет строку-формулу, подставляя в нее текущие значения 
    состояний пользователя из словаря current_state.

    Пример:
    formula = "score + random.choice([20, -20])"
    current_state = {'score': 100}
    Результат может быть 120 или 80.
    """
    if not isinstance(current_state, dict):
        raise TypeError("current_state должен быть словарем.")

    try:
        # eval выполняет строку как код Python.
        # SAFE_GLOBALS ограничивает доступные функции.
        # current_state предоставляет переменные (например, 'score').
        new_value = eval(formula, SAFE_GLOBALS, current_state)
        return new_value
    except Exception as e:
        print(f"!!! ОШИБКА при вычислении формулы '{formula}': {e} !!!")
        # В случае ошибки возвращаем None, чтобы обработчик мог это отловить.
        return None
