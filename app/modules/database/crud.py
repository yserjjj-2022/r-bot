# app/modules/database/crud.py
# Финальная версия 5.8: ИИ теперь различает типы событий

from sqlalchemy.orm import Session
from sqlalchemy.sql import func
from . import models

# --- Функции для работы с пользователями ---
def get_or_create_user(db: Session, telegram_id: int):
    """Находит пользователя по telegram_id или создает нового, если не найден."""
    user = db.query(models.User).filter(models.User.telegram_id == str(telegram_id)).first()
    if not user:
        user = models.User(telegram_id=str(telegram_id))
        db.add(user)
        db.commit()
        db.refresh(user)
    return user

# --- Функции для работы с сессиями опроса ---
def create_session(db: Session, user_id: int, graph_id: str):
    """Создает новую сессию опроса."""
    session = models.Session(user_id=user_id, graph_id=graph_id)
    db.add(session)
    db.commit()
    db.refresh(session)
    return session

def end_session(db: Session, session_id: int):
    """Завершает сессию опроса, устанавливая время окончания."""
    session = db.query(models.Session).filter(models.Session.id == session_id).first()
    if session and session.end_time is None:
        session.end_time = func.now()
        db.commit()

# --- Функции для работы с ответами ---
def create_response(db: Session, session_id: int, node_id: str, answer_text: str):
    """Сохраняет ответ пользователя на вопрос."""
    response = models.Response(session_id=session_id, node_id=node_id, answer_text=answer_text)
    db.add(response)
    db.commit()
    db.refresh(response)
    return response

# --- Функции для работы с состояниями пользователя ---
def get_user_state(db: Session, user_id: int, session_id: int, key: str, default: str = "0") -> str:
    """Получает значение конкретного ключа состояния для пользователя в рамках сессии."""
    state = db.query(models.UserState).filter(
        models.UserState.user_id == user_id,
        models.UserState.session_id == session_id,
        models.UserState.state_key == key
    ).order_by(models.UserState.id.desc()).first()
    return state.state_value if state else default

def update_user_state(db: Session, user_id: int, session_id: int, key: str, value: any):
    """Обновляет или создает значение ключа состояния для пользователя в рамках сессии."""
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

# --- Функции для работы с диалогами GigaChat ---
def create_ai_dialogue(db: Session, session_id: int, node_id: str, user_message: str, ai_response: str):
    """Сохраняет диалог с AI."""
    dialogue = models.AIDialogue(session_id=session_id, node_id=node_id, user_message=user_message, ai_response=ai_response)
    db.add(dialogue)
    db.commit()
    return dialogue

# --- Функция сборки контекста для ИИ ---
def build_full_context_for_ai(db: Session, session_id: int, user_id: int, current_question: str, options: list, event_type: str = None) -> str:
    """Собирает полный контекст, включая финансовое состояние и ТИП СОБЫТИЯ, для системного промпта."""
    # 1. Собираем историю игровых решений
    responses = db.query(models.Response).filter(models.Response.session_id == session_id).order_by(models.Response.id).all()
    history = "\n".join([f"- Ответ на вопрос '{r.node_id}': {r.answer_text}" for r in responses])
    if not history:
        history = "Пока нет."

    # 2. Собираем актуальное финансовое состояние
    score = get_user_state(db, user_id, session_id, 'score', '0')
    state_info = f"- Текущий капитал (score): {int(float(score)):,}".replace(",", " ") + " руб."

    # 3. Определяем природу события
    event_context = ""
    if event_type == 'external_shock':
        event_context = "**Природа события:** Внешний шок, не зависящий от предыдущих решений игрока.\n"
    elif event_type == 'player_choice':
        event_context = "**Природа события:** Активный выбор игрока.\n"

    # 4. Собираем финальный промпт
    options_text = "\n".join([f"- {opt['text']}" for opt in options]) if options else "Вариантов ответа нет."
    
    system_prompt = (
        "Ты — финансовый консультант в игре. Твоя задача — дать конкретный совет.\n\n"
        "--- КОНТЕКСТ ДЛЯ АНАЛИЗА ---\n"
        f"{event_context}"
        f"**Текущая игровая ситуация:**\n{current_question}\n\n"
        f"**Предложенные варианты выбора:**\n{options_text}\n\n"
        f"**Финансовая сводка по игроку:**\n{state_info}\n\n"
        f"**История предыдущих решений игрока:**\n{history}\n\n"
        "--- ЗАДАЧА ---\n"
        "Основываясь на ВСЕХ этих данных, ответь на следующий вопрос пользователя. Если это был внешний шок, прояви эмпатию. Если это выбор игрока, помоги ему взвесить риски."
    )
    return system_prompt