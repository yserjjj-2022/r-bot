import streamlit as st
import pandas as pd
import json
import plotly.graph_objects as go
from datetime import datetime
from sqlalchemy import text
from src.r_core.infrastructure.db import get_async_session_maker

# Настройка страницы
st.set_page_config(page_title="R-Bot Encephalogram", page_icon="🧠", layout="wide")

st.title("🧠 R-Bot Encephalogram: Timeline Analysis")

# --- CSS для красоты ---
st.markdown("""
<style>
    .metric-card {
        background-color: #f0f2f6;
        border-radius: 10px;
        padding: 15px;
        margin: 5px 0;
    }
    .winner-agent {
        border-left: 5px solid #ff4b4b;
        padding-left: 10px;
    }
    .delta-pos { color: green; font-weight: bold; }
    .delta-neg { color: red; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# --- DB Connection ---
async def load_session_data(limit=50):
    """Загружает историю диалога и метрики, объединяя их по времени"""
    SessionLocal = get_async_session_maker()
    async with SessionLocal() as session:
        # 1. Загружаем сообщения (User + Bot)
        # Мы берем последние N сообщений
        msgs_result = await session.execute(
            text("""
                SELECT 
                    id, role, content, created_at, 
                    session_id, user_id
                FROM chat_history 
                ORDER BY created_at DESC 
                LIMIT :limit
            """),
            {"limit": limit * 2} # *2 т.к. user+bot пары
        )
        messages = msgs_result.mappings().all()
        
        # 2. Загружаем метрики (они пишутся только на ход бота)
        metrics_result = await session.execute(
            text("""
                SELECT 
                    session_id, created_at, metrics_json
                FROM metrics_logs
                ORDER BY created_at DESC
                LIMIT :limit
            """),
            {"limit": limit}
        )
        metrics = metrics_result.mappings().all()
        
    return messages, metrics

# --- Helper: Parse Metrics ---
def parse_metrics(metrics_row):
    try:
        data = metrics_row["metrics_json"]
        if isinstance(data, str):
            data = json.loads(data)
        return data
    except:
        return {}

# --- Helper: Extract Scores ---
def extract_scores(metrics_data):
    # Пытаемся достать 'all_scores'
    scores = metrics_data.get("all_scores", {})
    # Если там старый формат или пусто
    if not scores:
        return {"Amygdala": 0, "Prefrontal": 0, "Striatum": 0, "Social": 0, "Intuition": 0}
    return scores

# --- Helper: Extract Hormones ---
def extract_hormones(metrics_data):
    # Парсим строку "NE:0.50 DA:0.50..." или берем из json если есть
    h_str = metrics_data.get("hormonal_state", "")
    h_map = {"NE": 0.5, "DA": 0.5, "5HT": 0.5, "CORT": 0.5}
    
    if "NE:" in h_str:
        parts = h_str.split(" ")
        for p in parts:
            if ":" in p:
                k, v = p.split(":")
                try:
                    h_map[k] = float(v)
                except:
                    pass
    return h_map

# --- MAIN LOGIC ---
import asyncio

# Run async code in sync streamlit
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)
messages, metrics_logs = loop.run_until_complete(load_session_data(20))

if not messages:
    st.warning("No data found.")
    st.stop()

# --- Process Data for Timeline ---
# Нам нужно сопоставить: [User Msg] -> [Bot Msg + Metrics]
timeline = []

# Разворачиваем сообщения в хронологический порядок (были DESC)
messages = sorted(messages, key=lambda x: x["created_at"])
metrics_logs = sorted(metrics_logs, key=lambda x: x["created_at"])

# Грубая привязка метрик к ответу бота
# Идем по сообщениям. Если это 'assistant', ищем ближайшую метрику по времени
for i, msg in enumerate(messages):
    if msg["role"] == "assistant":
        # Ищем пару (вопрос юзера перед этим)
        user_text = messages[i-1]["content"] if i > 0 and messages[i-1]["role"] == "user" else "(No context)"
        bot_text = msg["content"]
        timestamp = msg["created_at"]
        
        # Ищем метрику (с допуском 2 секунды)
        matched_metric = None
        for m in metrics_logs:
            delta = (m["created_at"] - timestamp).total_seconds()
            if abs(delta) < 5: # 5 sec window
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
                "winner": matched_metric.get("winner_agent", "Unknown")
            })

# --- VISUALIZATION: GLOBAL CHARTS ---
st.header("📈 Session Dynamics")

if timeline:
    df_scores = pd.DataFrame([t["scores"] for t in timeline])
    df_scores["time"] = [t["time"] for t in timeline]
    
    df_hormones = pd.DataFrame([t["hormones"] for t in timeline])
    df_hormones["time"] = [t["time"] for t in timeline]

    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Agent Conflict (Votes)")
        st.line_chart(df_scores.set_index("time"))
        
    with col2:
        st.subheader("Biochemistry (Hormones)")
        st.line_chart(df_hormones.set_index("time"))

# --- VISUALIZATION: TIMELINE CARDS ---
st.header("📅 Interaction History (Reverse Chronological)")

# Идем с конца (новые сверху)
for i in range(len(timeline)-1, -1, -1):
    item = timeline[i]
    prev_item = timeline[i-1] if i > 0 else None
    
    with st.expander(f"⏰ {item['time']} | 🏆 Winner: {item.get('winner', 'Unknown')}", expanded=(i == len(timeline)-1)):
        c1, c2 = st.columns([1, 1])
        
        with c1:
            st.markdown(f"**👤 User:** {item['user']}")
            st.markdown(f"**🤖 Bot:** {item['bot']}")
            
            # Volition Status
            volition = item['metrics'].get("volition_selected")
            if volition:
                st.success(f"🛡️ **Volition Active:** {volition}")
            else:
                st.caption("🛡️ Volition: Passive")
                
        with c2:
            # Scores with Delta
            st.markdown("### 📊 Agent Scores")
            cols = st.columns(5)
            agent_names = ["Amygdala", "Prefrontal", "Striatum", "Social", "Intuition"]
            
            for idx, agent in enumerate(agent_names):
                val = item['scores'].get(agent, 0)
                # Calc Delta
                delta_str = ""
                if prev_item:
                    prev_val = prev_item['scores'].get(agent, 0)
                    diff = val - prev_val
                    if diff > 0.1: delta_str = f"🔺 +{diff:.1f}"
                    elif diff < -0.1: delta_str = f"🔻 {diff:.1f}"
                
                # Highlight winner
                # (Простая логика: если score самый высокий)
                is_winner = val == max(item['scores'].values()) if item['scores'] else False
                
                with cols[idx]:
                    st.metric(
                        label=agent[:4], # Short name
                        value=f"{val:.1f}",
                        delta=delta_str if delta_str else None,
                        delta_color="normal"
                    )

            # Hormones with Delta
            st.markdown("### ⚗️ Hormones")
            h_cols = st.columns(4)
            for idx, (h_name, h_val) in enumerate(item['hormones'].items()):
                # Delta
                h_delta = ""
                if prev_item:
                    prev_h = prev_item['hormones'].get(h_name, 0.5)
                    diff = h_val - prev_h
                    if abs(diff) > 0.01:
                        h_delta = f"{diff:+.2f}"
                
                with h_cols[idx]:
                    st.metric(label=h_name, value=f"{h_val:.2f}", delta=h_delta)

