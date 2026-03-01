# Specification: Task 09 - Streamlit Character Selector & Mode Defaults

## Overview
This task establishes the foundation for the HEXACO dashboard by:
1. Setting UNIFIED council mode as the default (while keeping LEGACY available for debugging)
2. Creating a character selector UI that loads and switches between different AgentProfiles
3. Integrating the selected character with the R-Core kernel pipeline

## Goals
- [ ] Set UNIFIED as default council mode in Streamlit
- [ ] Add character selector dropdown populated from `agent_profiles` table
- [ ] Display current character name and description in UI
- [ ] Store selected character in `st.session_state` and pass to kernel
- [ ] Ensure kernel reinitializes when character changes

## Implementation Details

### 1. UNIFIED Mode Default
**File:** `app_streamlit.py`

**Current State:**
```python
use_unified_council = st.checkbox("🔄 Unified Council", value=True)
```

**Required Change:**
No change needed - already defaults to `True`. Verify that:
- The checkbox is checked by default
- LEGACY mode remains selectable (for debugging/regression testing)
- User's choice persists within the session

**Verification:**
- Test both modes still work
- Confirm UNIFIED is selected on fresh page load

---

### 2. Character Selector UI
**File:** `app_streamlit.py`

**Location:** In the sidebar, under "🤖 Bot Identity" section (already exists).

**Current Implementation:**
```python
selected_agent_name = st.sidebar.selectbox("Select Persona", ["Default"] + agent_names)
```

This already works! Task 09 just needs to ensure:

#### 2.1. Fetch All Characters
- Function `get_all_agents()` already exists and queries `AgentProfileModel`
- Returns list of all agent profiles with `name`, `description`, `gender`, `sliders_preset`, `hexaco_profile`

#### 2.2. Display Character Info
**Current:**
```python
if selected_agent_name != "Default":
    st.session_state.bot_name = selected_agent_name
    agent_data = next((a for a in available_agents if a.name == selected_agent_name), None)
    if agent_data:
        st.session_state.bot_gender = agent_data.gender or "Neutral"
        st.sidebar.caption(f"📝 {agent_data.description} | {st.session_state.bot_gender}")
```

**Enhancement:**
Add a more visible info box showing:
- Character name (bold)
- Description
- Gender
- Current HEXACO preset (if available)

**New Code:**
```python
if selected_agent_name != "Default":
    agent_data = next((a for a in available_agents if a.name == selected_agent_name), None)
    if agent_data:
        st.session_state.bot_name = agent_data.name
        st.session_state.bot_gender = agent_data.gender or "Neutral"
        st.session_state.current_agent_id = agent_data.id  # NEW: Store ID
        
        # Display character card
        st.sidebar.info(f"""
        **{agent_data.name}** ({agent_data.gender})
        
        {agent_data.description or 'No description'}
        
        *ID: {agent_data.id}*
        """)
        
        # Load HEXACO if available
        if agent_data.hexaco_profile:
            st.sidebar.caption(f"🧬 HEXACO: {agent_data.personality_preset or 'Custom'}")
else:
    st.session_state.bot_name = "R-Bot"
    st.session_state.bot_gender = "Neutral"
    st.session_state.current_agent_id = None
```

---

### 3. Kernel Integration
**File:** `app_streamlit.py`

**Current Behavior:**
- Kernel is reinitialized when `selected_agent_name` changes (via `last_agent_name` comparison)
- Sliders are loaded from `agent_data.sliders_preset`

**Required Enhancement:**
Ensure that when a character is selected:
1. The kernel's `config.name` is updated
2. HEXACO profile (if present) is loaded and applied via `TraitTranslationEngine`
3. Old kernel instance is discarded to prevent state leakage

**Implementation:**

```python
# Reset kernel if persona changes
if "last_agent_name" not in st.session_state:
    st.session_state.last_agent_name = selected_agent_name

if st.session_state.last_agent_name != selected_agent_name:
    st.session_state.kernel_instance = None  # Force reinitialization
    st.session_state.last_agent_name = selected_agent_name
    st.rerun()
```

This already exists. **No changes needed here.**

---

### 4. Session State Management
**Required State Variables:**
```python
if "current_agent_id" not in st.session_state:
    st.session_state.current_agent_id = None  # NEW

if "bot_name" not in st.session_state:
    st.session_state.bot_name = "R-Bot"

if "bot_gender" not in st.session_state:
    st.session_state.bot_gender = "Neutral"

if "last_agent_name" not in st.session_state:
    st.session_state.last_agent_name = "Default"
```

---

### 5. API Integration (Optional for Task 09)
**Note:** Full HEXACO editing will be in Task 10. For now, we only need to **read** the character's profile.

If `agent_data.hexaco_profile` exists:
- Display it as a small JSON or table in the sidebar
- Do NOT allow editing yet (that's Task 10)

**Example:**
```python
if agent_data.hexaco_profile:
    with st.sidebar.expander("🧬 HEXACO Profile (Read-Only)"):
        st.json(agent_data.hexaco_profile)
```

---

## Testing Checklist
- [ ] UNIFIED mode is selected by default on fresh load
- [ ] LEGACY mode can still be selected and works
- [ ] Character dropdown shows all agents from `agent_profiles`
- [ ] Selecting a character updates `st.session_state.bot_name` and `bot_gender`
- [ ] Character description is displayed in sidebar
- [ ] Kernel reinitializes when switching characters
- [ ] Chat history is preserved when switching (or cleared - decide)
- [ ] HEXACO profile (if present) is displayed as JSON in sidebar

---

## Files to Modify
1. `app_streamlit.py` - Main changes
   - Add `current_agent_id` to session state
   - Enhance character info display
   - Add HEXACO profile preview (read-only)

2. No backend changes needed (Task 08 already provides everything)

---

## Out of Scope (Deferred to Task 10)
- HEXACO sliders (editing)
- Preset selector
- Radar chart visualization
- Ghost markers
- POST to `/api/character/profile`

Task 09 is purely about **selecting** and **loading** existing characters, not editing them.
