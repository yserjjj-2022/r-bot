# app/modules/state_calculator.py
# Исправлена проблема с рандомом

import random
import time

# Инициализируем генератор случайных чисел с текущим временем
random.seed(int(time.time() * 1000000) % 1000000)

# Определяем "безопасное" окружение для функции eval().
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
    """
    if not isinstance(current_state, dict):
        raise TypeError("current_state должен быть словарем.")

    try:
        # Обновляем seed перед каждым вычислением для истинной случайности
        random.seed()
        
        # eval выполняет строку как код Python.
        new_value = eval(formula, SAFE_GLOBALS, current_state)
        print(f"--- [ФОРМУЛА] '{formula}' = {new_value} (из состояния {current_state}) ---")
        return new_value
    except Exception as e:
        print(f"!!! ОШИБКА при вычислении формулы '{formula}': {e} !!!")
        return None
