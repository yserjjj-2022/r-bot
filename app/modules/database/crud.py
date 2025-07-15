# app/modules/database/crud.py
# Финальная версия 5.12: ИИ теперь использует "трактовки" для создания профиля игрока

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

# --- Функции для работы с сессиями опроса (без изменений) ---
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

# --- ИЗМЕНЕНИЕ: Финальная, улучшенная функция сборки контекста для ИИ ---
def build_full_context_for_ai(db: Session, session_id: int, user_id: int, current_question: str, options: list, event_type: str = None) -> str:
    """Собирает полный, структурированный контекст, используя "трактовки" для создания профиля."""
    
    # 1. Собираем ВСЮ историю ответов из базы данных
    all_responses = db.query(models.Response).filter(models.Response.session_id == session_id).order_by(models.Response.id).all()
    
    # Собираем интерпретированный профиль и историю
    profile_info = []
    game_history = []

    for r in all_responses:
        # Ответы с трактовкой (которые мы сохранили) формируют профиль
        # Мы можем определить их по наличию двоеточия, например: "Приоритет: Потенциальный доход"
        if ':' in r.answer_text and len(r.answer_text.split(':')[0]) < 30: # Простое эвристическое правило
            profile_info.append(f"- {r.answer_text}")
        else: # Все остальное - это игровые решения
            game_history.append(f"- На шаге '{r.node_id}' игрок выбрал: «{r.answer_text}»")

    profile_block = "\n".join(profile_info) if profile_info else "Не предоставлен."
    game_history_block = "\n".join(game_history) if game_history else "Еще не было."

    # 2. Собираем финансовую сводку
    score = get_user_state(db, user_id, session_id, 'score', '0')
    state_info = f"- Текущий капитал: {int(float(score)):,} руб.".replace(",", " ")

    # 3. Собираем информацию о текущем событии
    event_nature = "Ситуация, требующая активного выбора от игрока."
    if event_type == 'external_shock':
        event_nature = "Внешний шок, не зависящий от решений игрока."
    
    options_text = "\n".join([f"- {opt['text']}" for opt in options]) if options else "Вариантов ответа нет."
    
    # 4. Формируем финальный промпт
    system_prompt = (
        "Ты — AI-ассистент, действующий как опытный финансовый консультант...\n\n" # Укорочено для краткости
        "--- АНАЛИТИЧЕСКАЯ СВОДКА ПО ИГРОКУ ---\n\n"
        f"**БЛОК 1: ПРОФИЛЬ ИГРОКА (ключевые характеристики и предпочтения).**\n{profile_block}\n\n"
        f"**БЛОК 2: ИСТОРИЯ РЕШЕНИЙ В ИГРЕ.**\n{game_history_block}\n\n"
        f"**БЛОК 3: ТЕКУЩЕЕ ФИНАНСОВОЕ СОСТОЯНИЕ.**\n{state_info}\n\n"
        "--- ТЕКУЩАЯ ЗАДАЧА ---\n"
        f"**Описание:** {current_question}\n"
        f"**Природа события:** {event_nature}\n"
        f"**Варианты выбора:**\n{options_text}\n\n"
        "--- ТВОЯ ИНСТРУКЦИЯ ---\n"
        "1. Внимательно изучи ВСЕ досье. Учитывай ПРОФИЛЬ ИГРОКА при даче совета.\n"
        "2. Проанализируй текущую задачу в контексте всей предыдущей истории.\n"
        "3. Дай конкретный, аргументированный и персонализированный совет, обращаясь к игроку."
    )
    return system_prompt