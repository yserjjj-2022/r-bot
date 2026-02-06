import asyncio
import streamlit as st
import pandas as pd
import altair as alt
from src.r_core.schemas import BotConfig, PersonalitySliders, IncomingMessage
from src.r_core.pipeline import RCoreKernel
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
    st.session_state.messages = [] # Format: {"role": "user/assistant", "content": str, "meta": dict}

if "kernel" not in st.session_state:
    # Init DB and Kernel once
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(init_models())
    except Exception as e:
        st.error(f"DB Init failed: {e}")

    # Default Sliders
    default_sliders = PersonalitySliders(
        empathy_bias=0.5, 
        risk_tolerance=0.5, 
        dominance_level=0.5, 
        pace_setting=0.5, 
        neuroticism=0.1
    )
    
    config = BotConfig(
        character_id="streamlit_user", 
        name="R-Bot", 
        sliders=default_sliders, 
        core_values=[]
    )
    st.session_state.kernel = RCoreKernel(config)
    st.session_state.sliders = default_sliders

# --- Sidebar: Cortex Controls ---
st.sidebar.title("🧠 Cortex Controls")
st.sidebar.markdown("Adjust the bot's personality live.")

empathy = st.sidebar.slider("Empathy Bias (Social vs Logic)", 0.0, 1.0, 0.5)
risk = st.sidebar.slider("Risk Tolerance (Striatum vs Amygdala)", 0.0, 1.0, 0.5)
dominance = st.sidebar.slider("Dominance", 0.0, 1.0, 0.5)
pace = st.sidebar.slider("Pace (Intuition Speed)", 0.0, 1.0, 0.5)

# Update sliders in kernel
st.session_state.kernel.config.sliders = PersonalitySliders(
    empathy_bias=empathy,
    risk_tolerance=risk,
    dominance_level=dominance,
    pace_setting=pace,
    neuroticism=0.1
)

st.sidebar.divider()
st.sidebar.info(f"Model: {settings.LLM_MODEL_NAME}")
if st.sidebar.button("Clear Memory & Chat"):
    st.session_state.messages = []
    st.experimental_rerun()

# --- Main Chat Area ---

st.title("R-Bot: Cognitive Architecture Debugger")
st.markdown("Chat with the bot and see which brain module wins.")

# Display history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])
        if "meta" in msg and msg["meta"]:
            with st.expander("See Brain Activity"):
                st.json(msg["meta"])

# Input
user_input = st.chat_input("Say something...")

if user_input:
    # 1. User Message
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.write(user_input)

    # 2. Process
    with st.spinner("Thinking (Retrieving + Council Debate)..."):
        incoming = IncomingMessage(
            user_id=999, # Streamlit User
            session_id="streamlit_session",
            text=user_input
        )
        
        # Async run in Streamlit
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        response = loop.run_until_complete(st.session_state.kernel.process_message(incoming))
        
        bot_text = response.actions[0].payload['text']
        stats = response.internal_stats

    # 3. Bot Response
    with st.chat_message("assistant"):
        st.write(bot_text)
        
        # 4. Visualization
        col1, col2 = st.columns([1, 2])
        
        with col1:
            st.metric("Winner", response.winning_agent.value, f"{stats['winner_score']} / 10")
            st.caption(f"Reason: {stats['winner_reason']}")
            st.caption(f"Latency: {stats['latency_ms']}ms")

        # with col2:
            # We can visualize scores of all agents here if we passed them out of kernel
            # For now, just showing the winner meta is enough for Sprint 2
    
    st.session_state.messages.append({
        "role": "assistant", 
        "content": bot_text, 
        "meta": stats
    })
