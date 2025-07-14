# app/modules/gigachat_handler.py (Версия 2.0 с однократной инициализацией и надежной обработкой ошибок)

import time
from gigachat import GigaChat
from gigachat.models import Chat, Messages, MessagesRole
from decouple import config
import traceback

# --- ГЛАВНОЕ ИЗМЕНЕНИЕ: Однократная инициализация клиента GigaChat ---
# Мы создаем клиент один раз при загрузке этого модуля.
# Это значительно повышает производительность.

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
    # Оставляем chat = None, чтобы функция get_ai_response знала о проблеме


def get_ai_response(user_message: str, system_prompt: str) -> str:
    """
    Отправляет запрос в GigaChat, используя переданный системный промпт.
    Возвращает текст ответа или пустую строку в случае ошибки.
    """
    # Проверяем, был ли клиент успешно инициализирован при старте
    if not chat:
        print("Ошибка вызова: Попытка использовать GigaChat, но клиент не был инициализирован.")
        return "" # Возвращаем пустую строку, telegram_handler обработает это

    # Основная роль ИИ, которая всегда будет в начале
    base_role_prompt = (
        "Ты — AI-ассистент. Твоя основная роль — исследователь. Веди диалог нейтрально."
        "Твоя главная задача в роли исследователя — помогать респонденту лучше понять предложенные ему вопросы."
        "ОДНАКО, если пользователь прямо просит совета, консультации или помощи в выборе ('что выбрать?', 'помоги', 'дай совет'), ты должен немедленно переключиться на роль финансового консультанта."
        "Твоя главная задача в роли финансового косультанта - проанализировать всю предоставленную историю ответов и текущее состояние счета, оценить риски и дать пользователю развернутую, аргументированную рекомендацию."
        "Рекомендация должна быть размером до 150 слов."
        "После ответа вернись к роли исследователя.\n\n"
    )
    
    full_system_prompt = base_role_prompt + system_prompt

    messages = [
        Messages(role=MessagesRole.SYSTEM, content=full_system_prompt),
        Messages(role=MessagesRole.USER, content=user_message)
    ]

    max_retries = 3
    for attempt in range(max_retries):
        try:
            print(f"Попытка №{attempt + 1} отправить запрос в GigaChat...")
            
            # Используем уже созданный клиент 'chat'.
            # Больше нет необходимости создавать его каждый раз в 'with' блоке.
            response = chat.chat(Chat(messages=messages))
            
            # Убеждаемся, что в ответе есть контент
            if response.choices and response.choices[0].message.content:
                return response.choices[0].message.content
            else:
                print("-> GigaChat вернул пустой ответ.")
                return ""

        except Exception as e:
            print(f"!!! ОШИБКА на попытке №{attempt + 1} при обращении к GigaChat API: {e}")
            if attempt == max_retries - 1:
                print("!!! Достигнуто максимальное количество попыток. Возвращаем пустую строку.")
                traceback.print_exc() # Печатаем полную ошибку в лог для анализа
                return "" # Сигнализируем об ошибке пустой строкой
            time.sleep((attempt + 1) * 2) # Экспоненциальная задержка перед повторной попыткой
            
    # Если цикл завершился без успешного ответа
    return ""
