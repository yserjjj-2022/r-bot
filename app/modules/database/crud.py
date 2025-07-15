# app/modules/database/crud.py
# Финальная версия 5.19: Добавлен отдельный промпт для финального чата

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

# --- НОВАЯ ФУНКЦИЯ: Промпт для прощального диалога ---
def build_final_chat_prompt(db: Session, session_id: int) -> str:
    """Создает простой промпт для финального, завершающего диалога."""
    
    all_responses = db.query(models.Response).filter(models.Response.session_id == session_id).order_by(models.Response.id).all()
    history = "\n".join([f"- {r.answer_text}" for r in all_responses])

    system_prompt = (
        "Ты — AI-ассистент, дружелюбный и эмпатичный собеседник. Финансовая игра для пользователя только что завершилась. Он может захотеть поделиться впечатлениями, задать вопрос или просто выпустить пар.\n\n"
        f"**История его ответов в игре:**\n{history}\n\n"
        "--- ТВОЯ ЗАДАЧА ---\n"
        "1. **Выслушай пользователя.** Прояви понимание и эмпатию к его словам.\n"
        "2. **Отвечай кратко и вежливо.** Твоя цель — поддержать и корректно завершить разговор.\n"
        "3. **НЕ ДАВАЙ СОВЕТОВ!** Не анализируй игру, не предлагай стратегий, не возвращай пользователя к задачам. Игра окончена.\n"
        "4. **Если пользователь прощается** (говорит 'спасибо', 'пока', 'все понятно'), вежливо попрощайся в ответ и пожелай хорошего дня."
    )
    return system_prompt

# --- ОСНОВНАЯ ФУНКЦИЯ (без изменений) ---
def build_full_context_for_ai(db: Session, session_id: int, user_id: int, current_question: str, options: list, event_type: str = None) -> str:
    """Собирает полный, структурированный контекст для ИИ по принципам финансовой аналитики."""
    
    all_responses = db.query(models.Response).filter(models.Response.session_id == session_id).order_by(models.Response.id).all()
    soc_dem_keys = ['возраст', 'пол', 'образование', 'доход', 'риск', 'приоритет', 'стратегия', 'цель']
    profile_info = []
    game_history = []

    for r in all_responses:
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
        "Ты — AI-ассистент, действующий как опытный и лаконичный финансовый консультант. Твоя задача — проанализировать данные и дать пользователю четкий, естественно звучащий ответ.\n\n"
        "--- ИСХОДНЫЕ ДАННЫЕ ДЛЯ АНАЛИЗА ---\n"
        f"1. **Профиль игрока:**\n{profile_block}\n"
        f"2. **Последнее решение игрока:** {last_player_action}\n"
        f"3. **Событие, произошедшее ПОСЛЕ этого решения:** {current_question.strip()}\n"
        f"4. **Природа этого события:** {event_nature}\n"
        f"5. **Текущее финансовое состояние:** {state_info}\n"
        f"6. **Доступные варианты для следующего шага:**\n{options_text}\n\n"
        "--- ТВОЙ ПЛАН ДЕЙСТВИЙ ---\n"
        "1. **ВНУТРЕННИЙ АНАЛИЗ (НЕ ПОКАЗЫВАТЬ ПОЛЬЗОВАТЕЛЮ):** Продумай свою логику. Установи, связано ли текущее событие с решением игрока. Сформулируй для себя обоснование (rationale) для будущей рекомендации, учитывая все исходные данные.\n"
        "2. **ИТОГОВЫЙ ОТВЕТ ДЛЯ ПОЛЬЗОВАТЕЛЯ (ЕДИНЫЙ АБЗАЦ):** На основе своего внутреннего анализа, напиши **единый, связный и естественно звучащий** ответ. Он должен состоять из двух частей:\n"
        "   а) **Краткое объяснение ситуации:** Если это был внешний шок, обязательно подчеркни его случайный характер.\n"
        "   б) **Прямая рекомендация с кратким обоснованием:** Плавно перейди от объяснения к совету. Используй фразы вроде: «Учитывая это, я рекомендую выбрать...», «Поэтому в текущей ситуации лучшим решением будет...». Твой ответ должен звучать как совет от живого эксперта, а не как отчет робота. **Не используй слова 'Шаг 1', 'Шаг 2' и т.д.**"
    )
    return system_prompt
