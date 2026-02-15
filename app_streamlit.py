import asyncio
import streamlit as st
import pandas as pd
import altair as alt
import json
import plotly.graph_objects as go
import plotly.express as px
from typing import Dict, Any, List
from datetime import datetime
from sqlalchemy import select, delete, text
from src.r_core.schemas import BotConfig, PersonalitySliders, IncomingMessage
from src.r_core.pipeline import RCoreKernel
from src.r_core.memory import MemorySystem
# FIX: Removed init_models to prevent auto-migration
from src.r_core.infrastructure.db import AsyncSessionLocal, AgentProfileModel, UserProfileModel, SemanticModel
from src.r_core.config import settings
import re
import uuid # ✨ ADDED

# --- Setup Page ---
st.set_page_config(
    page_title="R-Bot Cortex Visualizer",
    page_icon="🧠",
    layout="wide"
)

# --- Init State ---
if "messages" not in st.session_state:
    st.session_state.messages = [] 

if "sliders" not in st.session_state:
    st.session_state.sliders = PersonalitySliders(
        empathy_bias=0.5, 
        risk_tolerance=0.5, 
        dominance_level=0.5, 
        pace_setting=0.5, 
        neuroticism=0.1,
        # ✨ NEW: Dashboard Controls (Homeostasis)
        chaos_level=0.2,
        learning_speed=0.5,
        persistence=0.5,
        # === Prediction Error ===
        pred_threshold=0.65, 
        pred_sensitivity=10.0
    )

if "bot_name" not in st.session_state:
    st.session_state.bot_name = "R-Bot"
    st.session_state.bot_gender = "Neutral"

# --- PERSISTENT KERNEL HACK ---
if "kernel_instance" not in st.session_state:
    st.session_state.kernel_instance = None

def run_async(coro):
    try:
        return asyncio.run(coro)
    except RuntimeError:
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(coro)

# --- ANALYTICS HELPERS ---
async def load_session_data(limit=100):
    """Загружает историю диалога и метрики, объединяя их по времени"""
    async with AsyncSessionLocal() as session:
        # 1. Загружаем сообщения
        msgs_result = await session.execute(
            text("""
                SELECT id, role, content, created_at, session_id, user_id
                FROM chat_history 
                ORDER BY created_at DESC 
                LIMIT :limit
            """),
            {"limit": limit * 2}
        )
        messages = msgs_result.mappings().all()
        
        # 2. Загружаем метрики (с поддержкой нового формата таблицы)
        try:
            metrics_result = await session.execute(
                text("""
                    SELECT session_id, timestamp, payload
                    FROM rcore_metrics
                    ORDER BY timestamp DESC
                    LIMIT :limit
                """),
                {"limit": limit}
            )
            metrics = metrics_result.mappings().all()
        except Exception as e:
            print(f"Warning: Could not load metrics (schema mismatch?): {e}")
            metrics = []
            
    return messages, metrics

def parse_metrics(metrics_row):
    try:
        data = metrics_row["payload"]
        if isinstance(data, str):
            data = json.loads(data)
        elif data is None:
            data = {}
            
        # Восстанавливаем timestamp, если он был потерян при парсинге JSON
        if "timestamp" not in data and "timestamp" in metrics_row:
            data["timestamp"] = metrics_row["timestamp"]
            
        return data
    except Exception as e:
        print(f"Error parsing metrics: {e}")
        return {}

def extract_scores(metrics_data):
    # Пытаемся достать 'all_scores' - бывает внутри 'agent_scores' или просто 'all_scores'
    scores = metrics_data.get("all_scores")
    if not scores:
        scores = metrics_data.get("agent_scores") 
    
    if not scores:
        return {"Amygdala": 0, "Prefrontal": 0, "Striatum": 0, "Social": 0, "Intuition": 0}
        
    # Нормализуем ключи (убираем эмодзи и суффиксы)
    # Пример ключей: "social_cortex", "amygdala_safety"
    clean_scores = {}
    
    mapping = {
        "amygdala": "Amygdala",
        "prefrontal": "Prefrontal",
        "striatum": "Striatum",
        "social": "Social",
        "intuition": "Intuition",
        "uncertainty": "Uncertainty" # ✨ Add Uncertainty
    }
    
    # Сначала заполним нулями
    for v in mapping.values(): clean_scores[v] = 0.0

    for k, v in scores.items():
        k_lower = k.lower()
        found = False
        for key_part, nice_name in mapping.items():
            if key_part in k_lower:
                clean_scores[nice_name] = float(v)
                found = True
                break
        
        # Если не нашли в маппинге, добавляем как есть (Capitalized)
        if not found:
            clean_scores[k.capitalize()] = float(v)
        
    return clean_scores

def extract_hormones(metrics_data):
    h_str = metrics_data.get("hormonal_state", "")
    h_map = {"NE": 0.5, "DA": 0.5, "5HT": 0.5, "CORT": 0.5}
    
    # 1. Если это словарь
    if isinstance(h_str, dict):
        h_map.update(h_str)
        return h_map

    # 2. Если строка "NE:0.5 DA:0.3..."
    if isinstance(h_str, str):
        # Очистка от лишних символов (скобок, запятых)
        clean_str = h_str.replace(",", " ").replace("{", "").replace("}", "").replace("'", "")
        parts = clean_str.split()
        for p in parts:
            if ":" in p:
                k, v = p.split(":")
                try:
                    h_map[k.strip()] = float(v)
                except:
                    pass
    return h_map

def extract_mood(metrics_data):
    """Извлекает VAD (Mood) из метрик"""
    # Ищем 'mood_state' or 'current_mood'
    mood_data = metrics_data.get("mood_state") or metrics_data.get("current_mood", "")
    vad = {"Valence": 0.0, "Arousal": 0.0, "Dominance": 0.0}
    
    if isinstance(mood_data, dict):
        vad["Valence"] = mood_data.get("valence", mood_data.get("Valence", 0.0))
        vad["Arousal"] = mood_data.get("arousal", mood_data.get("Arousal", 0.0))
        vad["Dominance"] = mood_data.get("dominance", mood_data.get("Dominance", 0.0))
        
    elif isinstance(mood_data, str):
        # Парсим строку вида "V:0.04 A:-0.05 D:0.01" или "MoodVector(valence=...)"
        try:
            # Убираем лишний мусор если это repr() объекта
            clean_str = mood_data.replace("MoodVector(", "").replace(")", "").replace(",", " ")
            parts = clean_str.split() 
            for p in parts:
                if "=" in p: # format valence=0.5
                    k, v = p.split("=")
                    k_title = k.capitalize()
                    if k_title in vad: vad[k_title] = float(v)
                elif ":" in p: # format V:0.5
                    k, v = p.split(":")
                    k_upper = k.upper()
                    if k_upper.startswith("V"): vad["Valence"] = float(v)
                    elif k_upper.startswith("A"): vad["Arousal"] = float(v)
                    elif k_upper.startswith("D"): vad["Dominance"] = float(v)
        except:
            pass
            
    return vad

def get_mood_label(metrics_data, vad):
    """
    Определяет текстовое описание настроения.
    Приоритет:
    1. Hormonal Archetype (если есть и не Neutral)
    2. Active Style (если есть)
    3. VAD interpretation
    """
    
    # 1. Hormonal Archetype
    archetype = metrics_data.get("hormonal_archetype")
    if archetype and isinstance(archetype, str) and archetype.upper() not in ["NEUTRAL", "CALM"]:
        return f"🔥 {archetype.upper()}"

    # 2. Active Style (Technical VAD description)
    style = metrics_data.get("active_style")
    if style and isinstance(style, str):
        # Ищем технические маркеры VAD
        if "[HIGH TEMPO]" in style: return "⚡ High Tempo (Agitated)"
        if "[LOW TEMPO]" in style: return "🐢 Low Tempo (Relaxed)"
        if "[DOMINANT]" in style: return "🦁 Dominant"
        if "[SUBMISSIVE]" in style: return "🐰 Submissive"
            
    # 3. VAD Fallback (Quadrants)
    v = vad.get("Valence", 0)
    a = vad.get("Arousal", 0)
    
    if v > 0.3 and a > 0.3: return "Joyful / Excited"
    if v > 0.3 and a < -0.1: return "Relaxed / Content"
    if v < -0.1 and a > 0.3: return "Angry / Anxious"
    if v < -0.1 and a < -0.1: return "Sad / Depressed"
    
    return "Neutral / Balanced"

def get_winner_safe(metrics_data):
    # 1. Явное поле
    w = metrics_data.get("winner_agent") or metrics_data.get("winning_agent") or metrics_data.get("winner")
    if w: return w

    # 2. Вычисление по максимальному скору (если есть all_scores)
    scores = extract_scores(metrics_data)
    if scores and max(scores.values()) > 0:
        winner = max(scores.items(), key=lambda x: x[1])[0]
        return winner
        
    return "Unknown"

# --- DB Operations for Agents ---
async def get_all_agents():
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(AgentProfileModel))
        return result.scalars().all()

async def create_agent(name: str, desc: str, gender: str, sliders: Dict):
    async with AsyncSessionLocal() as session:
        new_agent = AgentProfileModel(
            name=name, 
            description=desc,
            gender=gender,
            sliders_preset=sliders
        )
        session.add(new_agent)
        await session.commit()

async def get_affective_memory(user_id: int = 999):
    async with AsyncSessionLocal() as session:
        stmt = select(SemanticModel).where(
            SemanticModel.user_id == user_id,
            SemanticModel.sentiment.isnot(None)
        ).order_by(SemanticModel.created_at.desc()).limit(20)
        result = await session.execute(stmt)
        rows = result.scalars().all()
        return [{"subject": r.subject, "predicate": r.predicate, "object": r.object, "sentiment": r.sentiment} for r in rows]

async def update_profile_data(data):
    mem = MemorySystem()
    await mem.update_user_profile(999, data)

async def get_profile_data():
    mem = MemorySystem()
    return await mem.store.get_user_profile(999) 


# ==========================================
#              MAIN NAVIGATION
# ==========================================
st.sidebar.title("🧠 Cortex Controls")
app_mode = st.sidebar.radio("Navigation", ["💬 Chat Interface", "📈 Encephalogram (Analytics)", "🧬 Brain Structure (Introspection)"])
st.sidebar.divider()

if app_mode == "📈 Encephalogram (Analytics)":
    # ==========================================
    #           ANALYTICS DASHBOARD
    # ==========================================
    st.title("🧠 R-Bot Encephalogram: Timeline Analysis")
    
    st.markdown("""
    <style>
        .delta-pos { color: green; font-weight: bold; }
        .delta-neg { color: red; font-weight: bold; }
        .mood-text { font-size: 1.2em; font-weight: bold; color: #222; background-color: #f0f2f6; padding: 5px 10px; border-radius: 5px;}
    </style>
    """, unsafe_allow_html=True)

    if st.sidebar.button("Refresh Data"):
        st.rerun()

    # Load Data
    with st.spinner("Reading Synaptic Logs..."):
        # FIX: Increased limit to 100 to show more history
        messages, metrics_logs = run_async(load_session_data(100))

    if not messages:
        st.warning("No data found.")
        st.stop()

    # Process Data
    timeline = []
    # Сортируем чтобы сопоставить сообщения и логи
    messages = sorted(messages, key=lambda x: x["created_at"])
    metrics_logs = sorted(metrics_logs, key=lambda x: x["timestamp"]) # Используем timestamp из метрик

    for i, msg in enumerate(messages):
        if msg["role"] == "assistant":
            user_text = messages[i-1]["content"] if i > 0 and messages[i-1]["role"] == "user" else "(No context)"
            bot_text = msg["content"]
            timestamp = msg["created_at"]
            
            matched_metric = None
            # Ищем ближайший лог (в пределах 5 сек)
            for m in metrics_logs:
                delta = (m["timestamp"] - timestamp).total_seconds()
                if abs(delta) < 5:
                    matched_metric = parse_metrics(m)
                    break
            
            if matched_metric:
                vad = extract_mood(matched_metric)
                timeline.append({
                    "time_str": timestamp.strftime("%H:%M:%S"),
                    "timestamp": timestamp, # Raw timestamp for plotting
                    "user": user_text,
                    "bot": bot_text,
                    "metrics": matched_metric,
                    "scores": extract_scores(matched_metric),
                    "hormones": extract_hormones(matched_metric),
                    "mood_vad": vad,
                    "mood_label": get_mood_label(matched_metric, vad),
                    "winner": get_winner_safe(matched_metric)
                })

    # Global Charts (Interactive Plotly)
    st.header("📈 Session Dynamics")
    if timeline:
        df_scores = pd.DataFrame([t["scores"] for t in timeline])
        df_scores["timestamp"] = [t["timestamp"] for t in timeline]
        
        df_hormones = pd.DataFrame([t["hormones"] for t in timeline])
        df_hormones["timestamp"] = [t["timestamp"] for t in timeline]

        c1, c2 = st.columns(2)
        with c1:
            st.subheader("Agent Activation Levels Over Time")
            # Convert to long format for Plotly Express
            df_scores_long = df_scores.melt(id_vars=["timestamp"], var_name="Agent", value_name="Score")
            fig_scores = px.line(
                df_scores_long, 
                x="timestamp", 
                y="Score", 
                color="Agent",
                # title="Agent Activation Levels Over Time",
                markers=True
            )
            fig_scores.update_layout(xaxis_title="Time", yaxis_title="Activation Score", hovermode="x unified")
            st.plotly_chart(fig_scores, width='stretch')
            
        with c2:
            st.subheader("Hormonal Levels Over Time")
            df_hormones_long = df_hormones.melt(id_vars=["timestamp"], var_name="Hormone", value_name="Level")
            fig_hormones = px.line(
                df_hormones_long, 
                x="timestamp", 
                y="Level", 
                color="Hormone",
                # title="Hormonal Levels Over Time",
                markers=True
            )
            fig_hormones.update_layout(xaxis_title="Time", yaxis_title="Concentration", hovermode="x unified")
            st.plotly_chart(fig_hormones, width='stretch')

    # Timeline Cards
    st.header("📅 Interaction History")
    # Обратный порядок для ленты
    for i in range(len(timeline)-1, -1, -1):
        item = timeline[i]
        prev_item = timeline[i-1] if i > 0 else None
        
        winner_display = item['winner']
        if winner_display == "Unknown": winner_display = "⚠️ Log Missing"

        with st.expander(f"⏰ {item['time_str']} | 🏆 {winner_display}", expanded=(i == len(timeline)-1)):
            c1, c2 = st.columns([1, 1])
            with c1:
                st.markdown(f"**👤 User:** {item['user']}")
                st.markdown(f"**🤖 Bot:** {item['bot']}")
                
                # --- Mood Section ---
                st.divider()
                st.markdown(f"<div class='mood-text'>{item['mood_label']}</div>", unsafe_allow_html=True)
                
                # VAD Metrics
                m_cols = st.columns(3)
                mood_order = ["Valence", "Arousal", "Dominance"]
                for idx, m_key in enumerate(mood_order):
                    val = item['mood_vad'].get(m_key, 0.0)
                    with m_cols[idx]:
                        st.metric(label=m_key, value=f"{val:.2f}")
                
                # ✨ PREDICTIVE PROCESSING STATS (NEW)
                if 'prediction_error' in item['metrics']:
                    st.divider()
                    pe = item['metrics'].get('prediction_error', 0.0)
                    next_pred = item['metrics'].get('next_prediction')
                    
                    pe_color = "red" if pe > 0.8 else "orange" if pe > 0.4 else "green"
                    st.markdown(f"**🔮 Prediction Error:** <span style='color:{pe_color}'>{pe:.4f}</span>", unsafe_allow_html=True)
                    if next_pred:
                        st.caption(f"Next Hypothesis: *{next_pred}*")

            with c2:
                # Scores
                st.markdown("### 📊 Council Votes")
                cols = st.columns(6) # Increase cols for Uncertainty
                agent_names = ["Amygdala", "Prefrontal", "Striatum", "Social", "Intuition", "Uncertainty"]
                for idx, agent in enumerate(agent_names):
                    val = item['scores'].get(agent, 0)
                    delta_str = ""
                    if prev_item:
                        diff = val - prev_item['scores'].get(agent, 0)
                        if abs(diff) > 0.1: delta_str = f"{diff:+.1f}"
                    
                    val_str = f"{val:.1f}"
                    if agent == item['winner']: val_str = f"🏆 {val:.1f}"
                         
                    with cols[idx]:
                        st.metric(label=agent[:4], value=val_str, delta=delta_str)
                
                # Hormones
                st.markdown("### ⚗️ Hormones")
                h_cols = st.columns(4)
                for idx, (h_name, h_val) in enumerate(item['hormones'].items()):
                    h_delta = ""
                    if prev_item:
                        diff = h_val - prev_item['hormones'].get(h_name, 0.5)
                        if abs(diff) > 0.01: h_delta = f"{diff:+.2f}"
                    with h_cols[idx]:
                        st.metric(label=h_name, value=f"{h_val:.2f}", delta=h_delta)

elif app_mode == "🧬 Brain Structure (Introspection)":
    st.title("🧬 Живая Архитектура (Introspection)")
    
    if not st.session_state.kernel_instance:
        st.warning("⚠️ Kernel not initialized. Please start a chat session first.")
    else:
        try:
            snapshot = st.session_state.kernel_instance.get_architecture_snapshot()
            
            # 1. Agents
            st.header("1. Активные Нейро-Агенты")
            st.caption("Компоненты, загруженные в Council System")
            
            cols = st.columns(len(snapshot["active_agents"]))
            for i, agent in enumerate(snapshot["active_agents"]):
                with cols[i]:
                    st.info(f"**{agent['name']}**\n\n`{agent['class']}`\n\n_{agent['description']}_")
            
            # 2. Subsystems
            st.header("2. Подсистемы")
            c1, c2, c3 = st.columns(3)
            c1.metric("Hippocampus", snapshot["subsystems"]["hippocampus"])
            c2.metric("Council Mode", snapshot["subsystems"]["council_mode"])
            c3.metric("Predictive Processing", snapshot["subsystems"]["predictive_processing"]) # ✨
            
            # 3. Hormonal Rules
            st.header("3. Гормональная Модуляция (Rules)")
            st.caption("Как эмоции (Archetypes) влияют на веса агентов")
            
            rules = snapshot["modulation_rules"]
            # Convert to DataFrame: Index = Archetype, Columns = AgentType
            rows = []
            for archetype, modifiers in rules.items():
                row = {"Archetype": archetype}
                for agent_enum, val in modifiers.items():
                    # agent_enum is typically an AgentType Enum, need .name
                    key = getattr(agent_enum, "name", str(agent_enum))
                    row[key] = val
                rows.append(row)
                
            df_rules = pd.DataFrame(rows).set_index("Archetype").fillna(1.0)
            st.dataframe(df_rules.style.background_gradient(cmap="coolwarm", vmin=0.0, vmax=2.0))
            
            # 4. Sliders (Current Config)
            st.header("4. Текущие веса (Sliders)")
            st.json(snapshot["control_sliders"])
            
        except Exception as e:
            st.error(f"Introspection failed: {e}")

else:
    # ==========================================
    #              CHAT INTERFACE
    # ==========================================
    
    # --- Sidebar Chat Controls ---
    st.sidebar.subheader("🤖 Bot Identity")
    try:
        available_agents = run_async(get_all_agents())
        agent_names = [a.name for a in available_agents]
    except Exception:
        agent_names = []

    selected_agent_name = st.sidebar.selectbox("Select Persona", ["Default"] + agent_names)

    # Reset kernel if persona changes
    if "last_agent_name" not in st.session_state:
        st.session_state.last_agent_name = selected_agent_name

    if st.session_state.last_agent_name != selected_agent_name:
        st.session_state.kernel_instance = None
        st.session_state.last_agent_name = selected_agent_name

    if selected_agent_name != "Default":
        st.session_state.bot_name = selected_agent_name
        agent_data = next((a for a in available_agents if a.name == selected_agent_name), None)
        if agent_data:
            st.session_state.bot_gender = agent_data.gender or "Neutral"
            st.sidebar.caption(f"📝 {agent_data.description} | {st.session_state.bot_gender}")
            preset = agent_data.sliders_preset
            st.session_state.sliders = PersonalitySliders(
                empathy_bias=preset.get("empathy_bias", 0.5),
                risk_tolerance=preset.get("risk_tolerance", 0.5),
                dominance_level=preset.get("dominance_level", 0.5),
                pace_setting=preset.get("pace_setting", 0.5),
                neuroticism=preset.get("neuroticism", 0.1),
                # ✨ NEW: Load Dashboard Controls
                chaos_level=preset.get("chaos_level", 0.2),
                learning_speed=preset.get("learning_speed", 0.5),
                persistence=preset.get("persistence", 0.5),
                # ✨ NEW: Load Pred Controls
                pred_threshold=preset.get("pred_threshold", 0.65), 
                pred_sensitivity=preset.get("pred_sensitivity", 10.0) 
            )
    else:
        st.session_state.bot_name = "R-Bot"
        st.session_state.bot_gender = "Neutral"

    # --- Sliders Control ---
    with st.sidebar.expander("Personality Tuner", expanded=False):
        st.markdown("### 🎭 Core Personality")
        empathy = st.slider("❤️ Empathy", 0.0, 1.0, st.session_state.sliders.empathy_bias)
        risk = st.slider("🎲 Risk / Curiosity", 0.0, 1.0, st.session_state.sliders.risk_tolerance)
        dominance = st.slider("👑 Dominance", 0.0, 1.0, st.session_state.sliders.dominance_level)
        pace = st.slider("⚡ Thinking Style", 0.0, 1.0, st.session_state.sliders.pace_setting)
        
        # ✨ NEW: Predictive Processing Sliders (Dashboard)
        st.markdown("### 🎛️ Neuro-Dynamics")
        st.caption("Homeostasis & Adaptation")
        chaos_level = st.slider("🌪️ Chaos Level (Entropy)", 0.0, 1.0, st.session_state.sliders.chaos_level, help="Стабильность vs Хаос. Повышает Uncertainty.")
        learning_speed = st.slider("🧠 Learning Speed (Plasticity)", 0.0, 1.0, st.session_state.sliders.learning_speed, help="Скорость обновления весов (RL Rate).")
        persistence = st.slider("🔋 Persistence (Willpower)", 0.0, 1.0, st.session_state.sliders.persistence, help="Упорство в достижении целей (Fuel).")
        
        st.markdown("---")
        st.caption("🔮 Predictive Error Params")
        pred_thresh = st.slider("Threshold (µ)", 0.1, 1.0, st.session_state.sliders.pred_threshold, help="Порог 'хорошей' ошибки. Выше = бот реже паникует.")
        pred_sens = st.slider("Sensitivity (k)", 1.0, 20.0, st.session_state.sliders.pred_sensitivity, help="Резкость реакции. Выше = сильнее награда/штраф.")
        
        use_unified_council = st.checkbox("🔄 Unified Council", value=False)

        st.session_state.sliders = PersonalitySliders(
            empathy_bias=empathy,
            risk_tolerance=risk,
            dominance_level=dominance,
            pace_setting=pace,
            neuroticism=0.1,
            # ✨ NEW fields
            chaos_level=chaos_level,
            learning_speed=learning_speed,
            persistence=persistence,
            pred_threshold=pred_thresh,
            pred_sensitivity=pred_sens
        )

    # --- Save Agent ---
    with st.sidebar.expander("💾 Save New Persona"):
        with st.form("new_agent_form"):
            new_name = st.text_input("Name")
            new_desc = st.text_input("Description")
            new_gender = st.selectbox("Gender", ["Neutral", "Male", "Female"])
            if st.form_submit_button("Create"):
                if new_name:
                    sliders_dict = {
                        "empathy_bias": empathy, "risk_tolerance": risk,
                        "dominance_level": dominance, "pace_setting": pace, "neuroticism": 0.1,
                        "chaos_level": chaos_level, "learning_speed": learning_speed, "persistence": persistence, # ✨ Save
                        "pred_threshold": pred_thresh, "pred_sensitivity": pred_sens
                    }
                    run_async(create_agent(new_name, new_desc, new_gender, sliders_dict))
                    st.success(f"Agent {new_name} saved!")
                    st.rerun()

    test_mode = st.sidebar.radio("🧪 Mode", ["Standard", "A/B Test"])
    
    if st.sidebar.button("Clear Chat"):
        st.session_state.messages = []
        st.session_state.kernel_instance = None
        st.rerun()

    # --- CHAT AREA ---
    st.title("R-Bot: Cognitive Architecture Debugger")
    st.markdown(f"Current Agent: **{st.session_state.bot_name}**")

    # Mood Dashboard (Top of Chat)
    if st.session_state.kernel_instance and hasattr(st.session_state.kernel_instance, 'current_mood'):
        m = st.session_state.kernel_instance.current_mood
        st.caption("Current Brain State (VAD)")
        c1, c2, c3 = st.columns(3)
        c1.metric("Valence", f"{m.valence:.2f}", help="Pleasure (+1) vs Displeasure (-1)")
        c2.metric("Arousal", f"{m.arousal:.2f}", help="Excitement (+1) vs Calm (-1)")
        c3.metric("Dominance", f"{m.dominance:.2f}", help="Control (+1) vs Submission (-1)")
        st.divider()

    # Chat History
    for msg in st.session_state.messages:
        if msg.get("type") == "ab_test":
            with st.chat_message(msg["role"]): st.write(f"**User:** {msg['content']}")
            c_c, c_z = st.columns(2)
            with c_c:
                st.info("🧠 Cortical"); st.write(msg["cortical_text"]); st.caption(f"{msg['cortical_latency']}ms")
            with c_z:
                st.warning("🧟 Zombie"); st.write(msg["zombie_text"]); st.caption(f"{msg['zombie_latency']}ms")
            st.divider()
        else:
            with st.chat_message(msg["role"]):
                st.write(msg["content"])
                if msg["role"] == "assistant" and "meta" in msg:
                    stats = msg["meta"]
                    w_name = msg.get("winner", "Unknown")
                    caption = f"🏆 Winner: **{w_name}**"
                    if stats.get("sentiment_context_used"): caption += " | 💚 Sentiment Used"
                    st.caption(caption)
                    
                    if "all_scores" in stats:
                        scores_df = pd.DataFrame([{"Agent": k, "Score": v} for k, v in stats["all_scores"].items()])
                        chart = alt.Chart(scores_df).mark_bar(size=15).encode(
                            x=alt.X('Score', scale=alt.Scale(domain=[0, 10])),
                            y=alt.Y('Agent', sort='-x'),
                            color=alt.condition(alt.datum.Agent == w_name, alt.value('orange'), alt.value('lightgray'))).properties(height=150)
                        st.altair_chart(chart, width='stretch')

    # Input
    user_input = st.chat_input("Say something...")
    if user_input:
        # Init Kernel
        if st.session_state.kernel_instance is None:
            # FIX: Use empty lists for values if needed, but ensure config is valid
            config = BotConfig(character_id="streamlit_user", name=st.session_state.bot_name, sliders=st.session_state.sliders, core_values=[], use_unified_council=use_unified_council)
            config.gender = st.session_state.bot_gender
            st.session_state.kernel_instance = RCoreKernel(config)
        else:
            st.session_state.kernel_instance.config.name = st.session_state.bot_name
            st.session_state.kernel_instance.config.sliders = st.session_state.sliders
            st.session_state.kernel_instance.config.use_unified_council = use_unified_council

        kernel = st.session_state.kernel_instance
        # FIX: ADD MESSAGE_ID
        incoming = IncomingMessage(
            user_id=999, 
            session_id="streamlit_session", 
            text=user_input,
            message_id=str(uuid.uuid4()) # ✨ ADDED
        )

        if test_mode == "A/B Test":
            with st.chat_message("user"): st.write(user_input)
            c1, c2 = st.columns(2)
            with c1, st.spinner("🧠 Cortical..."):
                resp_c = run_async(kernel.process_message(incoming, mode="CORTICAL"))
                st.info("Cortical"); st.write(resp_c.actions[0].payload['text'])
            with c2, st.spinner("🧟 Zombie..."):
                resp_z = run_async(kernel.process_message(incoming, mode="ZOMBIE"))
                st.warning("Zombie"); st.write(resp_z.actions[0].payload['text'])
            
            st.session_state.messages.append({
                "type": "ab_test", "role": "user", "content": user_input,
                "cortical_text": resp_c.actions[0].payload['text'], "cortical_latency": resp_c.internal_stats['latency_ms'],
                "zombie_text": resp_z.actions[0].payload['text'], "zombie_latency": resp_z.internal_stats['latency_ms']
            })
        else:
            st.session_state.messages.append({"role": "user", "content": user_input})
            with st.chat_message("user"): st.write(user_input)
            
            with st.spinner("Thinking..."):
                try:
                    response = run_async(kernel.process_message(incoming, mode="CORTICAL"))
                    bot_text = response.actions[0].payload['text']
                    stats = response.internal_stats
                    
                    with st.chat_message("assistant"):
                        st.write(bot_text)
                        st.caption(f"🏆 Winner: {response.winning_agent.value}")
                        
                        if "all_scores" in stats:
                            scores_df = pd.DataFrame([{"Agent": k, "Score": v} for k, v in stats["all_scores"].items()])
                            chart = alt.Chart(scores_df).mark_bar(size=15).encode(
                                x=alt.X('Score', scale=alt.Scale(domain=[0, 10])),
                                y=alt.Y('Agent', sort='-x'),
                                color=alt.condition(alt.datum.Agent == response.winning_agent.value, alt.value('orange'), alt.value('lightgray'))
                            ).properties(height=150)
                            st.altair_chart(chart, width='stretch')

                    st.session_state.messages.append({
                        "role": "assistant", "content": bot_text,
                        "meta": stats, "winner": response.winning_agent.value
                    })
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")
