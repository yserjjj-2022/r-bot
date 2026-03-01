# Specification: Task 10 - HEXACO Editor & Presets (Streamlit UI)

## Overview
This task implements the interactive HEXACO personality editor in Streamlit, allowing users to:
1. Edit 6 HEXACO trait sliders (H, E, X, A, C, O) for selected characters
2. Apply Light/Functional and Dark/Deviant presets
3. Save profiles via API (updating `agent_profiles.hexaco_profile` and `personality_preset`)
4. View current preset and reset to neutral (50/50) values

**NO database schema changes.** All persistence goes through existing API endpoints from Task 08.

---

## Goals
- [ ] Implement HEXACO slider panel in Streamlit sidebar
- [ ] Load character HEXACO profile via `GET /api/character/profile?name=...`
- [ ] Display and apply presets from `GET /api/character/presets`
- [ ] Save edited profile via `POST /api/character/profile`
- [ ] Handle API errors gracefully (show read-only mode if API unavailable)
- [ ] Integrate with existing character selector from Task 09

---

## Implementation Details

### 1. API Client Functions
**File:** `app_streamlit.py`

Add helper functions for HTTP communication with the FastAPI backend:

```python
import requests
from typing import Optional

# TODO: Move to settings.py later
API_BASE_URL = "http://localhost:8000"  # or settings.API_BASE_URL

def fetch_character_profile(name: str) -> Optional[dict]:
    """
    GET /api/character/profile?name={name}
    
    Returns:
        {
            "name": str,
            "hexaco_profile": {"H": int, "E": int, "X": int, "A": int, "C": int, "O": int},
            "personality_preset": str | None
        }
    """
    try:
        resp = requests.get(f"{API_BASE_URL}/api/character/profile", params={"name": name}, timeout=5)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        st.error(f"Failed to load profile: {e}")
        return None

def fetch_presets() -> Optional[dict]:
    """
    GET /api/character/presets
    
    Returns:
        {
            "light": {"Аналитик": {...}, "Эмпат": {...}, ...},
            "dark": {"Макиавеллист": {...}, "Нарцисс": {...}, ...}
        }
    """
    try:
        resp = requests.get(f"{API_BASE_URL}/api/character/presets", timeout=5)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        st.error(f"Failed to load presets: {e}")
        return None

def save_character_profile(name: str, hexaco: dict, preset: Optional[str]) -> bool:
    """
    POST /api/character/profile
    
    Payload:
        {
            "name": str,
            "hexaco_profile": {"H": int, ...},
            "personality_preset": str | None
        }
    
    Returns:
        True if success, False otherwise
    """
    try:
        payload = {
            "name": name,
            "hexaco_profile": hexaco,
            "personality_preset": preset
        }
        resp = requests.post(f"{API_BASE_URL}/api/character/profile", json=payload, timeout=5)
        resp.raise_for_status()
        return True
    except Exception as e:
        st.error(f"Failed to save profile: {e}")
        return False

def apply_preset(preset_name: str) -> Optional[dict]:
    """
    POST /api/character/presets/{preset_name}
    
    Returns:
        {"H": int, "E": int, ...} - the HEXACO profile for this preset
    """
    try:
        resp = requests.post(f"{API_BASE_URL}/api/character/presets/{preset_name}", timeout=5)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        st.error(f"Failed to apply preset: {e}")
        return None
```

---

### 2. Session State Extensions
**File:** `app_streamlit.py`

Add to global init section (near `if "bot_name" not in st.session_state`):

```python
if "hexaco_profile" not in st.session_state:
    st.session_state.hexaco_profile = None  # Will be loaded from API

if "personality_preset" not in st.session_state:
    st.session_state.personality_preset = None

if "hexaco_presets" not in st.session_state:
    st.session_state.hexaco_presets = None  # Cached preset list
```

---

### 3. Load Profile When Character Selected
**File:** `app_streamlit.py`

**Location:** In the Chat Interface section, after character selection logic (where `agent_data` is retrieved).

**Current code (Task 09):**
```python
if selected_agent_name != "Default":
    agent_data = next((a for a in available_agents if a.name == selected_agent_name), None)
    if agent_data:
        st.session_state.bot_name = agent_data.name
        st.session_state.bot_gender = agent_data.gender or "Neutral"
        st.session_state.current_agent_id = agent_data.id
        
        # Display character card
        st.sidebar.info(...)
        
        # Load HEXACO profile if available (Read-Only)  <-- REMOVE THIS BLOCK
        if agent_data.hexaco_profile:
            with st.sidebar.expander("🧬 HEXACO Profile (Read-Only)"):
                st.json(agent_data.hexaco_profile)
```

**New code (Task 10):**
```python
if selected_agent_name != "Default":
    agent_data = next((a for a in available_agents if a.name == selected_agent_name), None)
    if agent_data:
        st.session_state.bot_name = agent_data.name
        st.session_state.bot_gender = agent_data.gender or "Neutral"
        st.session_state.current_agent_id = agent_data.id
        
        # Display character card
        st.sidebar.info(...)
        
        # Load HEXACO profile from API
        profile_data = fetch_character_profile(agent_data.name)
        if profile_data:
            st.session_state.hexaco_profile = profile_data.get("hexaco_profile", {"H":50,"E":50,"X":50,"A":50,"C":50,"O":50})
            st.session_state.personality_preset = profile_data.get("personality_preset")
        else:
            # Fallback: empty/neutral profile
            st.session_state.hexaco_profile = {"H":50,"E":50,"X":50,"A":50,"C":50,"O":50}
            st.session_state.personality_preset = None
        
        # Load presets once (cache in session state)
        if st.session_state.hexaco_presets is None:
            st.session_state.hexaco_presets = fetch_presets()
```

---

### 4. HEXACO Editor Panel
**File:** `app_streamlit.py`

**Location:** In sidebar, after character card display, before "Personality Tuner" expander.

```python
# --- HEXACO Editor (Task 10) ---
if selected_agent_name != "Default" and st.session_state.current_agent_id is not None:
    with st.sidebar.expander("🧬 HEXACO Editor", expanded=False):
        hexaco = st.session_state.hexaco_profile or {"H":50, "E":50, "X":50, "A":50, "C":50, "O":50}
        
        st.markdown("### Trait Sliders")
        st.caption("Adjust personality dimensions (0-100)")
        
        H = st.slider("H: Хитрость ⟷ Искренность", 0, 100, hexaco["H"], help="Honesty-Humility")
        E = st.slider("E: Хладнокровие ⟷ Тревожность", 0, 100, hexaco["E"], help="Emotionality/Neuroticism")
        X = st.slider("X: Замкнутость ⟷ Общительность", 0, 100, hexaco["X"], help="Extraversion")
        A = st.slider("A: Сварливость ⟷ Покладистость", 0, 100, hexaco["A"], help="Agreeableness")
        C = st.slider("C: Хаотичность ⟷ Целеустремленность", 0, 100, hexaco["C"], help="Conscientiousness")
        O = st.slider("O: Консерватизм ⟷ Любознательность", 0, 100, hexaco["O"], help="Openness to Experience")
        
        # Current preset display
        current_preset = st.session_state.personality_preset or "Custom"
        st.caption(f"📌 Current Preset: **{current_preset}**")
        
        # Reset button
        if st.button("🔄 Reset to Neutral (50/50)"):
            st.session_state.hexaco_profile = {"H":50, "E":50, "X":50, "A":50, "C":50, "O":50}
            st.session_state.personality_preset = None
            st.rerun()
        
        st.divider()
        
        # --- Presets Section ---
        st.markdown("### 🎭 Apply Preset")
        
        presets = st.session_state.hexaco_presets
        if presets:
            # Light Presets
            st.markdown("**✨ Light / Functional Archetypes**")
            light_names = list(presets.get("light", {}).keys())
            selected_light = st.selectbox("Select Light Preset", ["<none>"] + light_names, key="light_preset_selector")
            
            if selected_light != "<none>":
                if st.button(f"Apply '{selected_light}'", key="apply_light"):
                    preset_hexaco = apply_preset(selected_light)
                    if preset_hexaco:
                        st.session_state.hexaco_profile = preset_hexaco
                        st.session_state.personality_preset = selected_light
                        st.success(f"Applied preset: {selected_light}")
                        st.rerun()
            
            st.markdown("---")
            
            # Dark Presets
            st.markdown("**🌑 Dark / Deviant Archetypes**")
            dark_names = list(presets.get("dark", {}).keys())
            selected_dark = st.selectbox("Select Dark Preset", ["<none>"] + dark_names, key="dark_preset_selector")
            
            if selected_dark != "<none>":
                if st.button(f"Apply '{selected_dark}'", key="apply_dark"):
                    preset_hexaco = apply_preset(selected_dark)
                    if preset_hexaco:
                        st.session_state.hexaco_profile = preset_hexaco
                        st.session_state.personality_preset = selected_dark
                        st.success(f"Applied preset: {selected_dark}")
                        st.rerun()
        else:
            st.warning("⚠️ Presets unavailable (API offline)")
        
        st.divider()
        
        # --- Save Button ---
        st.markdown("### 💾 Save Profile")
        if st.button("Save HEXACO Profile", type="primary"):
            # Detect if user manually edited sliders (optional: mark as "Custom")
            # For now, just save whatever is in sliders + current preset
            new_hexaco = {"H": H, "E": E, "X": X, "A": A, "C": C, "O": O}
            
            success = save_character_profile(
                name=st.session_state.bot_name,
                hexaco=new_hexaco,
                preset=st.session_state.personality_preset
            )
            
            if success:
                st.session_state.hexaco_profile = new_hexaco
                st.success("✅ Profile saved successfully!")
                # Force kernel reload on next message to apply new config
                st.session_state.kernel_instance = None
            else:
                st.error("❌ Failed to save profile")
```

---

### 5. API Availability Check
If API is down, show read-only mode:

```python
# At the top of HEXACO Editor expander
api_available = st.session_state.hexaco_presets is not None

if not api_available:
    st.warning("⚠️ API unavailable. HEXACO editor is in read-only mode.")
    st.json(st.session_state.hexaco_profile)
    st.stop()  # Don't render sliders if API is down
```

---

### 6. Kernel Integration (Verification Only)
**No changes needed in this task.**

Task 08 already implemented `TraitTranslationEngine` integration in `RCoreKernel.process_message()` [cite:323].

When HEXACO profile is updated:
1. Next message will reload `AgentProfileModel` from DB (with new `hexaco_profile`)
2. `TraitTranslationEngine.apply_to_bot_config()` will recalculate:
   - `intuition_gain` (from Openness)
   - `base_decay_rate` (from Conscientiousness)
   - `chaos_level` (from Emotionality)
   - etc. (see Task 08 translation matrix)

**Task 10 verification:**
- After saving profile, set `st.session_state.kernel_instance = None` to force reinitialization
- This ensures new HEXACO → R-Core translation happens on next user message

---

## Testing Checklist
- [ ] HEXACO editor shows only when a non-Default character is selected
- [ ] Sliders load current values from API
- [ ] Preset dropdowns populated from `GET /api/character/presets`
- [ ] Applying a preset updates sliders and `personality_preset` field
- [ ] "Reset to Neutral" button sets all traits to 50
- [ ] "Save Profile" button calls `POST /api/character/profile` successfully
- [ ] After save, kernel reinitializes on next message
- [ ] If API is down, show warning and disable editing
- [ ] Dark zone warning (H < 25 AND A < 25) shows visual indicator (optional, can defer to Task 11)

---

## Files to Modify
1. **app_streamlit.py**
   - Add API client functions (`fetch_character_profile`, `save_character_profile`, etc.)
   - Add session state variables (`hexaco_profile`, `personality_preset`, `hexaco_presets`)
   - Replace read-only HEXACO display with editor panel
   - Integrate preset selection and save logic

2. **No backend changes** (Task 08 API already complete)

---

## Out of Scope (Deferred to Task 11)
- Radar chart visualization (plotly hexagon)
- Ghost markers (showing previous values)
- Dark zone visual highlighting (red background when H < 25 AND A < 25)
- Real-time HEXACO → R-Core parameter preview (show translated values before save)

Task 10 focuses on **functional editing and persistence only**.

---

## Dependencies
- Task 08: API endpoints must be working (`/api/character/profile`, `/api/character/presets`)
- Task 09: Character selector and session state structure
- `requests` library (should already be installed)

---

## Notes
- API timeout set to 5 seconds for all requests
- If user edits sliders after applying a preset, `personality_preset` stays as-is (not auto-cleared to "Custom"). This can be refined later if needed.
- For production: move `API_BASE_URL` to `settings.py` or environment variable
