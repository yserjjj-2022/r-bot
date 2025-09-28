# app/modules/gigachat_handler.py
# Версия 3.0: Убрана дублирующая роль, вся логика промптов в crud.py

import time
from gigachat import GigaChat
from gigachat.models import Chat, Messages, MessagesRole
from decouple import config
import traceback

# --- Однократная инициализация клиента GigaChat ---
chat = None
try:
    GIGACHAT_CREDENTIALS = config("GIGACHAT_CREDENTIALS")
    GIGACHAT_MODEL = config("GIGACHAT_MODEL", default="GigaChat-Pro")
    
    if GIGACHAT_CREDENTIALS:
        print("Инициализация клиента GigaChat...")
        chat = GigaChat(
            credentials=GIGACHAT_CREDENTIALS,
            model=GIGACHAT_MODEL,
            verify_ssl_certs=False
        )
        print("-> Клиент GigaChat успешно инициализирован.")
    else:
        print("!!! ПРЕДУПРЕЖДЕНИЕ: Переменная GIGACHAT_CREDENTIALS не найдена. AI-ассистент будет недоступен.")

except Exception as e:
    print("!!! КРИТИЧЕСКАЯ ОШИБКА при инициализации клиента GigaChat !!!")
    traceback.print_exc()
    chat = None

def get_ai_response(user_message: str, system_prompt: str) -> str:
    """
    Отправляет запрос в GigaChat, используя готовый системный промпт.
    Возвращает текст ответа или пустую строку в случае ошибки.
    """
    # Проверяем, был ли клиент успешно инициализирован при старте
    if not chat:
        print("Ошибка вызова: Попытка использовать GigaChat, но клиент не был инициализирован.")
        return ""

    # --- УБРАНО: base_role_prompt больше не нужен ---
    # Используем system_prompt как есть - вся логика ролей теперь в crud.py
    
    messages = [
        Messages(role=MessagesRole.SYSTEM, content=system_prompt),
        Messages(role=MessagesRole.USER, content=user_message)
    ]

    max_retries = 3
    for attempt in range(max_retries):
        try:
            print(f"Попытка №{attempt + 1} отправить запрос в GigaChat...")
            
            response = chat.chat(Chat(messages=messages))
            
            if response.choices and response.choices[0].message.content:
                return response.choices[0].message.content
            else:
                print("-> GigaChat вернул пустой ответ.")
                return ""

        except Exception as e:
            print(f"!!! ОШИБКА на попытке №{attempt + 1} при обращении к GigaChat API: {e}")
            if attempt == max_retries - 1:
                print("!!! Достигнуто максимальное количество попыток. Возвращаем пустую строку.")
                traceback.print_exc()
                return ""
            time.sleep((attempt + 1) * 2)
            
    return ""
