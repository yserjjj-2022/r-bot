# app/modules/gigachat_handler.py

import time
from gigachat import GigaChat
from gigachat.models import Chat, Messages, MessagesRole
from decouple import config

GIGACHAT_CREDENTIALS = config("GIGACHAT_CREDENTIALS", default=None)
GIGACHAT_MODEL = config("GIGACHAT_MODEL", default="GigaChat-Pro")

# ИЗМЕНЕНИЕ: Функция теперь принимает готовый системный промпт.
def get_ai_response(user_message: str, system_prompt: str) -> str:
    """
    Отправляет запрос в GigaChat, используя переданный системный промпт.
    """
    if not GIGACHAT_CREDENTIALS:
        return "Ошибка: Учетные данные для GigaChat не настроены."

    # Основная роль ИИ, которая всегда будет в начале
    base_role_prompt = (
        "Ты — бот-исследователь, ведешь опрос. Твой стиль общения — вежливый, внимательный и вдумчивый. "
        "Твоя главная задача — помогать респонденту лучше понять вопросы опроса. "
        "Если респондент задает вопросы, не связанные с темой опроса, мягко верни его к текущему вопросу.\n\n"
    )
    
    # Объединяем базовую роль с динамическим контекстом
    full_system_prompt = base_role_prompt + system_prompt

    max_retries = 3
    for attempt in range(max_retries):
        try:
            print(f"Попытка №{attempt + 1} отправить запрос в GigaChat с моделью: {GIGACHAT_MODEL}")

            with GigaChat(
                credentials=GIGACHAT_CREDENTIALS,
                model=GIGACHAT_MODEL,
                verify_ssl_certs=False
            ) as giga:
                
                # Формируем сообщения: сначала системный промпт, потом сообщение пользователя
                messages = [
                    Messages(role=MessagesRole.SYSTEM, content=full_system_prompt),
                    Messages(role=MessagesRole.USER, content=user_message)
                ]

                response = giga.chat(Chat(messages=messages))
                
                return response.choices[0].message.content

        except Exception as e:
            print(f"Произошла непредвиденная ошибка при обращении к GigaChat API: {e}")
            # При последней попытке возвращаем ошибку
            if attempt == max_retries - 1:
                return "К сожалению, мой помощник сейчас не в сети. Попробуйте позже."
            time.sleep((attempt + 1) * 2) # Ожидание перед повторной попыткой
            
    return "К сожалению, мой помощник сейчас не в сети после нескольких попыток."
