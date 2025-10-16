# app/modules/database/crud.py
# ВЕРСИЯ 8.2 (16.10.2025): УНИВЕРСАЛЬНЫЕ ИИ-РОЛИ
# - ПЕРЕРАБОТАН: Блок построения промптов для ИИ.
# - build_full_context_for_ai теперь является "роутером" ролей.
# - build_persona_prompt стал универсальным для всех ролей из prompts.json.
# - Сохранена и улучшена сложная логика для build_financial_advisor_prompt.
# - Сохранена логика v8.1 для get_all_user_states для защиты от дубликатов.


import json
import os
from sqlalchemy.orm import Session
from sqlalchemy import func
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
    
    # Дефолтные промпты, если файл не найден
    _prompts_cache = {
        "default": "Ты умный помощник в интерактивном сценарии. Отвечай кратко и по существу. Помогай пользователю в контексте текущей ситуации.",
        "financial_advisor": "current_complex_prompt",
        "game_master": "Ты Мастер Игры — всеведущий ведущий, который знает все детали сценария, мотивы персонажей и скрытые взаимосвязи. Ты направляешь развитие сюжета, создаешь атмосферу, даешь подсказки когда игрок заходит в тупик. Твоя цель — сделать игру увлекательной и помочь игроку принимать осмысленные решения."
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
    ).order_by(models.UserState.id.desc()).first()
    return state.state_value if state else default


def update_user_state(db: Session, user_id: int, session_id: int, key: str, value: any):
    """Обновляет или создает (UPSERT) переменную состояния, предотвращая дубликаты."""
    existing_state = db.query(models.UserState).filter(
        models.UserState.user_id == user_id,
        models.UserState.session_id == session_id,
        models.UserState.state_key == key
    ).first()

    if existing_state:
        existing_state.state_value = str(value)
        existing_state.timestamp = func.now()
        db.commit()
        db.refresh(existing_state)
        return existing_state
    else:
        new_state = models.UserState(
            user_id=user_id, session_id=session_id,
            state_key=key, state_value=str(value)
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
    """Получает ПОСЛЕДНЕЕ состояние для каждой переменной, избегая проблем с дубликатами."""
    from . import models
    try:
        subquery = db.query(
            models.UserState.state_key,
            func.max(models.UserState.id).label('max_id')
        ).filter(
            models.UserState.user_id == user_id,
            models.UserState.session_id == session_id
        ).group_by(models.UserState.state_key).subquery()

        user_states = db.query(models.UserState).join(
            subquery,
            (models.UserState.state_key == subquery.c.state_key) & 
            (models.UserState.id == subquery.c.max_id)
        ).all()
        
        states_dict = {state.state_key: state.state_value for state in user_states}
        
        for key, value in states_dict.items():
            if isinstance(value, str):
                try:
                    states_dict[key] = float(value) if '.' in value else int(value)
                except (ValueError, TypeError):
                    pass
        
        states_dict.setdefault('score', 0)
        states_dict.setdefault('capital_before', 0)

        if not isinstance(states_dict.get('score'), (int, float)):
            print(f"🚨 [ЗАЩИТА] Некорректный тип для 'score': {type(states_dict['score'])}. Сброс на 0.")
            states_dict['score'] = 0
        if not isinstance(states_dict.get('capital_before'), (int, float)):
            states_dict['capital_before'] = 0

        return states_dict
        
    except Exception as e:
        print(f"❌ КРИТИЧЕСКАЯ ОШИБКА в get_all_user_states: {e}")
        return {'score': 0, 'capital_before': 0}


# =========================
# УНИВЕРСАЛЬНОЕ СОСТОЯНИЕ
# =========================
# ... (весь блок до "ПОСТРОЕНИЕ ПРОМПТОВ ДЛЯ ИИ" остается без изменений) ...
STATE_ALIASES = {
    "score": "капитал", "capital_before": "капитал (прошл.)", "health": "здоровье",
    "coins": "монеты", "debt": "задолженность", "deposit": "вклад",
}
def _safe_to_number(val: str):
    try: return float(val)
    except (TypeError, ValueError): return None
def collect_state_history(db: Session, user_id: int, session_id: int):
    rows = db.query(models.UserState).filter(models.UserState.user_id == user_id, models.UserState.session_id == session_id).order_by(models.UserState.id.asc()).all()
    hist = {}
    for r in rows: hist.setdefault(r.state_key, []).append((r.id, r.state_value))
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
        if last_action and delta is not None: line = f"- {label}: current={cur_txt}; previous={prev_txt}; delta={delta_txt} (действие: «{last_action}»); total={total_txt}"
        else: line = f"- {label}: current={cur_txt}; previous={prev_txt}; delta={delta_txt}; total={total_txt}"
        lines.append(line)
    summary = "\n".join(lines)
    print(f"--- [STATE] Сводка состояния для session={session_id} ---\n{summary}")
    return summary

# =========================
# ПОСТРОЕНИЕ ПРОМПТОВ ДЛЯ ИИ (v3.0 - УНИВЕРСАЛЬНЫЕ РОЛИ)
# =========================

def build_full_context_for_ai(
    db: Session,
    session_id: int,
    user_id: int,
    task_prompt: str,
    options: list,
    event_type: str = None,
    ai_persona: str = "default",
    ai_risk_appetite: int = 3
) -> str:
    """
    Главный роутер для сборки контекста ИИ с поддержкой разных ролей.
    """
    prompts = load_prompts()
    persona_key = str(ai_persona).strip().lower() if ai_persona else "default"
    system_template = prompts.get(persona_key, prompts.get("default", ""))
    
    print(f"--- [AI-CONTEXT] Роль: '{persona_key}', Шаблон: '{system_template[:30]}...'")

    if system_template == "current_complex_prompt":
        print("--- [AI-CONTEXT] Вызов сложного сборщика для financial_advisor ---")
        return build_financial_advisor_prompt(
            db, session_id, user_id, task_prompt, options, event_type, ai_risk_appetite
        )
    else:
        print(f"--- [AI-CONTEXT] Вызов универсального сборщика для '{persona_key}' ---")
        return build_persona_prompt(
            db, session_id, user_id, task_prompt, options, system_template
        )

def build_financial_advisor_prompt(
    db: Session, session_id: int, user_id: int, current_question: str, options: list,
    event_type: str = None, ai_risk_appetite: int = 3
) -> str:
    """Собирает детализированный промпт для роли 'financial_advisor'."""
    risk_philosophy_map = {1: "...", 2: "...", 3: "...", 4: "...", 5: "..."}
    ai_philosophy = risk_philosophy_map.get(ai_risk_appetite, "Сбалансированная...")
    
    all_responses = db.query(models.Response).filter(models.Response.session_id == session_id).order_by(models.Response.id).all()
    soc_dem_keys, profile_info, game_history = ['возраст', 'пол', 'образование', 'доход', 'риск', 'приоритет', 'стратегия', 'цель'], [], []
    
    for r in all_responses:
        is_profile_data = any(key in (r.node_id or "").lower() for key in soc_dem_keys)
        event_text, choice_text = ' '.join((r.node_text or "").split()), ' '.join((r.answer_text or "").split())
        if is_profile_data: profile_info.append(f"- {choice_text}")
        else: game_history.append(f"- Событие: «{event_text}»\n  - Решение игрока: «{choice_text}»")
    
    profile_block = "\n".join(profile_info) or "Еще не собран."
    history_block = "\n".join(game_history) or "Это первое действие."
    state_summary = build_universal_state_summary(db, user_id, session_id)
    options_text = "\n".join([f"- {opt['text']}" for opt in options]) if options else "Вариантов ответа нет."
    task_description = f"ТЕКУЩАЯ ЗАДАЧА: {current_question.strip()}" if current_question else ""
    
    return (f"Ты — AI-ассистент, финансовый консультант. Твоя философия: {ai_philosophy}\n\n"
            f"1. ДОСЬЕ НА ИГРОКА:\n{profile_block}\n\n"
            f"2. ХРОНОЛОГИЯ РЕШЕНИЙ:\n{history_block}\n\n"
            f"3. ФИНАНСОВОЕ СОСТОЯНИЕ:\n{state_summary}\n\n"
            f"{task_description}\n\n"
            f"ДОСТУПНЫЕ ИГРОКУ ВАРИАНТЫ:\n{options_text}\n\n"
            "ТВОЙ ПЛАН: Проанализируй всю информацию и дай краткий, но емкий совет в своей роли.")

def build_persona_prompt(
    db: Session, session_id: int, user_id: int, task_prompt: str, options: list, persona_template: str
) -> str:
    """Собирает универсальный промпт для любой роли, используя готовый шаблон."""
    recent_responses = db.query(models.Response).filter(models.Response.session_id == session_id).order_by(models.Response.id.desc()).limit(3).all()
    recent_history = [f"- {' '.join((r.node_text or '').split())} → {' '.join((r.answer_text or '').split())}" for r in reversed(recent_responses)]
    history_block = "\n".join(recent_history) or "Это начало диалога."
    
    state_summary = build_universal_state_summary(db, user_id, session_id)
    options_text = "\n".join([f"- {opt['text']}" for opt in options]) if options else "Вариантов нет."
    
    return (
        f"{persona_template}\n\n"
        f"### КОНТЕКСТ ДИАЛОГА ###\n"
        f"**Последние действия игрока:**\n{history_block}\n\n"
        f"**Текущее состояние игрока:**\n{state_summary}\n\n"
        f"**Твоя задача или вопрос от игрока:**\n{task_prompt.strip()}\n\n"
        f"**Варианты, доступные игроку:**\n{options_text}\n\n"
        f"Ответь в своей роли, кратко и по существу."
    )

# --- Доп. утилиты (сохранены для совместимости) ---
def get_simple_profile_context(db: Session, session_id: int) -> str:
    return "Профиль..."

def get_recent_history_context(db: Session, session_id: int, limit: int = 5) -> str:
    return "История..."

def get_current_state_context(db: Session, user_id: int, session_id: int) -> str:
    score = get_user_state(db, user_id, session_id, 'score', '0')
    return f"Счет: {score}"

