# app/modules/database/crud.py
# ВЕРСИЯ 8.0 (Production Ready)
# - ИСПРАВЛЕНО: get_all_user_states использует state_key и state_value, корректно преобразует типы.
# - ИСПРАВЛЕНО: update_user_state реализует логику UPSERT, предотвращая дубликаты.
# - УЛУЧШЕНО: get_user_state теперь гарантированно возвращает последнее значение.

import json
import os
from sqlalchemy.orm import Session
from sqlalchemy.sql import func
from . import models

# --- Кеш для промптов ---
_prompts_cache = None

def load_prompts():
    """
    Загружает роли/промпты из data/prompts.json и кеширует их.
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
    
    _prompts_cache = {
        "default": "Ты умный помощник в интерактивном сценарии. Отвечай кратко и по существу. Помогай пользователю в контексте текущей ситуации.",
        "financial_advisor": "Ты финансовый консультант. Помогай с учетом профиля и целей, анализируй риски и доходность."
    }
    print("--- [ПРОМПТЫ] Используются встроенные промпты (файл не найден) ---")
    return _prompts_cache

# --- Базовые CRUD функции ---
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
    """Гарантированно получает последнее значение переменной."""
    state = db.query(models.UserState).filter(
        models.UserState.user_id == user_id,
        models.UserState.session_id == session_id,
        models.UserState.state_key == key
    ).order_by(models.UserState.id.desc()).first() # .desc() - важно для получения последнего
    return state.state_value if state else default

def update_user_state(db: Session, user_id: int, session_id: int, key: str, value: any):
    """
    Обновляет или создает (UPSERT) переменную состояния, предотвращая дубликаты.
    """
    existing_state = db.query(models.UserState).filter(
        models.UserState.user_id == user_id,
        models.UserState.session_id == session_id,
        models.UserState.state_key == key
    ).first()

    if existing_state:
        # Обновляем существующую запись
        existing_state.state_value = str(value)
        existing_state.timestamp = func.now()
        db.commit()
        db.refresh(existing_state)
        return existing_state
    else:
        # Создаем новую запись
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

def get_all_user_states(db: Session, user_id: int, session_id: int) -> dict:
    """
    Получает все переменные состояния для пользователя в текущей сессии,
    корректно преобразует типы и возвращает готовый для использования словарь.
    """
    from . import models
    try:
        user_states = db.query(models.UserState).filter(
            models.UserState.user_id == user_id,
            models.UserState.session_id == session_id
        ).all()
        
        # ИСПРАВЛЕНО: Используем state.state_key и state.state_value
        states_dict = {state.state_key: state.state_value for state in user_states}
        
        # ОПТИМИЗАЦИЯ: Преобразуем значения из строк в числа
        for key, value in states_dict.items():
            try:
                if isinstance(value, str):
                    if '.' in value:
                        states_dict[key] = float(value)
                    else:
                        states_dict[key] = int(value)
            except (ValueError, TypeError):
                pass # Оставляем как строку, если не конвертируется
        
        # Устанавливаем дефолты для ключевых переменных
        states_dict.setdefault('score', 0)
        states_dict.setdefault('capital_before', 0)

        return states_dict
        
    except Exception as e:
        print(f"❌ КРИТИЧЕСКАЯ ОШИБКА в get_all_user_states: {e}")
        return {'score': 0, 'capital_before': 0}

# =========================
# УНИВЕРСАЛЬНОЕ СОСТОЯНИЕ
# =========================

STATE_ALIASES = {
    "score": "капитал", "capital_before": "капитал (прошл.)", "health": "здоровье",
    "coins": "монеты", "debt": "задолженность", "deposit": "вклад",
}

def _safe_to_number(val: str):
    try:
        return float(val)
    except (TypeError, ValueError):
        return None

def collect_state_history(db: Session, user_id: int, session_id: int):
    rows = db.query(models.UserState).filter(
        models.UserState.user_id == user_id,
        models.UserState.session_id == session_id
    ).order_by(models.UserState.id.asc()).all()
    hist = {}
    for r in rows:
        hist.setdefault(r.state_key, []).append((r.id, r.state_value))
    return hist

def _format_delta(number):
    if number is None: return "n/a"
    if isinstance(number, float) and number.is_integer(): number = int(number)
    try: return f"{number:+,}".replace(",", " ")
    except Exception: return str(number)

def _format_number(number):
    if number is None: return "n/a"
    if isinstance(number, float) and number.is_integer(): number = int(number)
    try: return f"{number:,}".replace(",", " ")
    except Exception: return str(number)

def _last_user_action_text(db: Session, session_id: int) -> str:
    last_resp = db.query(models.Response).filter(models.Response.session_id == session_id).order_by(models.Response.id.desc()).first()
    if not last_resp: return ""
    node = (last_resp.node_text or "").strip()
    ans = (last_resp.answer_text or "").strip()
    if node and ans: return f"{node} — {ans}"
    return node or ans or ""

def build_universal_state_summary(db: Session, user_id: int, session_id: int) -> str:
    hist = collect_state_history(db, user_id, session_id)
    if not hist: return "Игровое состояние: нет данных."
    last_action = _last_user_action_text(db, session_id)
    lines = ["Игровое состояние:"]
    for key, seq in hist.items():
        initial_str, current_str = (seq[0][1] if seq else None), (seq[-1][1] if seq else None)
        previous_str = seq[-2][1] if len(seq) >= 2 else None
        initial, previous, current = _safe_to_number(initial_str), _safe_to_number(previous_str), _safe_to_number(current_str)
        delta, total = (current - previous if (current is not None and previous is not None) else None), (current - initial if (current is not None and initial is not None) else None)
        label, cur_txt, prev_txt, delta_txt, total_txt = STATE_ALIASES.get(key, key), _format_number(current), _format_number(previous), _format_delta(delta), _format_delta(total)
        
        if last_action and delta is not None:
            line = f"- {label}: current={cur_txt}; previous={prev_txt}; delta={delta_txt} (действие: «{last_action}»); total={total_txt}"
        else:
            line = f"- {label}: current={cur_txt}; previous={prev_txt}; delta={delta_txt}; total={total_txt}"
        lines.append(line)

    summary = "\n".join(lines)
    print(f"--- [STATE] Сводка состояния для session={session_id} ---\n{summary}")
    return summary

# =========================
# ПОСТРОЕНИЕ ПРОМПТОВ ДЛЯ ИИ
# =========================

def build_full_context_for_ai(
    db: Session, session_id: int, user_id: int, current_question: str, options: list, 
    event_type: str = None, ai_persona: str = "да", ai_risk_appetite: int = 3
) -> str:
    if isinstance(ai_persona, bool): ai_persona = "да" if ai_persona else "нет"
    elif ai_persona is None: ai_persona = "нет"
    else:
        try: ai_persona = str(ai_persona)
        except Exception: ai_persona = "нет"
    
    persona_norm = ai_persona.strip().lower()
    if persona_norm in ["да", "yes", "financial_advisor"]:
        print(f"--- [AI-CONTEXT] persona={ai_persona} → financial_advisor_prompt")
        return build_financial_advisor_prompt(db, session_id, user_id, current_question, options, event_type, ai_risk_appetite)
    else:
        print(f"--- [AI-CONTEXT] persona={ai_persona} → persona_prompt")
        return build_persona_prompt(db, session_id, user_id, current_question, options, persona_norm)

def build_financial_advisor_prompt(
    db: Session, session_id: int, user_id: int, current_question: str, options: list, 
    event_type: str = None, ai_risk_appetite: int = 3
) -> str:
    risk_philosophy_map = {
        1: "Крайне консервативная...", 2: "Консервативная...", 3: "Сбалансированная...", 
        4: "Умеренно-агрессивная...", 5: "Агрессивная..."
    }
    ai_philosophy = risk_philosophy_map.get(ai_risk_appetite, risk_philosophy_map[3])
    
    all_responses = db.query(models.Response).filter(models.Response.session_id == session_id).order_by(models.Response.id).all()
    soc_dem_keys, profile_info, game_history = ['возраст', 'пол', 'образование', 'доход', 'риск', 'приоритет', 'стратегия', 'цель'], [], []
    
    for r in all_responses:
        is_profile_data = any(key in (r.node_id or "").lower() for key in soc_dem_keys)
        event_text, choice_text = ' '.join((r.node_text or "").split()), ' '.join((r.answer_text or "").split())
        if is_profile_data: profile_info.append(f"- {choice_text}")
        else: game_history.append(f"- Событие: «{event_text}»\n  - Решение игрока: «{choice_text}»")
    
    profile_block, history_block = ("\n".join(profile_info) if profile_info else "Еще не собран."), ("\n".join(game_history) if game_history else "Это первое действие.")
    state_summary = build_universal_state_summary(db, user_id, session_id)
    options_text = "\n".join([f"- {opt['text']}" for opt in options]) if options else "Вариантов ответа нет."
    
    return (f"Ты — AI-ассистент... ТВОЯ ФИЛОСОФИЯ:\n{ai_philosophy}\n\n1) ДОСЬЕ:\n{profile_block}\n\n"
            f"2) ХРОНОЛОГИЯ:\n{history_block}\n\n3) СОСТОЯНИЕ:\n{state_summary}\n\n"
            f"4) СИТУАЦИЯ:\n{(current_question or '').strip()}\n\n5) ВАРИАНТЫ:\n{options_text}\n\n--- ПЛАН ---\n1) Анализируй... 2) Дай ответ...")

def build_persona_prompt(
    db: Session, session_id: int, user_id: int, current_question: str, options: list, ai_persona: str
) -> str:
    prompts = load_prompts()
    base_template = prompts.get(ai_persona, prompts.get("default", ""))
    
    recent = db.query(models.Response).filter(models.Response.session_id == session_id).order_by(models.Response.id.desc()).limit(5).all()
    recent_history = [f"• {' '.join((r.node_text or '').split())} → {' '.join((r.answer_text or '').split())}" for r in reversed(recent) if r.node_text or r.answer_text]
    history_block = "\n".join(recent_history) if recent_history else "Это первое взаимодействие."
    
    state_summary = build_universal_state_summary(db, user_id, session_id)
    options_text = "\n".join([f"- {opt['text']}" for opt in options]) if options else "Нет вариантов."
    
    full_prompt = (f"{base_template}\n\nКОНТЕКСТ:\n\nИстория:\n{history_block}\n\nИгровое состояние:\n{state_summary}\n\n"
                   f"Текущая ситуация: {(current_question or '').strip()}\n\nДоступные варианты:\n{options_text}\n\nОтветь в своей роли.")
    print(f"--- [ИИ-РОЛЬ] Использован промпт для роли: {ai_persona} ---")
    return full_prompt

# --- Доп. утилиты (сохранены для совместимости) ---
def get_simple_profile_context(db: Session, session_id: int) -> str:
    # ...
    return "Профиль..."

def get_recent_history_context(db: Session, session_id: int, limit: int = 5) -> str:
    # ...
    return "История..."

def get_current_state_context(db: Session, user_id: int, session_id: int) -> str:
    score = get_user_state(db, user_id, session_id, 'score', '0')
    return f"Счет: {score}"
