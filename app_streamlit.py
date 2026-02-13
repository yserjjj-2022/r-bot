import asyncio
import streamlit as st
import pandas as pd
import altair as alt
import json
import plotly.graph_objects as go
from typing import Dict, Any, List
from datetime import datetime
from sqlalchemy import select, delete, text
from src.r_core.schemas import BotConfig, PersonalitySliders, IncomingMessage
from src.r_core.pipeline import RCoreKernel
from src.r_core.memory import MemorySystem
from src.r_core.infrastructure.db import init_models, AsyncSessionLocal, AgentProfileModel, UserProfileModel, SemanticModel, get_async_session_maker
from src.r_core.config import settings

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
        neuroticism=0.1
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
async def load_session_data(limit=50):
    """Загружает историю диалога и метрики, объединяя их по времени"""
    SessionLocal = get_async_session_maker()
    async with SessionLocal() as session:
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
        
        # Загружаем метрики
        metrics_result = await session.execute(
            text("""
                SELECT session_id, timestamp as created_at, payload, affective_triggers_detected, sentiment_context_used
                FROM rcore_metrics
                ORDER BY timestamp DESC
                LIMIT :limit
            """),
            {"limit": limit}
        )
        metrics = metrics_result.mappings().all()
    return messages, metrics

def parse_metrics(metrics_row):
    try:
        data = metrics_row["payload"]
        if isinstance(data, str):
            data = json.loads(data)
        elif data is None:
            data = {}
            
        # Добавляем специфичные поля
        data["affective_triggers_detected"] = metrics_row.get("affective_triggers_detected", 0)
        data["sentiment_context_used"] = metrics_row.get("sentiment_context_used", False)
        
        return data
    except Exception as e:
        print(f"Error parsing metrics: {e}")
        return {}

def extract_scores(metrics_data):
    scores = metrics_data.get("all_scores", {})
    if not scores:
        # Fallback 1: может быть в другом формате?
        return {"Amygdala": 0, "Prefrontal": 0, "Striatum": 0, "Social": 0, "Intuition": 0}
    return scores

def extract_hormones(metrics_data):
    h_str = metrics_data.get("hormonal_state", "")
    h_map = {"NE": 0.5, "DA": 0.5, "5HT": 0.5, "CORT": 0.5}
    if isinstance(h_str, str) and "NE:" in h_str:
        parts = h_str.split(" ")
        for p in parts:
            if ":" in p:
                k, v = p.split(":")
                try:
                    h_map[k] = float(v)
                except:
                    pass
    return h_map

def extract_mood(metrics_data):
    """Извлекает VAD (Mood) из метрик"""
    # Обычно это лежит в current_mood: "Valence: 0.5, Arousal: ..." или объект
    mood_str = metrics_data.get("current_mood", "")
    vad = {"Valence": 0.0, "Arousal": 0.0, "Dominance": 0.0}
    
    if isinstance(mood_str, str):
        # Парсим строку вида "Valence: 0.85, Arousal: 0.42, Dominance: 0.65"
        try:
            parts = mood_str.split(",")
            for p in parts:
                k, v = p.strip().split(":")
                if k in vad:
                    vad[k] = float(v)
        except:
            pass
    elif isinstance(mood_str, dict):
         vad.update(mood_str)
         
    return vad

def get_winner_safe(metrics_data):
    # Пытаемся найти победителя в разных полях
    w = metrics_data.get("winner_agent")
    if not w:
        w = metrics_data.get("winning_agent") # sometimes stored differently
    if not w:
        w = metrics_data.get("winner")
        
    return w or "Unknown"

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
app_mode = st.sidebar.radio("Navigation", ["💬 Chat Interface", "📈 Encephalogram (Analytics)"])
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
    </style>
    """, unsafe_allow_html=True)

    if st.sidebar.button("Refresh Data"):
        st.rerun()

    # Load Data
    with st.spinner("Reading Synaptic Logs..."):
        messages, metrics_logs = run_async(load_session_data(30))

    if not messages:
        st.warning("No data found.")
        st.stop()

    # Process Data
    timeline = []
    messages = sorted(messages, key=lambda x: x["created_at"])
    metrics_logs = sorted(metrics_logs, key=lambda x: x["created_at"])

    for i, msg in enumerate(messages):
        if msg["role"] == "assistant":
            user_text = messages[i-1]["content"] if i > 0 and messages[i-1]["role"] == "user" else "(No context)"
            bot_text = msg["content"]
            timestamp = msg["created_at"]
            
            matched_metric = None
            for m in metrics_logs:
                delta = (m["created_at"] - timestamp).total_seconds()
                if abs(delta) < 5:
                    matched_metric = parse_metrics(m)
                    break
            
            if matched_metric:
                timeline.append({
                    "time": timestamp.strftime("%H:%M:%S"),
                    "user": user_text,
                    "bot": bot_text,
                    "metrics": matched_metric,
                    "scores": extract_scores(matched_metric),
                    "hormones": extract_hormones(matched_metric),
                    "mood": extract_mood(matched_metric),
                    "winner": get_winner_safe(matched_metric)
                })

    # Global Charts
    st.header("📈 Session Dynamics")
    if timeline:
        df_scores = pd.DataFrame([t["scores"] for t in timeline])
        df_scores["time"] = [t["time"] for t in timeline]
        
        df_hormones = pd.DataFrame([t["hormones"] for t in timeline])
        df_hormones["time"] = [t["time"] for t in timeline]
        
        df_mood = pd.DataFrame([t["mood"] for t in timeline])
        df_mood["time"] = [t["time"] for t in timeline]

        c1, c2 = st.columns(2)
        with c1:
            st.subheader("Agent Conflict")
            st.line_chart(df_scores.set_index("time"))
        with c2:
            st.subheader("Biochemistry & Mood")
            st.line_chart(df_hormones.set_index("time"))
            # Можно добавить и Mood на график, но пока ограничимся этим

    # Timeline Cards
    st.header("📅 Interaction History")
    for i in range(len(timeline)-1, -1, -1):
        item = timeline[i]
        prev_item = timeline[i-1] if i > 0 else None
        
        with st.expander(f"⏰ {item['time']} | 🏆 Winner: {item['winner']}", expanded=(i == len(timeline)-1)):
            c1, c2 = st.columns([1, 1])
            with c1:
                st.markdown(f"**👤 User:** {item['user']}")
                st.markdown(f"**🤖 Bot:** {item['bot']}")
                volition = item['metrics'].get("volition_selected")
                if volition:
                    st.success(f"🛡️ **Volition Active:** {volition}")
                
                # --- NEW: Mood Section ---
                st.markdown("### 🎭 Current Mood")
                m_cols = st.columns(3)
                mood_order = ["Valence", "Arousal", "Dominance"]
                for idx, m_key in enumerate(mood_order):
                    val = item['mood'].get(m_key, 0.0)
                    with m_cols[idx]:
                        st.metric(label=m_key, value=f"{val:.2f}")

            with c2:
                # Scores
                st.markdown("### 📊 Council Votes")
                cols = st.columns(5)
                agent_names = ["Amygdala", "Prefrontal", "Striatum", "Social", "Intuition"]
                for idx, agent in enumerate(agent_names):
                    val = item['scores'].get(agent, 0)
                    delta_str = ""
                    if prev_item:
                        diff = val - prev_item['scores'].get(agent, 0)
                        if abs(diff) > 0.1: delta_str = f"{diff:+.1f}"
                    
                    # Highlight winner visually
                    color = "normal"
                    if agent == item['winner']:
                         val_str = f"🏆 {val:.1f}"
                    else:
                         val_str = f"{val:.1f}"
                         
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
                neuroticism=preset.get("neuroticism", 0.1)
            )
    else:
        st.session_state.bot_name = "R-Bot"
        st.session_state.bot_gender = "Neutral"

    # --- Sliders Control ---
    with st.sidebar.expander("Personality Tuner", expanded=False):
        empathy = st.slider("❤️ Empathy", 0.0, 1.0, st.session_state.sliders.empathy_bias)
        risk = st.slider("🎲 Risk / Curiosity", 0.0, 1.0, st.session_state.sliders.risk_tolerance)
        dominance = st.slider("👑 Dominance", 0.0, 1.0, st.session_state.sliders.dominance_level)
        pace = st.slider("⚡ Thinking Style", 0.0, 1.0, st.session_state.sliders.pace_setting)
        
        use_unified_council = st.checkbox("🔄 Unified Council", value=False)

        st.session_state.sliders = PersonalitySliders(
            empathy_bias=empathy,
            risk_tolerance=risk,
            dominance_level=dominance,
            pace_setting=pace,
            neuroticism=0.1
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
                        "dominance_level": dominance, "pace_setting": pace, "neuroticism": 0.1
                    }
                    run_async(create_agent(new_name, new_desc, new_gender, sliders_dict))
                    st.success(f"Agent {new_name} saved!")
                    st.rerun()

    test_mode = st.sidebar.radio("🧪 Mode", ["Standard", "A/B Test"])
    
    # --- User Profile ---
    st.sidebar.divider()
    if "profile_loaded" not in st.session_state:
        try:
            data = run_async(get_profile_data())
            st.session_state.user_profile_data = data or {}
            st.session_state.profile_loaded = True
        except Exception:
            st.session_state.user_profile_data = {}

    with st.sidebar.expander("👤 User Identity"):
        with st.form("profile_form"):
            p_name = st.text_input("Name", st.session_state.user_profile_data.get("name", ""))
            curr_mode = st.session_state.user_profile_data.get("preferred_mode", "formal")
            p_mode = st.selectbox("Style", ["formal", "informal"], index=0 if curr_mode=="formal" else 1)
            if st.form_submit_button("Save"):
                run_async(update_profile_data({"name": p_name, "preferred_mode": p_mode}))
                st.session_state.user_profile_data.update({"name": p_name, "preferred_mode": p_mode})
                st.success("Saved!")

    # --- Affective Memory (Collapsed by default) ---
    st.sidebar.subheader("💚 Emotional Memory")
    # FIX: expanded=False by default
    with st.sidebar.expander("View User Preferences", expanded=False):
        try:
            affective_data = run_async(get_affective_memory(999))
            if affective_data:
                for item in affective_data:
                    pred = item["predicate"]
                    emoji = "🔴" if pred in ["HATES", "DESPISES"] else "💚" if pred in ["LOVES", "ADORES"] else "⚪"
                    st.caption(f"{emoji} {pred} {item['object']}")
            else:
                st.caption("No emotional data yet.")
        except Exception:
            pass

    if st.sidebar.button("Clear Chat"):
        st.session_state.messages = []
        st.session_state.kernel_instance = None
        st.rerun()

    # --- CHAT AREA ---
    st.title("R-Bot: Cognitive Architecture Debugger")
    st.markdown(f"Current Agent: **{st.session_state.bot_name}**")

    # Mood Dashboard
    if st.session_state.kernel_instance and hasattr(st.session_state.kernel_instance, 'current_mood'):
        m = st.session_state.kernel_instance.current_mood
        c1, c2, c3 = st.columns(3)
        c1.metric("Valence", f"{m.valence:.2f}")
        c2.metric("Arousal", f"{m.arousal:.2f}")
        c3.metric("Dominance", f"{m.dominance:.2f}")
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
                        # FIX: Use scale=alt.Scale(domain=[...]) instead of direct domain=...
                        chart = alt.Chart(scores_df).mark_bar(size=15).encode(
                            x=alt.X('Score', scale=alt.Scale(domain=[0, 10])),
                            y=alt.Y('Agent', sort='-x'),
                            color=alt.condition(alt.datum.Agent == w_name, alt.value('orange'), alt.value('lightgray'))
                        ).properties(height=150)
                        st.altair_chart(chart, use_container_width=True)

    # Input
    user_input = st.chat_input("Say something...")
    if user_input:
        # Init Kernel
        if st.session_state.kernel_instance is None:
            config = BotConfig(character_id="streamlit_user", name=st.session_state.bot_name, sliders=st.session_state.sliders, core_values=[], use_unified_council=use_unified_council)
            config.gender = st.session_state.bot_gender
            st.session_state.kernel_instance = RCoreKernel(config)
        else:
            st.session_state.kernel_instance.config.name = st.session_state.bot_name
            st.session_state.kernel_instance.config.sliders = st.session_state.sliders
            st.session_state.kernel_instance.config.use_unified_council = use_unified_council

        kernel = st.session_state.kernel_instance
        incoming = IncomingMessage(user_id=999, session_id="streamlit_session", text=user_input)

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
                            # FIX: Use scale=alt.Scale(domain=[...])
                            chart = alt.Chart(scores_df).mark_bar(size=15).encode(
                                x=alt.X('Score', scale=alt.Scale(domain=[0, 10])),
                                y=alt.Y('Agent', sort='-x'),
                                color=alt.condition(alt.datum.Agent == response.winning_agent.value, alt.value('orange'), alt.value('lightgray'))
                            ).properties(height=150)
                            st.altair_chart(chart, use_container_width=True)

                    st.session_state.messages.append({
                        "role": "assistant", "content": bot_text,
                        "meta": stats, "winner": response.winning_agent.value
                    })
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")
