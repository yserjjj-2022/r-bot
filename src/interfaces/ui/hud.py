import streamlit as st
import pandas as pd
import altair as alt

def render_neuro_hud(stats: dict):
    """
    Renders a compact Heads-Up Display (HUD) for R-Bot's internal state.
    Place this right after the bot's response.
    """
    if not stats:
        st.caption("No neural data available.")
        return

    # --- 1. Top Row: Winner & Prediction Error ---
    c1, c2, c3 = st.columns([2, 1, 1])
    
    # Winner Agent
    winner = stats.get("winner_agent", "Unknown")
    # Sometimes it comes as enum value, sometimes string. Handle both.
    if hasattr(winner, "value"): winner = winner.value
    winner = str(winner).upper()
    
    icon = _get_agent_icon(winner)
    score = stats.get("winner_score", 0.0)
    
    with c1:
        st.markdown(f"#### 🏆 {icon} {winner} <span style='font-size:0.8em; color:gray'>({score:.1f})</span>", unsafe_allow_html=True)
        reason = stats.get("winner_reason", "No rationale")
        st.caption(f"Reason: *{reason}*")

    # Predictive Error (Surprise)
    pe = stats.get("prediction_error", 0.0)
    pe_color = "green" if pe < 0.3 else "orange" if pe < 0.7 else "red"
    pe_label = "Low" if pe < 0.3 else "Med" if pe < 0.7 else "High"
    
    with c2:
        st.metric("😲 Surprise (PE)", f"{pe:.2f}", delta=pe_label, delta_color="inverse")

    # Volition (Focus)
    volition = stats.get("volition_selected", "None")
    with c3:
        if volition:
             st.metric("🎯 Focus", volition)
        else:
             st.metric("🎯 Focus", "Drifting", delta_color="off")

    st.divider()

    # --- 2. Middle Row: Neural Activity & Hormones ---
    hc1, hc2 = st.columns([3, 2])

    with hc1:
        st.caption("🧠 Cortical Activity (Council Votes)")
        all_scores = stats.get("all_scores", {})
        if all_scores:
            # Prepare data for Altair
            # Normalize keys to short names
            data = []
            for k, v in all_scores.items():
                short_name = k.split("_")[0].capitalize()[:4] # Amygdala -> Amyg
                data.append({"Agent": short_name, "Score": v, "Full": k})
            
            df = pd.DataFrame(data)
            
            # Highlight winner
            chart = alt.Chart(df).mark_bar().encode(
                x=alt.X('Agent', sort='-y'),
                y=alt.Y('Score', scale=alt.Scale(domain=[0, 10])),
                color=alt.condition(
                    alt.datum.Score == score,  # Approximate match for winner
                    alt.value('orange'),     # The winner color
                    alt.value('#e0e0e0')     # Others color
                ),
                tooltip=['Full', 'Score']
            ).properties(height=120)
            
            st.altair_chart(chart, use_container_width=True)

    with hc2:
        st.caption("⚗️ Neurochemistry")
        # Hormones come as string "NE:0.5..." or dict
        h_state = stats.get("hormonal_state", {})
        if isinstance(h_state, str):
            h_state = _parse_hormone_str(h_state)
            
        if h_state:
            # Custom HTML bars for compactness
            for h, val in h_state.items():
                color = _get_hormone_color(h)
                pct = min(100, max(0, int(val * 100)))
                st.markdown(
                    f"""
                    <div style="display:flex; align-items:center; margin-bottom:4px;">
                        <span style="width:40px; font-weight:bold; font-size:0.8em;">{h}</span>
                        <div style="flex-grow:1; background-color:#eee; height:8px; border-radius:4px;">
                            <div style="width:{pct}%; background-color:{color}; height:100%; border-radius:4px;"></div>
                        </div>
                        <span style="width:30px; text-align:right; font-size:0.7em;">{val:.2f}</span>
                    </div>
                    """, 
                    unsafe_allow_html=True
                )
    
    # --- 3. Bottom: Next Prediction ---
    next_pred = stats.get("next_prediction")
    if next_pred:
        st.info(f"🔮 **Hypothesis:** I expect you to say: *'{next_pred}'*")


def _get_agent_icon(name: str) -> str:
    name = name.lower()
    if "amyg" in name: return "🛡️"
    if "pref" in name: return "🧠"
    if "soc" in name: return "💖"
    if "stria" in name: return "💎"
    if "intuit" in name: return "🔮"
    if "uncer" in name: return "❓"
    return "🤖"

def _get_hormone_color(name: str) -> str:
    if "NE" in name: return "#ff4b4b" # Red (Adrenaline/Norepinephrine)
    if "DA" in name: return "#ffa500" # Orange (Dopamine/Reward)
    if "5HT" in name: return "#00c853" # Green (Serotonin/Mood)
    if "CORT" in name: return "#6200ea" # Purple (Cortisol/Stress)
    return "gray"

def _parse_hormone_str(h_str: str) -> dict:
    # "NE:0.10 DA:0.50 5HT:0.50 CORT:0.10"
    res = {}
    parts = h_str.replace("{", "").replace("}", "").replace("'", "").replace(",", "").split()
    for p in parts:
        if ":" in p:
            k, v = p.split(":")
            try:
                res[k] = float(v)
            except: pass
    return res
