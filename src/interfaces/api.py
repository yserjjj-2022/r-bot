"""
R-Bot Character Profile API
Provides HEXACO personality management endpoints.
"""

from typing import Dict, Any, Optional
from fastapi import FastAPI, APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from src.r_core.infrastructure.db import AsyncSessionLocal, AgentProfileModel
from src.r_core.translation_engine import TraitTranslationEngine, is_dark_archetype

# Create FastAPI app
app = FastAPI(
    title="R-Bot API",
    description="Character profile management and HEXACO translation",
    version="1.0.0"
)

# Create router
router = APIRouter(prefix="/api/character", tags=["character"])


# === Request/Response Models ===

class HexacoProfileRequest(BaseModel):
    """HEXACO profile update request."""
    name: Optional[str] = None
    hexaco_profile: Optional[Dict[str, int]] = None
    sliders_preset: Optional[Dict[str, float]] = None
    description: Optional[str] = None
    gender: Optional[str] = None
    personality_preset: Optional[str] = None


class HexacoProfileResponse(BaseModel):
    """HEXACO profile response."""
    name: str
    hexaco_profile: Dict[str, int] = {"H": 50, "E": 50, "X": 50, "A": 50, "C": 50, "O": 50}
    sliders_preset: Dict[str, Any] = {}
    description: Optional[str] = None
    gender: str = "Neutral"
    personality_preset: Optional[str] = None
    is_dark_archetype: bool = False
    translated_config: Optional[Dict[str, Any]] = None


class PresetListResponse(BaseModel):
    """List of available presets."""
    light_presets: Dict[str, Dict[str, int]]
    dark_presets: Dict[str, Dict[str, int]]


# === API Endpoints ===

@router.get("/profile", response_model=HexacoProfileResponse)
async def get_character_profile(name: str = "default"):
    """
    Get character profile by name.
    Returns HEXACO profile and translated R-Core config.
    """
    async with AsyncSessionLocal() as session:
        stmt = select(AgentProfileModel).where(AgentProfileModel.name == name)
        result = await session.execute(stmt)
        profile = result.scalar_one_or_none()
        
        if not profile:
            raise HTTPException(status_code=404, detail=f"Profile '{name}' not found")
        
        hexaco = profile.hexaco_profile
        if hexaco is None:
            hexaco = {"H": 50, "E": 50, "X": 50, "A": 50, "C": 50, "O": 50}
        
        # Translate to R-Core config
        translator = TraitTranslationEngine(hexaco)
        translated = translator.translate()
        translated_config = {
            "intuition_gain": translated.intuition_gain,
            "chaos_level": translated.chaos_level,
            "base_decay_rate": translated.base_decay_rate,
            "persistence": translated.persistence,
            "dynamic_phatic_threshold": translated.dynamic_phatic_threshold,
            "social_agent_weight": translated.social_agent_weight,
            "pred_sensitivity": translated.pred_sensitivity,
            "amygdala_multiplier": translated.amygdala_multiplier,
            "striatum_agent_weight": translated.striatum_agent_weight,
            "force_manipulation_strategies": translated.force_manipulation_strategies,
            "bifurcation_threshold_modifier": translated.bifurcation_threshold_modifier,
            "baseline_cortisol": translated.baseline_cortisol,
            "baseline_oxytocin": translated.baseline_oxytocin,
        }
        
        return HexacoProfileResponse(
            name=profile.name,
            hexaco_profile=hexaco,
            sliders_preset=profile.sliders_preset or {},
            description=profile.description,
            gender=profile.gender or "Neutral",
            personality_preset=profile.personality_preset,
            is_dark_archetype=is_dark_archetype(hexaco),
            translated_config=translated_config
        )


@router.post("/profile", response_model=HexacoProfileResponse)
async def update_character_profile(request: HexacoProfileRequest):
    """
    Update character profile.
    Can update HEXACO profile, sliders, description, and gender.
    
    CRITICAL: When hexaco_profile is provided, sliders_preset is automatically
    recalculated via TraitTranslationEngine (one-way sync from HEXACO to sliders).
    When only sliders_preset is provided, it acts as manual override.
    """
    async with AsyncSessionLocal() as session:
        # Find existing or create new
        profile_name = request.name or "default"
        stmt = select(AgentProfileModel).where(AgentProfileModel.name == profile_name)
        result = await session.execute(stmt)
        profile = result.scalar_one_or_none()
        
        if not profile:
            # Create new profile
            profile = AgentProfileModel(
                name=profile_name,
                hexaco_profile=request.hexaco_profile or {
                    "H": 50, "E": 50, "X": 50, "A": 50, "C": 50, "O": 50
                }
            )
            session.add(profile)
        else:
            # Update existing
            hexaco_updated = request.hexaco_profile is not None
            sliders_override = request.sliders_preset is not None
            preset_updated = request.personality_preset is not None
            
            if hexaco_updated:
                # CRITICAL: One-way sync HEXACO -> sliders_preset
                profile.hexaco_profile = request.hexaco_profile
                profile.personality_preset = None  # Clear preset name on manual edit
                
                # Translate HEXACO to sliders
                translator = TraitTranslationEngine(request.hexaco_profile)
                translated = translator.translate()
                
                # Keep non-HEXACO-dependent fields
                current_sliders = profile.sliders_preset or {}
                profile.sliders_preset = {
                    "empathy_bias": translated.intuition_gain,
                    "risk_tolerance": translated.persistence,
                    "dominance_level": translated.striatum_agent_weight,
                    "pace_setting": translated.social_agent_weight,
                    "chaos_level": translated.chaos_level,
                    "persistence": translated.persistence,
                    "pred_sensitivity": translated.pred_sensitivity,
                    "learning_speed": current_sliders.get("learning_speed", 0.5),
                    "pred_threshold": current_sliders.get("pred_threshold", 0.65)
                }
            elif sliders_override:
                # Manual override - save as-is
                profile.sliders_preset = request.sliders_preset
            elif preset_updated:
                profile.personality_preset = request.personality_preset
            
            if request.description is not None:
                profile.description = request.description
            if request.gender is not None:
                profile.gender = request.gender
        
        await session.commit()
        
        # Refresh and return
        await session.refresh(profile)
        
        hexaco = profile.hexaco_profile or {
            "H": 50, "E": 50, "X": 50, "A": 50, "C": 50, "O": 50
        }
        
        translator = TraitTranslationEngine(hexaco)
        translated = translator.translate()
        
        return HexacoProfileResponse(
            name=profile.name,
            hexaco_profile=hexaco,
            sliders_preset=profile.sliders_preset or {},
            description=profile.description,
            gender=profile.gender or "Neutral",
            personality_preset=profile.personality_preset,
            is_dark_archetype=is_dark_archetype(hexaco),
            translated_config={
                "intuition_gain": translated.intuition_gain,
                "chaos_level": translated.chaos_level,
                "base_decay_rate": translated.base_decay_rate,
            }
        )


@router.get("/presets", response_model=PresetListResponse)
async def get_presets():
    """
    Get all available character presets.
    """
    return PresetListResponse(
        light_presets=TraitTranslationEngine.PRESETS_LIGHT,
        dark_presets=TraitTranslationEngine.PRESETS_DARK
    )


@router.post("/presets/{preset_name}", response_model=HexacoProfileResponse)
async def apply_preset(preset_name: str, profile_name: str = "default"):
    """
    Apply a preset to a character profile.
    Sets personality_preset name and recalculates sliders_preset from HEXACO.
    """
    preset = TraitTranslationEngine.ALL_PRESETS.get(preset_name)
    if not preset:
        raise HTTPException(status_code=404, detail=f"Preset '{preset_name}' not found")
    
    async with AsyncSessionLocal() as session:
        stmt = select(AgentProfileModel).where(AgentProfileModel.name == profile_name)
        result = await session.execute(stmt)
        profile = result.scalar_one_or_none()
        
        if not profile:
            profile = AgentProfileModel(
                name=profile_name,
                hexaco_profile=preset,
                personality_preset=preset_name
            )
            session.add(profile)
        else:
            profile.hexaco_profile = preset
            profile.personality_preset = preset_name
        
        # Translate preset HEXACO to sliders
        translator = TraitTranslationEngine(preset)
        translated = translator.translate()
        
        current_sliders = profile.sliders_preset or {}
        profile.sliders_preset = {
            "empathy_bias": translated.intuition_gain,
            "risk_tolerance": translated.persistence,
            "dominance_level": translated.striatum_agent_weight,
            "pace_setting": translated.social_agent_weight,
            "chaos_level": translated.chaos_level,
            "persistence": translated.persistence,
            "pred_sensitivity": translated.pred_sensitivity,
            "learning_speed": current_sliders.get("learning_speed", 0.5),
            "pred_threshold": current_sliders.get("pred_threshold", 0.65)
        }
        
        await session.commit()
        await session.refresh(profile)
        
        # Ensure hexaco_profile is never None
        hexaco = profile.hexaco_profile
        if hexaco is None:
            hexaco = {"H": 50, "E": 50, "X": 50, "A": 50, "C": 50, "O": 50}
        
        return HexacoProfileResponse(
            name=profile.name,
            hexaco_profile=hexaco,
            sliders_preset=profile.sliders_preset or {},
            description=profile.description,
            gender=profile.gender or "Neutral",
            personality_preset=profile.personality_preset,
            is_dark_archetype=is_dark_archetype(preset)
        )


# Mount router to app
app.include_router(router)
