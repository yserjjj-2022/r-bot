# app/modules/database/crud.py

from sqlalchemy.orm import Session
from . import models

# --- Функции для работы с пользователями ---

def get_or_create_user(db: Session, telegram_id: int):
    """
    Находит пользователя по telegram_id или создает нового, если не найден.
    Принимает сессию `db` в качестве аргумента.
    """
    # Ищем пользователя, используя переданную сессию `db`
    user = db.query(models.User).filter(models.User.telegram_id == str(telegram_id)).first()
    if not user:
        # Создаем нового пользователя в рамках той же сессии `db`
        user = models.User(telegram_id=str(telegram_id))
        db.add(user)
        db.commit()
        db.refresh(user)
    return user

# --- Функции для работы с сессиями опроса ---

def create_session(db: Session, user_id: int, graph_id: str):
    """
    Создает новую сессию опроса.
    """
    session = models.Session(user_id=user_id, graph_id=graph_id)
    db.add(session)
    db.commit()
    db.refresh(session)
    return session

def end_session(db: Session, session_id: int):
    """
    Завершает сессию опроса.
    """
    session = db.query(models.Session).filter(models.Session.id == session_id).first()
    if session:
        session.is_active = False
        db.commit()

# --- Функции для работы с ответами ---

def create_response(db: Session, session_id: int, node_id: str, answer_text: str):
    """
    Сохраняет ответ пользователя на вопрос.
    """
    response = models.Response(session_id=session_id, node_id=node_id, answer_text=answer_text)
    db.add(response)
    db.commit()
    db.refresh(response)
    return response

def get_response_for_node(db: Session, session_id: int, node_id: str):
    """
    Получает последний ответ пользователя для конкретного узла в рамках сессии.
    """
    return db.query(models.Response).filter(
        models.Response.session_id == session_id,
        models.Response.node_id == node_id
    ).order_by(models.Response.id.desc()).first()

# --- Функции для работы с диалогами GigaChat ---

def create_ai_dialogue(db: Session, session_id: int, node_id: str, user_message: str, ai_response: str):
    """
    Сохраняет диалог с AI.
    """
    dialogue = models.AIDialogue(
        session_id=session_id,
        node_id=node_id,
        user_message=user_message,
        ai_response=ai_response
    )
    db.add(dialogue)
    db.commit()
    return dialogue

def build_full_context_for_ai(db: Session, session_id: int, current_question: str, options: list) -> str:
    """
    Собирает полный контекст для системного промпта GigaChat.
    """
    # Собираем историю ответов пользователя
    responses = db.query(models.Response).filter(models.Response.session_id == session_id).order_by(models.Response.id).all()
    history = "\n".join([f"- Ответ на вопрос '{r.node_id}': {r.answer_text}" for r in responses])

    # Форматируем варианты ответа
    options_text = "\n".join([f"- {opt['text']}" for opt in options]) if options else "Вариантов ответа нет."

    # Собираем системный промпт
    system_prompt = (
        "Ты — вежливый и компетентный ассистент."
        f"Текущий вопрос, который задали пользователю: '{current_question}'\n"
        f"Варианты ответов, которые ему были предложены:\n{options_text}\n"
        f"История предыдущих ответов пользователя:\n{history}\n"
        "Основываясь на этой информации, ответь на следующий вопрос пользователя."
    )
    return system_prompt
