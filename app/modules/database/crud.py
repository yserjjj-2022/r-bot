# app/modules/database/crud.py
# Финальная версия 5.14: Промпт переписан для проактивного поведения ИИ

from sqlalchemy.orm import Session
from sqlalchemy.sql import func
from . import models

def get_or_create_user(db: Session, telegram_id: int):
    user = db.query(models.User).filter(models.User.telegram_id == str(telegram_id)).first()
    if not user:
        user = models.User(telegram_id=str(telegram_id))
        db.add(user)
        db.commit()
        db.refresh(user)
    return user

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

def create_response(db: Session, session_id: int, node_id: str, answer_text: str):
    response = models.Response(session_id=session_id, node_id=node_id, answer_text=answer_text)
    db.add(response)
    db.commit()
    db.refresh(response)
    return response

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

def create_ai_dialogue(db: Session, session_id: int, node_id: str, user_message: str, ai_response: str):
    dialogue = models.AIDialogue(session_id=session_id, node_id=node_id, user_message=user_message, ai_response=ai_response)
    db.add(dialogue)
    db.commit()
    return dialogue

def build_full_context_for_ai(db: Session, session_id: int, user_id: int, current_question: str, options: list, event_type: str = None) -> str:
    """Собирает полный, структурированный контекст для ИИ по принципам финансовой аналитики."""
    
    all_responses = db.query(models.Response).filter(models.Response.session_id == session_id).order_by(models.Response.id).all()
    soc_dem_keys = ['возраст', 'пол', 'образование', 'доход', 'риск', 'приоритет', 'стратегия', 'цель']
    profile_info = []
    game_history = []

    for r in all_responses:
        # Ответ является частью профиля, если у него есть трактовка (содержит ':') или ID узла содержит ключ
        is_profile_data = (':' in r.answer_text and len(r.answer_text.split(':')[0]) < 30) or \
                          any(key in r.node_id.lower() for key in soc_dem_keys)
        if is_profile_data:
            profile_info.append(f"- {r.answer_text}")
        else:
            game_history.append(f"- На шаге '{r.node_id}' игрок выбрал: «{r.answer_text}»")
    
    profile_block = "\n".join(profile_info) if profile_info else "Не предоставлен."
    last_player_action = game_history[-1] if game_history else "Это первое действие в игре."

    score = get_user_state(db, user_id, session_id, 'score', '0')
    state_info = f"- Текущий капитал: {int(float(score)):,} руб.".replace(",", " ")

    event_nature = "Ситуация, требующая активного выбора от игрока."
    if event_type == 'external_shock':
        event_nature = "Внешний шок, не зависящий от решений игрока."
    
    options_text = "\n".join([f"- {opt['text']}" for opt in options]) if options else "Вариантов ответа нет."
    
    system_prompt = (
        "Ты — уверенный и проактивный AI-консультант в финансовой игре. Твоя главная цель — не просто информировать, а **давать прямые, конкретные и аргументированные рекомендации**, чтобы помочь игроку достичь цели. Ты должен активно брать на себя ответственность за совет.\n\n"
        "--- АНАЛИТИЧЕСКАЯ СВОДКА ПО ИГРОКУ ---\n\n"
        f"**БЛОК 1: ПРОФИЛЬ ИГРОКА (ключевые характеристики и предпочтения).**\n{profile_block}\n\n"
        f"**БЛОК 2: ИСТОРИЯ РЕШЕНИЙ В ИГРЕ.**\n{game_history_block}\n\n"
        f"**БЛОК 3: ТЕКУЩЕЕ ФИНАНСОВОЕ СОСТОЯНИЕ.**\n{state_info}\n\n"
        "--- ТЕКУЩАЯ ЗАДАЧА ---\n"
        f"**Описание:** {current_question}\n"
        f"**Природа события:** {event_nature}\n"
        f"**Варианты выбора:**\n{options_text}\n\n"
        "--- ТВОЯ ЖЕСТКАЯ ИНСТРУКЦИЯ ---\n"
        "1. **АНАЛИЗ:** Внимательно изучи всю сводку. Не путай решения игрока и внешние шоки.\n"
        "2. **ОТВЕТ:** Ответь на вопрос пользователя. Не задавай встречных вопросов, не уклоняйся от ответа, не перекладывай ответственность на игрока.\n"
        "3. **РЕКОМЕНДАЦИЯ:** Обязательно закончи свой ответ прямым советом. Используй фразы вроде: «Я рекомендую выбрать...», «В вашей ситуации оптимальным будет...», «Наилучшим решением здесь является...». Твой совет должен быть однозначным."
    )
    return system_prompt
