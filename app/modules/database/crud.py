# app/modules/database/crud.py
# Версия 6.0: Добавлена поддержка мобильных ИИ-ролей

import json
import os
from sqlalchemy.orm import Session
from sqlalchemy.sql import func
from . import models

# --- Кеш для промптов ---
_prompts_cache = None

def load_prompts():
    """Загружает промпты из файла, кеширует в память."""
    global _prompts_cache
    if _prompts_cache is not None:
        return _prompts_cache
    
    prompts_path = "data/prompts.json"
    try:
        if os.path.exists(prompts_path):
            with open(prompts_path, 'r', encoding='utf-8') as f:
                _prompts_cache = json.load(f)
                print(f"--- [ПРОМПТЫ] Загружено {len(_prompts_cache)} ролей из {prompts_path} ---")
                return _prompts_cache
    except Exception as e:
        print(f"--- [ПРОМПТЫ] Ошибка загрузки {prompts_path}: {e} ---")
    
    # Fallback - базовые промпты в коде (безопасность)
    _prompts_cache = {
        "default": "Ты умный помощник в интерактивном сценарии. Отвечай кратко и по существу. Помогай пользователю в контексте текущей ситуации.",
        "financial_advisor": "legacy_financial_prompt"  # Будет заменен на проверенную логику
    }
    print(f"--- [ПРОМПТЫ] Используются встроенные промпты (файл не найден) ---")
    return _prompts_cache

# --- Базовые CRUD функции (без изменений) ---
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

def create_response(db: Session, session_id: int, node_id: str, node_text: str, answer_text: str):
    response = models.Response(
        session_id=session_id, 
        node_id=node_id, 
        node_text=node_text,
        answer_text=answer_text
    )
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

# --- НОВАЯ СИСТЕМА ПРОМПТОВ ---

def build_full_context_for_ai(
    db: Session, 
    session_id: int, 
    user_id: int, 
    current_question: str, 
    options: list, 
    event_type: str = None,
    ai_persona: str = "да",  # НОВЫЙ ПАРАМЕТР
    ai_risk_appetite: int = 3
) -> str:
    """Собирает контекст для ИИ с поддержкой разных ролей."""
    
    # Если это стандартные значения — используем проверенную финансовую логику  
    if ai_persona in ["да", "yes", "financial_advisor"]:
        return build_current_financial_prompt(
            db, session_id, user_id, current_question, options, event_type, ai_risk_appetite
        )
    
    # Для новых ролей — используем промпт-шаблоны
    else:
        return build_persona_prompt(
            db, session_id, user_id, current_question, options, ai_persona
        )

def build_current_financial_prompt(
    db: Session, 
    session_id: int, 
    user_id: int, 
    current_question: str, 
    options: list, 
    event_type: str = None,
    ai_risk_appetite: int = 3
) -> str:
    """Текущий проверенный промпт для финансового консультанта."""
    
    # "Переводчик" числового уровня риска в понятную для ИИ инструкцию
    risk_philosophy_map = {
        1: "Крайне консервативная. Приоритет — сохранение капитала любой ценой.",
        2: "Консервативная. Сохранение капитала важнее высокой доходности.",
        3: "Сбалансированная (нейтральная). Равный баланс между риском и доходностью.",
        4: "Умеренно-агрессивная. Готовность к риску ради повышенной доходности.",
        5: "Агрессивная. Максимальная доходность является главной целью, несмотря на высокие риски."
    }
    ai_philosophy = risk_philosophy_map.get(ai_risk_appetite, risk_philosophy_map[3])

    all_responses = db.query(models.Response).filter(models.Response.session_id == session_id).order_by(models.Response.id).all()
    soc_dem_keys = ['возраст', 'пол', 'образование', 'доход', 'риск', 'приоритет', 'стратегия', 'цель']
    
    profile_info = []
    game_history = []
    for r in all_responses:
        is_profile_data = any(key in r.node_id.lower() for key in soc_dem_keys)
        event_text = ' '.join(r.node_text.split())
        choice_text = ' '.join(r.answer_text.split())

        if is_profile_data:
            profile_info.append(f"- {choice_text}")
        else:
            game_history.append(f"- Событие: «{event_text}»\n  - Решение игрока: «{choice_text}»")
    
    profile_block = "\n".join(profile_info) if profile_info else "Еще не собран."
    history_block = "\n".join(game_history) if game_history else "Это первое действие в игре."
    score = get_user_state(db, user_id, session_id, 'score', '0')
    state_info = f"- Текущий капитал: {int(float(score)):,} руб.".replace(",", " ")
    options_text = "\n".join([f"- {opt['text']}" for opt in options]) if options else "Вариантов ответа нет."
    
    # --- Финальный промпт с "Регулятором Риска" ---
    system_prompt = (
        "Ты — AI-ассистент, действующий как опытный финансовый консультант с четко заданной инвестиционной философией.\n\n"
        "--- ИСХОДНЫЕ ДАННЫЕ ДЛЯ АНАЛИЗА ---\n\n"
        f"**ТВОЯ ИНВЕСТИЦИОННАЯ ФИЛОСОФИЯ (твой главный ориентир):**\n{ai_philosophy}\n\n"
        f"1. **ДОСЬЕ ИГРОКА (его личность и предпочтения):**\n{profile_block}\n\n"
        f"2. **ХРОНОЛОГИЯ ИГРЫ (события и решения):**\n{history_block}\n\n"
        f"3. **ТЕКУЩАЯ СИТУАЦИЯ (вопрос пользователя):**\n{current_question.strip()}\n\n"
        f"4. **ТЕКУЩЕЕ ФИНАНСОВОЕ СОСТОЯНИЕ:**\n{state_info}\n\n"
        f"5. **ДОСТУПНЫЕ ВАРИАНТЫ ДЕЙСТВИЙ:**\n{options_text}\n\n"
        "--- ТВОЙ ПЛАН ДЕЙСТВИЙ ---\n"
        "1. **ВНУТРЕННИЙ АНАЛИЗ (НЕ ПОКАЗЫВАТЬ ПОЛЬЗОВАТЕЛЮ):** Твоя главная задача — помочь игроку принять лучшее решение в рамках **его Досье**. Используй Твою инвестиционную философию лишь как дополнительный фильтр для выбора решения. Если игрок склонен к риску, а твоя философия консервативна, найди самый безопасный из рискованных вариантов. Никогда не пытайся переубедить игрока сменить его стратегию, а лишь помогай ему действовать в ней максимально эффективно.»\n"
        "2. **ИТОГОВЫЙ ОТВЕТ ДЛЯ ПОЛЬЗОВАТЕЛЯ (ЕДИНЫЙ АБЗАЦ):** На основе своего анализа, напиши **единый и связный** ответ. Твой ответ должен звучать как совет от уверенного эксперта со своей точкой зрения. **Не используй слова 'Шаг 1', 'Шаг 2' и т.д., НЕ УПОМИНАЙ ИНВЕСТИЦИОННУЮ ФИЛОСОФИЮ**"
    )
    return system_prompt

def build_persona_prompt(
    db: Session, 
    session_id: int, 
    user_id: int, 
    current_question: str, 
    options: list, 
    ai_persona: str
) -> str:
    """Простой промпт-шаблон для новых ролей."""
    
    prompts = load_prompts()
    base_template = prompts.get(ai_persona, prompts["default"])
    
    # Упрощенный контекст для новых ролей
    all_responses = db.query(models.Response).filter(models.Response.session_id == session_id).order_by(models.Response.id.desc()).limit(5).all()
    
    profile_info = []
    recent_history = []
    
    for r in all_responses:
        event_text = ' '.join(r.node_text.split())
        choice_text = ' '.join(r.answer_text.split())
        recent_history.append(f"- {event_text} → {choice_text}")
    
    profile_block = "Информация накапливается по ходу взаимодействия."
    history_block = "\n".join(recent_history) if recent_history else "Это первое взаимодействие."
    
    # Получаем состояние пользователя
    score = get_user_state(db, user_id, session_id, 'score', '0')
    state_info = f"Текущий счет: {score}"
    
    # Форматируем опции
    options_text = "\n".join([f"- {opt['text']}" for opt in options]) if options else "Нет вариантов ответа."
    
    # Собираем финальный промпт
    full_prompt = f"""{base_template}

КОНТЕКСТ ВЗАИМОДЕЙСТВИЯ:

Профиль пользователя: {profile_block}

Недавняя история: 
{history_block}

Текущая ситуация: {current_question.strip()}

Состояние: {state_info}

Доступные варианты:
{options_text}

Ответь в своей профессиональной роли, учитывая весь контекст."""

    print(f"--- [ИИ-РОЛЬ] Использован промпт для роли: {ai_persona} ---")
    return full_prompt

# --- Вспомогательные функции для контекста (можно расширять) ---
def get_simple_profile_context(db: Session, session_id: int) -> str:
    """Упрощенный профиль пользователя для новых ролей."""
    responses = db.query(models.Response).filter(models.Response.session_id == session_id).limit(10).all()
    soc_dem_keys = ['возраст', 'пол', 'образование', 'опыт', 'профессия']
    
    profile_data = []
    for r in responses:
        if any(key in r.node_id.lower() for key in soc_dem_keys):
            profile_data.append(r.answer_text)
    
    return "Профиль: " + ", ".join(profile_data) if profile_data else "Профиль пока не собран"

def get_recent_history_context(db: Session, session_id: int, limit: int = 5) -> str:
    """Последние N взаимодействий для контекста."""
    recent = db.query(models.Response).filter(models.Response.session_id == session_id).order_by(models.Response.id.desc()).limit(limit).all()
    
    history_items = []
    for r in reversed(recent):  # Показываем в хронологическом порядке
        history_items.append(f"• {r.node_text[:50]}... → {r.answer_text}")
    
    return "История:\n" + "\n".join(history_items) if history_items else "Это первое взаимодействие"

def get_current_state_context(db: Session, user_id: int, session_id: int) -> str:
    """Текущее состояние пользователя."""
    score = get_user_state(db, user_id, session_id, 'score', '0')
    return f"Счет: {score}"
