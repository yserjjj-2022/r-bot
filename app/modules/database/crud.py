# app/modules/database/crud.py
# Версия 7.2:
# - Универсальная сводка состояния для ИИ (current/previous/delta/action/total) для всех переменных
# - Изоляция финансового промпта (только для роли financial_advisor и legacy "да"/"yes")
# - Поддержка ролей из data/prompts.json с кешированием
# - Обратная совместимость с текущей БД и логикой

import json
import os
from sqlalchemy.orm import Session
from sqlalchemy.sql import func
from . import models

# --- Кеш для промптов ---
_prompts_cache = None

def load_prompts():
    """
    Загружает роле-вые промпты из data/prompts.json.
    Если файла нет или ошибка — возвращает базовый набор.
    Кеширует результат в памяти.
    """
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
    
    # Fallback - базовые промпты в коде
    _prompts_cache = {
        "default": "Ты умный помощник в интерактивном сценарии. Отвечай кратко и по существу. Помогай пользователю в контексте текущей ситуации.",
        "financial_advisor": "Ты финансовый консультант. Помогай с учетом профиля и целей, анализируй риски и доходность."
    }
    print(f"--- [ПРОМПТЫ] Используются встроенные промпты (файл не найден) ---")
    return _prompts_cache

# --- Базовые CRUD функции (как были) ---
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

# =========================
# УНИВЕРСАЛЬНОЕ СОСТОЯНИЕ
# =========================

# Алиасы для человекочитаемых названий переменных (можно дополнять)
STATE_ALIASES = {
    "score": "капитал",
    "capital_before": "капитал (прошл.)",
    "health": "здоровье",
    "coins": "монеты",
    "debt": "задолженность",
    "deposit": "вклад",
}

def _safe_to_number(val: str):
    """Преобразует строковое значение переменной к float, если возможно, иначе None."""
    try:
        return float(val)
    except (TypeError, ValueError):
        return None

def collect_state_history(db: Session, user_id: int, session_id: int):
    """
    Собирает историю значений всех переменных пользователя в сессии.
    Возвращает dict: { key: [ (id, value_str), ... ] } в порядке времени (возрастание id).
    """
    rows = db.query(models.UserState).filter(
        models.UserState.user_id == user_id,
        models.UserState.session_id == session_id
    ).order_by(models.UserState.id.asc()).all()

    hist = {}
    for r in rows:
        hist.setdefault(r.state_key, []).append((r.id, r.state_value))
    return hist

def _format_delta(number):
    """Форматирует дельту со знаком и пробелами тысяч: +12 345 / -7 000 / +3.5"""
    if number is None:
        return "n/a"
    if isinstance(number, float) and number.is_integer():
        number = int(number)
    try:
        s = f"{number:+,}".replace(",", " ")
        return s
    except Exception:
        return str(number)

def _format_number(number):
    """Форматирует число с пробелами тысяч."""
    if number is None:
        return "n/a"
    if isinstance(number, float) and number.is_integer():
        number = int(number)
    try:
        return f"{number:,}".replace(",", " ")
    except Exception:
        return str(number)

def _last_user_action_text(db: Session, session_id: int) -> str:
    """
    Возвращает краткое описание последнего действия игрока в сессии:
    «<Текст узла> — <Ответ/интерпретация>».
    Если нет записей — возвращает пустую строку.
    """
    last_resp = db.query(models.Response).filter(models.Response.session_id == session_id)\
        .order_by(models.Response.id.desc()).first()
    if not last_resp:
        return ""
    node = (last_resp.node_text or "").strip()
    ans = (last_resp.answer_text or "").strip()
    if node and ans:
        return f"{node} — {ans}"
    return node or ans or ""

def build_universal_state_summary(db: Session, user_id: int, session_id: int) -> str:
    """
    Формирует компактный текстовый блок состояния всех переменных:
    <alias|key>: current=..., previous=..., delta=...(действие: "..."), total=...
    """
    hist = collect_state_history(db, user_id, session_id)
    if not hist:
        return "Игровое состояние: нет данных."

    last_action = _last_user_action_text(db, session_id)
    lines = ["Игровое состояние:"]

    for key, seq in hist.items():
        # Находим initial, previous, current
        initial_str = seq[0][1] if seq else None
        current_str = seq[-1][1] if seq else None
        previous_str = seq[-2][1] if len(seq) >= 2 else None

        initial = _safe_to_number(initial_str)
        previous = _safe_to_number(previous_str)
        current = _safe_to_number(current_str)

        # Вычисляем метрики
        delta = current - previous if (current is not None and previous is not None) else None
        total = current - initial if (current is not None and initial is not None) else None

        # Красивые подписи
        label = STATE_ALIASES.get(key, key)
        cur_txt = _format_number(current)
        prev_txt = _format_number(previous)
        delta_txt = _format_delta(delta)
        total_txt = _format_delta(total)

        # Формируем строку (включаем действие, если есть последняя запись и была дельта)
        if last_action and delta is not None:
            line = f"- {label}: current={cur_txt}; previous={prev_txt}; delta={delta_txt} (действие: «{last_action}»); total={total_txt}"
        else:
            line = f"- {label}: current={cur_txt}; previous={prev_txt}; delta={delta_txt}; total={total_txt}"
        lines.append(line)

    summary = "\n".join(lines)
    # Для отладки (можно убрать позже)
    print(f"--- [STATE] Сводка состояния для session={session_id} ---\n{summary}")
    return summary

# =========================
# ПОСТРОЕНИЕ ПРОМПТОВ ДЛЯ ИИ
# =========================

def build_full_context_for_ai(
    db: Session, 
    session_id: int, 
    user_id: int, 
    current_question: str, 
    options: list, 
    event_type: str = None,
    ai_persona: str = "да",
    ai_risk_appetite: int = 3
) -> str:
    """
    Собирает контекст для ИИ с поддержкой разных ролей.
    Изоляция: финансовый промпт только для financial_advisor/да/yes, остальным — универсальный.
    """
    persona_norm = (ai_persona or "").strip().lower()
    if persona_norm in ["да", "yes", "financial_advisor"]:
        print(f"--- [AI-CONTEXT] persona={ai_persona} → financial_advisor_prompt")
        return build_financial_advisor_prompt(
            db, session_id, user_id, current_question, options, event_type, ai_risk_appetite
        )
    else:
        print(f"--- [AI-CONTEXT] persona={ai_persona} → persona_prompt")
        return build_persona_prompt(
            db, session_id, user_id, current_question, options, persona_norm
        )

def build_financial_advisor_prompt(
    db: Session, 
    session_id: int, 
    user_id: int, 
    current_question: str, 
    options: list, 
    event_type: str = None,
    ai_risk_appetite: int = 3
) -> str:
    """
    Специализированный промпт для финансового консультанта.
    Внимание: упоминает инвестиционную философию — используется ТОЛЬКО для роли financial_advisor/да/yes.
    """
    # "Переводчик" числового уровня риска в инструкцию
    risk_philosophy_map = {
        1: "Крайне консервативная. Приоритет — сохранение капитала любой ценой.",
        2: "Консервативная. Сохранение капитала важнее высокой доходности.",
        3: "Сбалансированная (нейтральная). Равный баланс между риском и доходностью.",
        4: "Умеренно-агрессивная. Готовность к риску ради повышенной доходности.",
        5: "Агрессивная. Максимальная доходность является главной целью, несмотря на высокие риски."
    }
    ai_philosophy = risk_philosophy_map.get(ai_risk_appetite, risk_philosophy_map[3])

    # Профиль и история
    all_responses = db.query(models.Response).filter(models.Response.session_id == session_id).order_by(models.Response.id).all()
    soc_dem_keys = ['возраст', 'пол', 'образование', 'доход', 'риск', 'приоритет', 'стратегия', 'цель']
    
    profile_info = []
    game_history = []
    for r in all_responses:
        is_profile_data = any(key in (r.node_id or "").lower() for key in soc_dem_keys)
        event_text = ' '.join((r.node_text or "").split())
        choice_text = ' '.join((r.answer_text or "").split())

        if is_profile_data:
            profile_info.append(f"- {choice_text}")
        else:
            game_history.append(f"- Событие: «{event_text}»\n  - Решение игрока: «{choice_text}»")
    
    profile_block = "\n".join(profile_info) if profile_info else "Еще не собран."
    history_block = "\n".join(game_history) if game_history else "Это первое действие в игре."

    # Универсальная сводка всех переменных
    state_summary = build_universal_state_summary(db, user_id, session_id)

    options_text = "\n".join([f"- {opt['text']}" for opt in options]) if options else "Вариантов ответа нет."
    
    system_prompt = (
        "Ты — AI-ассистент, действующий как опытный финансовый консультант с четко заданной инвестиционной философией.\n\n"
        "--- ИСХОДНЫЕ ДАННЫЕ ДЛЯ АНАЛИЗА ---\n\n"
        f"ТВОЯ ИНВЕСТИЦИОННАЯ ФИЛОСОФИЯ:\n{ai_philosophy}\n\n"
        f"1) ДОСЬЕ ИГРОКА:\n{profile_block}\n\n"
        f"2) ХРОНОЛОГИЯ ИГРЫ:\n{history_block}\n\n"
        f"3) ИГРОВОЕ СОСТОЯНИЕ:\n{state_summary}\n\n"
        f"4) ТЕКУЩАЯ СИТУАЦИЯ:\n{(current_question or '').strip()}\n\n"
        f"5) ВАРИАНТЫ ДЕЙСТВИЙ:\n{options_text}\n\n"
        "--- ТВОЙ ПЛАН ДЕЙСТВИЙ ---\n"
        "1) Анализируй ситуацию в контексте ДОСЬЕ и Игрового состояния. "
        "2) Дай единый связный ответ. Не используй 'Шаг 1/2' и не упоминай философию явно."
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
    """
    Универсальный промпт для любых ролей (detective, teacher, therapist, game_master и т.д.).
    НЕ содержит финансовых терминов. Включает историю, универсальную сводку состояния и текущую задачу.
    """
    prompts = load_prompts()
    base_template = prompts.get(ai_persona, prompts.get("default", ""))

    # Короткая недавняя история (последние 5)
    recent = db.query(models.Response).filter(models.Response.session_id == session_id)\
        .order_by(models.Response.id.desc()).limit(5).all()
    recent_history = []
    for r in reversed(recent):
        event_text = ' '.join((r.node_text or "").split())
        choice_text = ' '.join((r.answer_text or "").split())
        if event_text or choice_text:
            recent_history.append(f"• {event_text} → {choice_text}")
    history_block = "\n".join(recent_history) if recent_history else "Это первое взаимодействие."

    # Универсальная сводка всех переменных
    state_summary = build_universal_state_summary(db, user_id, session_id)

    # Варианты
    options_text = "\n".join([f"- {opt['text']}" for opt in options]) if options else "Нет вариантов ответа."
    
    full_prompt = (
        f"{base_template}\n\n"
        f"КОНТЕКСТ ВЗАИМОДЕЙСТВИЯ:\n\n"
        f"История:\n{history_block}\n\n"
        f"Игровое состояние:\n{state_summary}\n\n"
        f"Текущая ситуация: {(current_question or '').strip()}\n\n"
        f"Доступные варианты:\n{options_text}\n\n"
        f"Ответь в своей роли, учитывая весь контекст."
    )

    print(f"--- [ИИ-РОЛЬ] Использован промпт для роли: {ai_persona} ---")
    return full_prompt

# --- Опциональные вспомогательные функции профиля/истории (если нужны в других местах) ---

def get_simple_profile_context(db: Session, session_id: int) -> str:
    """Упрощенный профиль пользователя для новых ролей."""
    responses = db.query(models.Response).filter(models.Response.session_id == session_id).limit(10).all()
    soc_dem_keys = ['возраст', 'пол', 'образование', 'опыт', 'профессия']
    
    profile_data = []
    for r in responses:
        if any(key in (r.node_id or "").lower() for key in soc_dem_keys):
            if r.answer_text:
                profile_data.append(r.answer_text)
    
    return "Профиль: " + ", ".join(profile_data) if profile_data else "Профиль пока не собран"

def get_recent_history_context(db: Session, session_id: int, limit: int = 5) -> str:
    """Последние N взаимодействий для контекста."""
    recent = db.query(models.Response).filter(models.Response.session_id == session_id).order_by(models.Response.id.desc()).limit(limit).all()
    
    history_items = []
    for r in reversed(recent):  # Показываем в хронологическом порядке
        if r.node_text or r.answer_text:
            history_items.append(f"• {str(r.node_text)[:50]}... → {r.answer_text}")
    
    return "История:\n" + "\n".join(history_items) if history_items else "Это первое взаимодействие"

def get_current_state_context(db: Session, user_id: int, session_id: int) -> str:
    """Текущее состояние пользователя (сохранена для совместимости)."""
    score = get_user_state(db, user_id, session_id, 'score', '0')
    return f"Счет: {score}"
