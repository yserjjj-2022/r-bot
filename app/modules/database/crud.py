# app/modules/database/crud.py

from sqlalchemy.orm import Session
from . import models
from datetime import datetime

def get_or_create_user(db: Session, telegram_id: int):
    """
    Находит пользователя по telegram_id или создает нового, если он не найден.
    """
    user = db.query(models.User).filter(models.User.telegram_id == str(telegram_id)).first()
    if not user:
        user = models.User(telegram_id=str(telegram_id))
        db.add(user)
        db.commit()
        db.refresh(user)
    return user

def create_session(db: Session, user_id: int, graph_id: str):
    """
    Создает новую сессию опроса для пользователя.
    """
    session = models.Session(user_id=user_id, graph_id=graph_id)
    db.add(session)
    db.commit()
    db.refresh(session)
    return session

def create_response(db: Session, session_id: int, node_id: str, answer_text: str):
    """
    Записывает ответ пользователя (нажатие кнопки) в базу данных.
    """
    response = models.Response(session_id=session_id, node_id=node_id, answer_text=answer_text)
    db.add(response)
    db.commit()
    db.refresh(response)
    return response

def create_ai_dialogue(db: Session, session_id: int, node_id: str, user_message: str, ai_response: str):
    """
    Записывает диалог с ИИ в базу данных.
    """
    dialogue = models.AIDialogue(session_id=session_id, node_id=node_id, user_message=user_message, ai_response=ai_response)
    db.add(dialogue)
    db.commit()
    db.refresh(dialogue)
    return dialogue

def end_session(db: Session, session_id: int):
    """
    Проставляет время окончания сессии.
    """
    session = db.query(models.Session).filter(models.Session.id == session_id).first()
    if session:
        session.end_time = datetime.utcnow()
        db.commit()

# --- НОВАЯ КЛЮЧЕВАЯ ФУНКЦИЯ ---
def build_full_context_for_ai(db: Session, session_id: int, current_node_text: str, current_node_options: list) -> str:
    """
    Собирает ПОЛНЫЙ контекст сессии (профиль, история ответов, история чата, текущий вопрос)
    и формирует из него единый системный промпт для GigaChat.
    """
    session = db.query(models.Session).filter(models.Session.id == session_id).first()
    if not session:
        return ""

    # 1. Собираем профиль пользователя (из прошлых ответов)
    # Пример: если мы знаем, что на узлах 'q_age', 'q_gender' спрашивали возраст/пол.
    # Этот блок нужно будет адаптировать под ваш реальный граф.
    profile_data = []
    # age_response = db.query(models.Response).filter_by(session_id=session_id, node_id='q_age').first()
    # if age_response:
    #     profile_data.append(f"Возраст: {age_response.answer_text}")
    
    # 2. Собираем историю ответов на вопросы графа (нажатия кнопок)
    responses = db.query(models.Response).filter(models.Response.session_id == session_id).order_by(models.Response.timestamp).all()
    response_history = [f"- На вопрос с ID '{r.node_id}' ответил: '{r.answer_text}'" for r in responses]

    # 3. Собираем историю диалога с ИИ
    dialogues = db.query(models.AIDialogue).filter(models.AIDialogue.session_id == session_id).order_by(models.AIDialogue.timestamp).all()
    dialogue_history = []
    for d in dialogues:
        dialogue_history.append(f"- Мой вопрос: {d.user_message}")
        dialogue_history.append(f"- Твой ответ: {d.ai_response}")

    # 4. Формируем контекст текущего вопроса
    options_text = "\n".join([f"- {opt['text']}" for opt in current_node_options if 'action' not in opt]) # Исключаем сервисные кнопки
    current_situation = f"Пользователю задан вопрос: \"{current_node_text}\"\nС вариантами ответа:\n{options_text}"

    # Собираем все в один большой промпт для ИИ
    full_prompt_context = (
        f"--- ПРОФИЛЬ РЕСПОНДЕНТА ---\n" + ("\n".join(profile_data) if profile_data else "Пока нет данных.") +
        f"\n\n--- ИСТОРИЯ ЕГО ОТВЕТОВ В ОПРОСЕ ---\n" + ("\n".join(response_history) if response_history else "Пока нет ответов.") +
        f"\n\n--- ИСТОРИЯ ДИАЛОГА С ТОБОЙ ---\n" + ("\n".join(dialogue_history) if dialogue_history else "Пока не общались.") +
        f"\n\n--- ТЕКУЩАЯ СИТУАЦИЯ ---\n{current_situation}"
    )
    
    return full_prompt_context

def get_response_for_node(db: Session, session_id: int, node_id: str):
    """
    Находит последний ответ пользователя для конкретного узла в текущей сессии.
    """
    response = db.query(models.Response).filter(
        models.Response.session_id == session_id,
        models.Response.node_id == node_id
    ).order_by(models.Response.timestamp.desc()).first()
    
    return response