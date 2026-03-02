# Specification: Task 10.5 - Fix API Entry Point

## Problem
API endpoints were created in Task 08 but placed in the wrong location:
- Current: `src/r_core/api.py` (contains `APIRouter` only)
- Missing: FastAPI `app` instance
- Result: Cannot start API server with `uvicorn src.interfaces.api:app`

## Goal
Move API to correct location and create proper FastAPI app entry point.

---

## Implementation

### 1. Move File
**Action:** Move `src/r_core/api.py` → `src/interfaces/api.py`

**Why:**
- `src/interfaces/` is the correct place for external interface layers (API, UI, etc.)
- `src/r_core/` should contain business logic only

### 2. Convert Router to App
**File:** `src/interfaces/api.py`

**Current structure (in `src/r_core/api.py`):**
```python
from fastapi import APIRouter

router = APIRouter(prefix="/api/character", tags=["character"])

@router.get("/profile")
async def get_character_profile(...):
    ...
```

**New structure:**
```python
"""
R-Bot Character Profile API
Provides HEXACO personality management endpoints.
"""

from typing import Dict, Any, Optional
from fastapi import FastAPI, APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, update

from src.r_core.infrastructure.db import AsyncSessionLocal, AgentProfileModel
from src.r_core.translation_engine import TraitTranslationEngine, is_dark_archetype

# Create FastAPI app
app = FastAPI(
    title="R-Bot API",
    description="Character profile management and HEXACO translation",
    version="1.0.0"
)

# Create router (keep existing structure)
router = APIRouter(prefix="/api/character", tags=["character"])

# ... (keep all existing Pydantic models and endpoints as-is) ...

# Mount router to app at the end of file
app.include_router(router)
```

**Changes:**
1. Add `from fastapi import FastAPI` import
2. Create `app = FastAPI(...)` instance at top (after imports)
3. Keep existing `router = APIRouter(...)` and all endpoints unchanged
4. Add `app.include_router(router)` at the end
5. Update imports: `from src.r_core.infrastructure.db` (change relative to absolute)

### 3. Fix Import Paths
**In `src/interfaces/api.py`:**

Change:
```python
from .infrastructure.db import AsyncSessionLocal, AgentProfileModel
from .translation_engine import TraitTranslationEngine, is_dark_archetype
```

To:
```python
from src.r_core.infrastructure.db import AsyncSessionLocal, AgentProfileModel
from src.r_core.translation_engine import TraitTranslationEngine, is_dark_archetype
```

### 4. Delete Old File
**Action:** Remove `src/r_core/api.py` (now in `src/interfaces/api.py`)

---

## Testing

### Start API Server
```bash
uvicorn src.interfaces.api:app --reload --host 0.0.0.0 --port 8000
```

**Expected output:**
```
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
INFO:     Started reloader process [xxxxx] using WatchFiles
INFO:     Started server process [xxxxx]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
```

### Test Endpoints

1. **Health check:**
   ```bash
   curl http://localhost:8000/docs
   # Should show Swagger UI
   ```

2. **Get presets:**
   ```bash
   curl http://localhost:8000/api/character/presets
   # Should return {"light_presets": {...}, "dark_presets": {...}}
   ```

3. **Get profile:**
   ```bash
   curl http://localhost:8000/api/character/profile?name=default
   # Should return profile or 404
   ```

---

## Files Changed

1. **DELETE:** `src/r_core/api.py`
2. **CREATE:** `src/interfaces/api.py` (moved from above + modifications)
   - Add `FastAPI` import
   - Create `app` instance
   - Fix import paths (relative → absolute)
   - Mount router: `app.include_router(router)`

---

## Success Criteria

- [ ] `uvicorn src.interfaces.api:app --reload` starts without errors
- [ ] Swagger docs accessible at `http://localhost:8000/docs`
- [ ] All 4 endpoints respond correctly:
  - `GET /api/character/profile`
  - `POST /api/character/profile`
  - `GET /api/character/presets`
  - `POST /api/character/presets/{preset_name}`
- [ ] Streamlit can connect to API (Task 10 functionality works)
- [ ] Old file `src/r_core/api.py` removed

---

## Notes

- **No functional changes** — only moving file and creating app wrapper
- **All endpoint logic stays the same** (router code unchanged)
- **Import paths must be absolute** in `src/interfaces/` (not relative like in `src/r_core/`)
