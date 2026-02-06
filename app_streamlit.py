import asyncio
import streamlit as st
import pandas as pd
import altair as alt
from src.r_core.schemas import BotConfig, PersonalitySliders, IncomingMessage
from src.r_core.pipeline import RCoreKernel
from src.r_core.memory import MemorySystem # Added import
from src.r_core.infrastructure.db import init_models
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

def run_async(coro):
    try:
        return asyncio.run(coro)
    except RuntimeError:
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(coro)

# --- Sidebar ---
st.sidebar.title("🧠 Cortex Controls")
st.sidebar.markdown("Adjust the bot's personality live.")

empathy = st.sidebar.slider("Empathy Bias (Social vs Logic)", 0.0, 1.0, st.session_state.sliders.empathy_bias)
risk = st.sidebar.slider("Risk Tolerance (Striatum vs Amygdala)", 0.0, 1.0, st.session_state.sliders.risk_tolerance)
dominance = st.sidebar.slider("Dominance", 0.0, 1.0, st.session_state.sliders.dominance_level)
pace = st.sidebar.slider("Pace (Intuition Speed)", 0.0, 1.0, st.session_state.sliders.pace_setting)

st.session_state.sliders = PersonalitySliders(
    empathy_bias=empathy,
    risk_tolerance=risk,
    dominance_level=dominance,
    pace_setting=pace,
    neuroticism=0.1
)

st.sidebar.divider()
st.sidebar.info(f"Model: {settings.LLM_MODEL_NAME}")

# --- User Profile Section (NEW) ---
st.sidebar.subheader("👤 User Identity (Hard Facts)")

async def get_profile_data():
    mem = MemorySystem()
    return await mem.store.get_user_profile(999) # User 999

async def update_profile_data(data):
    mem = MemorySystem()
    await mem.update_user_profile(999, data)

# Load profile on first run
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
        
        # Gender Select
        g_opts = ["", "Male", "Female", "Neutral"]
        curr_g = st.session_state.user_profile_data.get("gender", "")
        g_idx = g_opts.index(curr_g) if curr_g in g_opts else 0
        p_gender = st.selectbox("Gender", g_opts, index=g_idx)
        
        # Mode Select
        m_opts = ["formal", "informal"]
        curr_m = st.session_state.user_profile_data.get("preferred_mode", "formal")
        m_idx = m_opts.index(curr_m) if curr_m in m_opts else 0
        p_mode = st.selectbox("Address Style", m_opts, index=m_idx)
        
        if st.form_submit_button("Save Identity"):
            new_data = {"name": p_name, "gender": p_gender, "preferred_mode": p_mode}
            try:
                run_async(update_profile_data(new_data))
                st.session_state.user_profile_data = new_data
                st.success("Saved!")
            except Exception as e:
                st.error(f"Error: {e}")

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
    st.rerun()

# --- Main Chat Area ---

st.title("R-Bot: Cognitive Architecture Debugger")
st.markdown("Chat with the bot and see which brain module wins.")

# Display history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])
        
        # Display small stats under assistant messages
        if msg["role"] == "assistant" and "meta" in msg:
            stats = msg["meta"]
            
            # Winner Badge
            st.caption(f"🏆 Winner: **{msg['winner']}** ({stats['winner_score']}/10)")
            
            # Tiny chart for all scores
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
                        alt.value('orange'),  # Winner color
                        alt.value('lightgray')   # Others color
                    ),
                    tooltip=['Agent', 'Score']
                ).properties(height=150) # Compact height
                
                st.altair_chart(chart, use_container_width=True)
            
            with st.expander("Details"):
                st.json(stats)

# Input
user_input = st.chat_input("Say something...")

if user_input:
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.write(user_input)

    with st.spinner("Thinking..."):
        config = BotConfig(
            character_id="streamlit_user", 
            name="R-Bot", 
            sliders=st.session_state.sliders, 
            core_values=[]
        )
        kernel = RCoreKernel(config)
        
        incoming = IncomingMessage(
            user_id=999, 
            session_id="streamlit_session",
            text=user_input
        )
        
        try:
            response = run_async(kernel.process_message(incoming))
            
            bot_text = response.actions[0].payload['text']
            stats = response.internal_stats
            winner_name = response.winning_agent.value

            with st.chat_message("assistant"):
                st.write(bot_text)
                
                # Live Chart
                st.caption(f"🏆 Winner: **{winner_name}**")
                
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
            
        except Exception as e:
            st.error(f"Kernel Panic: {e}")
            st.error("Please check console logs.")
