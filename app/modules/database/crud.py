# app/modules/database/crud.py
# Финальная версия: Добавлены финансовые показатели в промпт для ИИ

from sqlalchemy.orm import Session
from sqlalchemy.sql import func
from . import models

# --- Функции для работы с пользователями (без изменений) ---
def get_or_create_user(db: Session, telegram_id: int):
    user = db.query(models.User).filter(models.User.telegram_id == str(telegram_id)).first()
    if not user:
        user = models.User(telegram_id=str(telegram_id))
        db.add(user)
        db.commit()
        db.refresh(user)
    return user

# --- Функции для работы с сессиями (без изменений)---
def create_session(db: Session, user_id: int, graph_id: str):
    session = models.Session(user_id=user_id, graph_id=graph_id)
    db.add(session)
    db.commit()
    db.refresh(session)
    return session

def end_session(db: Session, session_id: int):
    session = db.query(models.Session).filter(models.Session.id == session_id).first()
    if session and session.end_time is None:
        session.end_time = func.now()
        db.commit()

# --- Функции для работы с ответами (без изменений) ---
def create_response(db: Session, session_id: int, node_id: str, answer_text: str):
    response = models.Response(session_id=session_id, node_id=node_id, answer_text=answer_text)
    db.add(response)
    db.commit()
    db.refresh(response)
    return response

# --- Функции для работы с состояниями пользователя (без изменений) ---
def get_user_state(db: Session, user_id: int, session_id: int, key: str, default: str = "0") -> str:
    state = db.query(models.UserState).filter(
        models.UserState.user_id == user_id,
        models.UserState.session_id == session_id,
        models.UserState.state_key == key
    ).order_by(models.UserState.id.desc()).first()
    return state.state_value if state else default

def update_user_state(db: Session, user_id: int, session_id: int, key: str, value: any):
    new_state = models.UserState(
        user_id=user_id,
        session_id=session_id,
        state_key=key,
        state_value=str(value)
    )
    db.add(new_state)
    db.commit()
    db.refresh(new_state)
    return new_state

# --- Функции для работы с диалогами GigaChat (без изменений) ---
def create_ai_dialogue(db: Session, session_id: int, node_id: str, user_message: str, ai_response: str):
    dialogue = models.AIDialogue(session_id=session_id, node_id=node_id, user_message=user_message, ai_response=ai_response)
    db.add(dialogue)
    db.commit()
    return dialogue

# --- ИЗМЕНЕНИЕ: Улучшенная функция сборки контекста для ИИ ---
def build_full_context_for_ai(db: Session, session_id: int, user_id: int, current_question: str, options: list) -> str:
    """Собирает полный контекст, включая финансовое состояние, для системного промпта."""
    # 1. Собираем историю ответов (как и раньше)
    responses = db.query(models.Response).filter(models.Response.session_id == session_id).order_by(models.Response.id).all()
    history = "\n".join([f"- Ответ на вопрос '{r.node_id}': {r.answer_text}" for r in responses])
    if not history:
        history = "Пока нет."

    # 2. Собираем АКТУАЛЬНОЕ финансовое состояние игрока
    score = get_user_state(db, user_id, session_id, 'score', '0')
    capital_before = get_user_state(db, user_id, session_id, 'capital_before', '0')
    
    # Форматируем финансовую сводку
    state_info = (
        f"- Текущий капитал (score): {int(float(score)):,}".replace(",", " ") + " руб.\n"
        f"- Капитал до начала раунда (capital_before): {int(float(capital_before)):,}".replace(",", " ") + " руб."
    )

    # 3. Собираем финальный промпт с новой, улучшенной структурой
    options_text = "\n".join([f"- {opt['text']}" for opt in options]) if options else "Вариантов ответа нет."
    
    system_prompt = (
        "Ты — AI-ассистент в финансовой игре. Твоя роль — финансовый консультант. Твоя задача — проанализировать всю предоставленную информацию и дать пользователю развернутый, аргументированный совет.\n\n"
        "--- КОНТЕКСТ ---\n"
        f"**Текущий вопрос пользователю:**\n{current_question}\n\n"
        f"**Предложенные варианты выбора:**\n{options_text}\n\n"
        f"**ФИНАНСОВАЯ СВОДКА ПО ИГРОКУ:**\n{state_info}\n\n"
        f"**История предыдущих решений игрока:**\n{history}\n\n"
        "--- ЗАДАЧА ---\n"
        "Основываясь на ВСЕЙ этой информации, ответь на следующий вопрос пользователя. Дай конкретную рекомендацию."
    )
    return system_prompt
