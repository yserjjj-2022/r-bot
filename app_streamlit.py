import asyncio
import streamlit as st
import pandas as pd
import altair as alt
from typing import Dict, Any
from sqlalchemy import select, delete
from src.r_core.schemas import BotConfig, PersonalitySliders, IncomingMessage
from src.r_core.pipeline import RCoreKernel
from src.r_core.memory import MemorySystem
from src.r_core.infrastructure.db import init_models, AsyncSessionLocal, AgentProfileModel, UserProfileModel, SemanticModel
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

async def delete_agent_by_name(name: str):
    async with AsyncSessionLocal() as session:
        stmt = delete(AgentProfileModel).where(AgentProfileModel.name == name)
        await session.execute(stmt)
        await session.commit()

# ✨ NEW: Get Affective Memory (User's Emotional Preferences)
async def get_affective_memory(user_id: int = 999):
    """Получить список эмоционально окрашенных объектов из памяти"""
    async with AsyncSessionLocal() as session:
        stmt = select(SemanticModel).where(
            SemanticModel.user_id == user_id,
            SemanticModel.sentiment.isnot(None)
        ).order_by(SemanticModel.created_at.desc()).limit(20)
        
        result = await session.execute(stmt)
        rows = result.scalars().all()
        
        return [
            {
                "subject": r.subject,
                "predicate": r.predicate,
                "object": r.object,
                "sentiment": r.sentiment,
                "created_at": r.created_at
            }
            for r in rows
        ]

# --- Sidebar ---
st.sidebar.title("🧠 Cortex Controls")

# --- Agent Selector ---
st.sidebar.subheader("🤖 Bot Identity")

try:
    available_agents = run_async(get_all_agents())
    agent_names = [a.name for a in available_agents]
except Exception:
    agent_names = []

selected_agent_name = st.sidebar.selectbox(
    "Select Persona", 
    ["Default"] + agent_names
)

# Reset kernel if persona changes
if "last_agent_name" not in st.session_state:
    st.session_state.last_agent_name = selected_agent_name

if st.session_state.last_agent_name != selected_agent_name:
    st.session_state.kernel_instance = None # Force reset to clear mood
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
st.sidebar.markdown("### Fine-tune Personality")

empathy = st.sidebar.slider(
    "❤️ Empathy (Social Cortex)", 
    0.0, 1.0, st.session_state.sliders.empathy_bias,
    help="High: Prioritizes feelings, politeness, and relationships.\nLow: Prioritizes facts and dry efficiency."
)

risk = st.sidebar.slider(
    "🎲 Risk / Curiosity (Striatum)", 
    0.0, 1.0, st.session_state.sliders.risk_tolerance,
    help="High: Seeks novelty, fun, gamification. Playful.\nLow: Cautious, safe, predictable (Amygdala dominance)."
)

dominance = st.sidebar.slider(
    "👑 Dominance (PFC/Amygdala)", 
    0.0, 1.0, st.session_state.sliders.dominance_level,
    help="High: Leader, assertive, directive.\nLow: Assistant, submissive, helpful."
)

pace = st.sidebar.slider(
    "⚡ Pace (Intuition vs Logic)", 
    0.0, 1.0, st.session_state.sliders.pace_setting,
    help="High (1.0): Logic heavy (System 2). Thoughtful, slow.\nLow (0.0): Intuition heavy (System 1). Fast, heuristic."
)

st.session_state.sliders = PersonalitySliders(
    empathy_bias=empathy,
    risk_tolerance=risk,
    dominance_level=dominance,
    pace_setting=pace,
    neuroticism=0.1
)

# --- Save New Agent Form ---
with st.sidebar.expander("💾 Save as New Agent"):
    with st.form("new_agent_form"):
        new_name = st.text_input("Name (e.g. Jarvis)")
        new_desc = st.text_input("Description (e.g. Polite Butler)")
        new_gender = st.selectbox("Gender", ["Neutral", "Male", "Female"])
        
        if st.form_submit_button("Create"):
            if new_name:
                sliders_dict = {
                    "empathy_bias": empathy,
                    "risk_tolerance": risk,
                    "dominance_level": dominance,
                    "pace_setting": pace,
                    "neuroticism": 0.1
                }
                run_async(create_agent(new_name, new_desc, new_gender, sliders_dict))
                st.success(f"Agent {new_name} saved!")
                st.rerun()

st.sidebar.divider()

# ✨ NEW: Test Mode Switcher
test_mode = st.sidebar.radio(
    "🧪 Experiment Mode",
    ["Standard (Cortical)", "A/B Test (Zombie vs Cortical)"],
    help="A/B Test runs two models in parallel: Your sophisticated Cortical Brain vs a dumb Zombie LLM."
)

st.sidebar.divider()

# --- User Profile Section ---
st.sidebar.subheader("👤 User Identity")

async def get_profile_data():
    mem = MemorySystem()
    return await mem.store.get_user_profile(999) 

async def update_profile_data(data):
    mem = MemorySystem()
    await mem.update_user_profile(999, data)

if "profile_loaded" not in st.session_state:
    try:
        data = run_async(get_profile_data())
        st.session_state.user_profile_data = data or {}
        st.session_state.profile_loaded = True
    except Exception:
        st.session_state.user_profile_data = {}

with st.sidebar.expander("Edit User Profile", expanded=False):
    with st.form("profile_form"):
        p_name = st.text_input("Name", st.session_state.user_profile_data.get("name", ""))
        
        g_opts = ["", "Male", "Female", "Neutral"]
        curr_g = st.session_state.user_profile_data.get("gender", "")
        g_idx = g_opts.index(curr_g) if curr_g in g_opts else 0
        p_gender = st.selectbox("Gender", g_opts, index=g_idx)
        
        m_opts = ["formal", "informal"]
        curr_m = st.session_state.user_profile_data.get("preferred_mode", "formal")
        m_idx = m_opts.index(curr_m) if curr_m in m_opts else 0
        p_mode = st.selectbox("Address Style", m_opts, index=m_idx)
        
        if st.form_submit_button("Save Identity"):
            new_data = {"name": p_name, "gender": p_gender, "preferred_mode": p_mode}
            run_async(update_profile_data(new_data))
            st.session_state.user_profile_data = new_data
            st.success("Saved!")

st.sidebar.divider()

# ✨ NEW: Affective Memory Display in Sidebar
st.sidebar.subheader("💚 Emotional Memory")
with st.sidebar.expander("View User Preferences", expanded=False):
    try:
        affective_data = run_async(get_affective_memory(999))
        
        if affective_data:
            for item in affective_data:
                sentiment = item["sentiment"]
                valence = sentiment.get("valence", 0.0)
                
                # Эмодзи на основе predicate и valence
                if item["predicate"] in ["HATES", "DESPISES"]:
                    emoji = "🔴"
                elif item["predicate"] == "FEARS":
                    emoji = "😨"
                elif item["predicate"] in ["LOVES", "ADORES"]:
                    emoji = "💚"
                elif item["predicate"] == "ENJOYS":
                    emoji = "😊"
                else:
                    emoji = "⚪"
                
                st.caption(f"{emoji} **{item['predicate']}** {item['object']} (V: {valence:.2f})")
        else:
            st.info("No emotional preferences stored yet.\nTry saying 'I hate X' or 'I love Y'")
    except Exception as e:
        st.error(f"Error loading affective memory: {e}")

st.sidebar.divider()

if st.sidebar.button("Initialize DB"):
    with st.spinner("Creating tables..."):
        try:
            run_async(init_models())
            st.sidebar.success("DB Ready!")
        except Exception as e:
            st.sidebar.error(f"DB Error: {e}")

if st.sidebar.button("Clear Memory & Chat"):
    st.session_state.messages = []
    st.session_state.kernel_instance = None # RESET KERNEL MOOD
    st.rerun()

# --- Main Chat Area ---

st.title("R-Bot: Cognitive Architecture Debugger")
st.markdown(f"Current Agent: **{st.session_state.bot_name}** ({st.session_state.bot_gender})")

# --- Mood Dashboard (Top) ---
if st.session_state.kernel_instance and hasattr(st.session_state.kernel_instance, 'current_mood'):
    m = st.session_state.kernel_instance.current_mood
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Valence (Joy)", f"{m.valence:.2f}", delta_color="normal", help="Pos: Happy/Warm\nNeg: Sad/Cold")
    with col2:
        st.metric("Arousal (Energy)", f"{m.arousal:.2f}", delta_color="normal", help="High: Excited/Angry\nLow: Calm/Bored")
    with col3:
        st.metric("Dominance (Control)", f"{m.dominance:.2f}", delta_color="normal", help="High: Leader\nLow: Follower")
    st.divider()

# Display history
for msg in st.session_state.messages:
    if msg.get("type") == "ab_test":
        # A/B TEST DISPLAY
        with st.chat_message(msg["role"]):
            st.write(f"**User:** {msg['content']}") # User input repetition
        
        col_c, col_z = st.columns(2)
        with col_c:
            st.info("🧠 **Cortical (R-Bot)**")
            st.write(msg["cortical_text"])
            st.caption(f"Latency: {msg['cortical_latency']}ms")
        with col_z:
            st.warning("🧟 **Zombie Mode**")
            st.write(msg["zombie_text"])
            st.caption(f"Latency: {msg['zombie_latency']}ms")
        st.divider()
        
    else:
        # STANDARD DISPLAY
        with st.chat_message(msg["role"]):
            st.write(msg["content"])
            
            if msg["role"] == "assistant" and "meta" in msg:
                stats = msg["meta"]
                
                # ✨ NEW: Highlight affective context usage
                affective_triggers = stats.get("affective_triggers_detected", 0)
                sentiment_used = stats.get("sentiment_context_used", False)
                
                winner_caption = f"🏆 Winner: **{msg['winner']}** ({stats['winner_score']}/10)"
                
                if sentiment_used:
                    winner_caption += f" | 💚 Sentiment Context Used ({affective_triggers} triggers)"
                
                # Show active style if available
                active_style = stats.get("active_style", "")
                tooltip_text = f"Winner: {msg['winner']}"
                if active_style:
                    tooltip_text += f"\n\nStyle Instructions:\n{active_style}"

                st.caption(winner_caption, help=tooltip_text)
                
                if "all_scores" in stats:
                    scores_df = pd.DataFrame([
                        {"Agent": k, "Score": v} 
                        for k, v in stats["all_scores"].items()
                    ])
                    chart = alt.Chart(scores_df).mark_bar(size=15).encode(
                        x=alt.X('Score', scale=alt.Scale(domain=[0, 10])),
                        y=alt.Y('Agent', sort='-x'),
                        color=alt.condition(
                            alt.datum.Agent == msg['winner'],
                            alt.value('orange'),
                            alt.value('lightgray')
                        ),
                        tooltip=['Agent', 'Score']
                    ).properties(height=150)
                    st.altair_chart(chart, use_container_width=True)
                
                with st.expander("Technical Details"):
                    st.json(stats)

# Input
user_input = st.chat_input("Say something...")

if user_input:
    
    # Initialize Kernel
    if st.session_state.kernel_instance is None:
            config = BotConfig(
            character_id="streamlit_user", 
            name=st.session_state.bot_name, 
            sliders=st.session_state.sliders, 
            core_values=[]
        )
            config.gender = st.session_state.bot_gender
            st.session_state.kernel_instance = RCoreKernel(config)
    else:
            st.session_state.kernel_instance.config.name = st.session_state.bot_name
            st.session_state.kernel_instance.config.gender = st.session_state.bot_gender
            st.session_state.kernel_instance.config.sliders = st.session_state.sliders

    kernel = st.session_state.kernel_instance
    incoming = IncomingMessage(
        user_id=999, 
        session_id="streamlit_session",
        text=user_input
    )

    if test_mode == "A/B Test (Zombie vs Cortical)":
        # --- A/B LOGIC ---
        with st.chat_message("user"):
            st.write(user_input)
            
        col_cortical, col_zombie = st.columns(2)
        
        with col_cortical:
            with st.spinner("🧠 Cortical Thinking..."):
                resp_cortical = run_async(kernel.process_message(incoming, mode="CORTICAL"))
                st.info("🧠 **Cortical (R-Bot)**")
                st.write(resp_cortical.actions[0].payload['text'])
                st.caption(f"Latency: {resp_cortical.internal_stats['latency_ms']}ms")
        
        with col_zombie:
            with st.spinner("🧟 Zombie Generating..."):
                resp_zombie = run_async(kernel.process_message(incoming, mode="ZOMBIE"))
                st.warning("🧟 **Zombie Mode**")
                st.write(resp_zombie.actions[0].payload['text'])
                st.caption(f"Latency: {resp_zombie.internal_stats['latency_ms']}ms")
        
        # Save composite message for history display
        st.session_state.messages.append({
            "type": "ab_test",
            "role": "user", # display hack
            "content": user_input,
            "cortical_text": resp_cortical.actions[0].payload['text'],
            "cortical_latency": resp_cortical.internal_stats['latency_ms'],
            "zombie_text": resp_zombie.actions[0].payload['text'],
            "zombie_latency": resp_zombie.internal_stats['latency_ms']
        })
        
    else:
        # --- STANDARD LOGIC ---
        st.session_state.messages.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.write(user_input)

        with st.spinner(f"{st.session_state.bot_name} is thinking..."):
            try:
                response = run_async(kernel.process_message(incoming, mode="CORTICAL"))
                
                bot_text = response.actions[0].payload['text']
                stats = response.internal_stats
                winner_name = response.winning_agent.value

                with st.chat_message("assistant"):
                    st.write(bot_text)
                    
                    # ✨ NEW: Show affective context indicator
                    affective_triggers = stats.get("affective_triggers_detected", 0)
                    sentiment_used = stats.get("sentiment_context_used", False)
                    
                    caption_text = f"🏆 Winner: **{winner_name}**"
                    if sentiment_used:
                        caption_text += f" | 💚 Sentiment Context Used ({affective_triggers} triggers)"
                    
                    st.caption(caption_text)
                    
                    # Show Chart
                    if "all_scores" in stats:
                        scores_df = pd.DataFrame([
                            {"Agent": k, "Score": v} 
                            for k, v in stats["all_scores"].items()
                        ])
                        chart = alt.Chart(scores_df).mark_bar(size=15).encode(
                            x=alt.X('Score', scale=alt.Scale(domain=[0, 10])),
                            y=alt.Y('Agent', sort='-x'),
                            color=alt.condition(
                                alt.datum.Agent == winner_name,
                                alt.value('orange'),
                                alt.value('lightgray')
                            )
                        ).properties(height=150)
                        st.altair_chart(chart, use_container_width=True)

                st.session_state.messages.append({
                    "role": "assistant", 
                    "content": bot_text, 
                    "meta": stats,
                    "winner": winner_name
                })
                
                # Force UI update to show new mood metrics at top
                st.rerun() 
                
            except Exception as e:
                st.error(f"Kernel Panic: {e}")
                st.error("Please check console logs.")
