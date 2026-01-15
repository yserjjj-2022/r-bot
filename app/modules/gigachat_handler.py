# app/modules/gigachat_handler.py
# Версия 4.1: Добавлена настройка температуры генерации (AI_TEMPERATURE)

"""
=== ИНСТРУКЦИЯ ПО ВЫБОРУ МОДЕЛИ ===

Режимы работы (управляется через .env):

1. ОФИЦИАЛЬНЫЙ (COMPLIANCE_MODE=true):
   - Всегда используется GigaChat-2-Pro
   - Для официальных исследований с требованиями 152-ФЗ
   - Обработка данных на территории РФ
   - ACTIVE_MODEL игнорируется

2. ЭКСПЕРИМЕНТАЛЬНЫЙ (COMPLIANCE_MODE=false):
   - Используется модель из ACTIVE_MODEL
   - Для исследований поведения, тестов, playground
   - Можно свободно менять модели

Доступные модели (для ACTIVE_MODEL):
- deepseek-main    - основная рабочая (дешёвая, быстрая)
- deepseek-fast    - быстрая версия DeepSeek
- qwen-max         - лучшая для roleplay
- gigachat-pro     - для compliance (автоматически в официальном режиме)

Переменные окружения (.env):
- COMPLIANCE_MODE=true/false
- ACTIVE_MODEL=deepseek-main
- AI_TEMPERATURE=0.6 (0.0 - строгий робот, 1.0 - креатив/хаос)
- GIGACHAT_CREDENTIALS=...
- VSEGPT_API_KEY=sk-...
"""

import time
import traceback
from gigachat import GigaChat
from gigachat.models import Chat, Messages, MessagesRole
from decouple import config

# Попытка импорта openai для VseGPT
try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    print("⚠️ Библиотека openai не установлена. VseGPT модели недоступны.")

# === КОНФИГУРАЦИЯ ИЗ .ENV ===
# Безопасный дефолт: официальное исследование
COMPLIANCE_MODE = config("COMPLIANCE_MODE", default=True, cast=bool)
ACTIVE_MODEL = config("ACTIVE_MODEL", default="deepseek-main")
# Температура: 0.5-0.7 оптимум для ролеплея. Ниже - суше, выше - бред.
AI_TEMPERATURE = config("AI_TEMPERATURE", default=0.6, cast=float)

# === МОДЕЛИ ===
MODELS = {
    "deepseek-main": {
        "backend": "vsegpt",
        "model_id": "deepseek/deepseek-v3.2-alt",
        "description": "⭐ Основная: дешёвая, быстрая, качественная"
    },
    "deepseek-fast": {
        "backend": "vsegpt",
        "model_id": "deepseek/deepseek-v3.2-alt-faster",
        "description": "🚀 Быстрая версия DeepSeek"
    },
    "qwen-max": {
        "backend": "vsegpt",
        "model_id": "qwen/qwen-max",
        "description": "🎭 Лучшая для roleplay"
    },
    "gigachat-pro": {
        "backend": "gigachat",
        "model_id": "GigaChat-2-Pro",
        "description": "🛡️ Compliance (официальные исследования)"
    }
}

# === ИНИЦИАЛИЗАЦИЯ КЛИЕНТОВ ===

# GigaChat
gigachat_client = None
GIGACHAT_CREDENTIALS = config("GIGACHAT_CREDENTIALS", default="")
if GIGACHAT_CREDENTIALS:
    try:
        print("Инициализация клиента GigaChat...")
        gigachat_client = GigaChat(
            credentials=GIGACHAT_CREDENTIALS,
            verify_ssl_certs=False
        )
        print("-> GigaChat клиент готов")
    except Exception as e:
        print(f"!!! ОШИБКА инициализации GigaChat: {e}")
        traceback.print_exc()
        gigachat_client = None

# VseGPT (OpenAI-compatible)
vsegpt_client = None
if OPENAI_AVAILABLE:
    VSEGPT_API_KEY = config("VSEGPT_API_KEY", default="")
    if VSEGPT_API_KEY:
        try:
            print("Инициализация клиента VseGPT...")
            vsegpt_client = openai.OpenAI(
                api_key=VSEGPT_API_KEY,
                base_url="https://api.vsegpt.ru/v1"
            )
            print("-> VseGPT клиент готов")
        except Exception as e:
            print(f"!!! ОШИБКА инициализации VseGPT: {e}")
            traceback.print_exc()
            vsegpt_client = None

# === СТРАХОВКА: COMPLIANCE БЕЗ GIGACHAT = КРИТИЧЕСКАЯ ОШИБКА ===
if COMPLIANCE_MODE and not gigachat_client:
    raise RuntimeError(
        "🚨 КРИТИЧЕСКАЯ ОШИБКА: COMPLIANCE_MODE=true, но GigaChat не инициализирован!\n"
        "Проверьте переменную окружения GIGACHAT_CREDENTIALS.\n"
        "Старт приложения запрещён в официальном режиме без сертифицированного AI."
    )

# === БАННЕР РЕЖИМА (защита от ошибки оператора) ===
print("\n" + "=" * 72)
if COMPLIANCE_MODE:
    print("🛡️  R-BOT AI MODE: COMPLIANCE_MODE=TRUE (OFFICIAL RESEARCH)")
    print("    Provider locked: GigaChat only")
    print(f"    Temperature: {AI_TEMPERATURE}")
else:
    print("🔬 R-BOT AI MODE: COMPLIANCE_MODE=FALSE (EXPERIMENT)")
    print(f"    Selected model: {ACTIVE_MODEL}")
    print(f"    Temperature: {AI_TEMPERATURE}")
    print(f"    Description: {MODELS.get(ACTIVE_MODEL, {}).get('description', 'N/A')}")
print("=" * 72 + "\n")


def get_ai_response(user_message: str, system_prompt: str) -> str:
    """
    Отправляет запрос к AI с автоматическими повторами при сбоях.
    
    Args:
        user_message: сообщение пользователя
        system_prompt: системный промпт (роль, контекст)
    
    Returns:
        str: ответ AI или специальное сообщение об ошибке (начинается с ⚠️)
    """
    
    # Определяем модель с учётом compliance-режима
    if COMPLIANCE_MODE:
        selected_model = "gigachat-pro"
    else:
        selected_model = ACTIVE_MODEL
    
    config_model = MODELS[selected_model]
    backend = config_model["backend"]
    model_id = config_model["model_id"]
    
    MAX_RETRIES = 3
    
    for attempt in range(1, MAX_RETRIES + 1):
        start_time = time.time()
        
        try:
            print(f"[AI] Попытка {attempt}/{MAX_RETRIES} | {backend}/{model_id}")
            
            # Вызов бэкенда
            if backend == "gigachat":
                response = _call_gigachat(user_message, system_prompt, model_id)
            elif backend == "vsegpt":
                response = _call_vsegpt(user_message, system_prompt, model_id)
            else:
                raise ValueError(f"Неизвестный backend: {backend}")
            
            # Успех
            latency_ms = int((time.time() - start_time) * 1000)
            print(f"[AI] ✅ Успех за {latency_ms}ms на попытке {attempt}")
            return response
            
        except Exception as e:
            latency_ms = int((time.time() - start_time) * 1000)
            error_type = type(e).__name__
            is_retryable = _is_retryable_error(e)
            
            print(f"[AI] ❌ Ошибка на попытке {attempt}: {error_type}")
            
            # Если это последняя попытка ИЛИ ошибка непоправимая
            if attempt == MAX_RETRIES or not is_retryable:
                print(f"[AI] 🚫 Отказ после {attempt} попыток: {e}")
                
                # КРИТИЧНО: Если в compliance-режиме упал GigaChat → игра на паузу
                if COMPLIANCE_MODE:
                    return "⚠️ Сервис временно недоступен. Пожалуйста, попробуйте позже или обратитесь к администратору."
                else:
                    return ""
            
            # Экспоненциальная задержка перед следующей попыткой
            delay = 2 ** attempt
            print(f"[AI] 🔄 Повтор через {delay} сек...")
            time.sleep(delay)
    
    return "⚠️ Сервис временно недоступен."


def _call_gigachat(user_message: str, system_prompt: str, model_id: str) -> str:
    """Вызов GigaChat API"""
    if not gigachat_client:
        raise RuntimeError("GigaChat клиент не инициализирован")
    
    messages = [
        Messages(role=MessagesRole.SYSTEM, content=system_prompt),
        Messages(role=MessagesRole.USER, content=user_message)
    ]
    
    response = gigachat_client.chat(Chat(
        messages=messages,
        model=model_id,
        temperature=AI_TEMPERATURE  # NEW: Температура
    ))
    
    if response.choices and response.choices[0].message.content:
        return response.choices[0].message.content
    else:
        raise ValueError("GigaChat вернул пустой ответ")


def _call_vsegpt(user_message: str, system_prompt: str, model_id: str) -> str:
    """Вызов VseGPT API (OpenAI-compatible)"""
    if not vsegpt_client:
        raise RuntimeError("VseGPT клиент не инициализирован")
    
    response = vsegpt_client.chat.completions.create(
        model=model_id,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ],
        temperature=AI_TEMPERATURE  # NEW: Температура
    )
    
    if response.choices and response.choices[0].message.content:
        return response.choices[0].message.content
    else:
        raise ValueError("VseGPT вернул пустой ответ")


def _is_retryable_error(error: Exception) -> bool:
    """Определяет, стоит ли повторять запрос при данной ошибке"""
    error_str = str(error).lower()
    
    # Сетевые ошибки → retry
    if any(x in error_str for x in ["timeout", "connection", "network"]):
        return True
    
    # Rate limit → retry
    if "429" in error_str or "too many requests" in error_str:
        return True
    
    # Server errors → retry
    if any(x in error_str for x in ["500", "502", "503", "internal server error"]):
        return True
    
    # Auth/validation errors → НЕ retry
    if any(x in error_str for x in ["401", "403", "404", "400", "unauthorized", "invalid"]):
        return False
    
    # По умолчанию повторяем (осторожный подход)
    return True
