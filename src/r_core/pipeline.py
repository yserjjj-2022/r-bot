import asyncio
import random
from typing import Dict, List, Optional
from datetime import datetime
from sqlalchemy import text, select


from .schemas import (
    IncomingMessage, 
    CoreResponse, 
    CoreAction, 
    BotConfig, 
    ProcessingMode,
    AgentType,
    MoodVector,
    SemanticTriple,
    AgentSignal,
    HormonalState 
)
from .memory import MemorySystem
from .infrastructure.llm import LLMService
from .infrastructure.db import log_turn_metrics, AsyncSessionLocal, AgentProfileModel, UserProfileModel
from .agents import (
    IntuitionAgent,
    AmygdalaAgent,
    PrefrontalAgent,
    SocialAgent,
    StriatumAgent,
    UncertaintyAgent
)
from .neuromodulation import NeuroModulationSystem
from .hippocampus import Hippocampus
from .behavioral_config import behavioral_config
from .utils import is_phatic_message, cosine_distance 


class RCoreKernel:
    # === КОНФИГУРАЦИЯ КОНТЕКСТА ===
    COUNCIL_CONTEXT_DEPTH = 1  
    
    # === AFFECTIVE KEYWORDS ===
    AFFECTIVE_KEYWORDS = [
        "ненавижу", "боюсь", "люблю", "обожаю", "презираю", "терпеть не могу", "не выношу",
        "hate", "fear", "love", "enjoy", "despise", "adore", "can't stand"
    ]
    
    # === VOLITIONAL CONSTANTS ===
    VOLITION_PERSISTENCE_BONUS = 0.3 
    VOLITION_DECAY_PER_DAY = 0.1      
    VOLITION_FOCUS_DURATION = 3       


    # === HORMONAL MODULATION RULES (Introspection Exposed) ===
    HORMONAL_MODULATION_RULES = {
        "RAGE": {AgentType.AMYGDALA: 1.6, AgentType.PREFRONTAL: 0.6, AgentType.SOCIAL: 0.8},
        "FEAR": {AgentType.AMYGDALA: 1.8, AgentType.STRIATUM: 0.4, AgentType.PREFRONTAL: 0.7},
        "BURNOUT": {AgentType.PREFRONTAL: 0.3, AgentType.INTUITION: 1.5, AgentType.AMYGDALA: 1.2},
        "SHAME": {AgentType.INTUITION: 1.3},
        "TRIUMPH": {AgentType.STRIATUM: 1.3, AgentType.AMYGDALA: 0.5, AgentType.PREFRONTAL: 1.1}
    }
    
    def __init__(self, config: BotConfig):
        self.config = config
        self.llm = LLMService() 
        self.memory = MemorySystem(store=None)
        
        # --- EHS: Internal State ---
        self.current_mood = MoodVector(valence=0.1, arousal=0.1, dominance=0.0) 
        
        # --- Neuro-Modulation System (Hormonal Physics) ---
        self.neuromodulation = NeuroModulationSystem()
        
        # --- Hippocampus (Lazy Consolidation) ---
        self.hippocampus = Hippocampus(
            llm_client=self.llm,
            embedding_client=self.llm
        )
        
        # Init agents
        self.agents = [
            IntuitionAgent(self.llm),
            AmygdalaAgent(self.llm),
            PrefrontalAgent(self.llm),
            SocialAgent(self.llm),
            StriatumAgent(self.llm),
            UncertaintyAgent(self.llm) 
        ]
        
        # Volitional State (In-memory cache for session persistence)
        self.active_focus = {
            "pattern_id": None,
            "turns_remaining": 0,
            "user_id": None
        }


    def get_architecture_snapshot(self) -> Dict:
        """
        Возвращает текущую структуру управления для визуализации.
        """
        return {
            "active_agents": [
                {
                    "name": agent.agent_type.value if hasattr(agent, 'agent_type') else "Unknown",
                    "class": agent.__class__.__name__,
                    "description": agent.__doc__.strip().split('\n')[0] if agent.__doc__ else "No docstring"
                }
                for agent in self.agents
            ],
            "control_sliders": self.config.sliders.dict(),
            "modulation_rules": self.HORMONAL_MODULATION_RULES,
            "subsystems": {
                "hippocampus": "Active" if self.hippocampus else "Disabled",
                "council_mode": "Unified" if self.config.use_unified_council else "Legacy",
                "predictive_processing": "Active" 
            }
        }


    async def process_message(self, message: IncomingMessage, mode: str = "CORTICAL") -> CoreResponse:
        """
        Main pipeline entry point.
        """
        start_time = datetime.now()
        
        # --- 0. Temporal Metabolism (Sense of Time) ---
        delta_minutes = self.neuromodulation.metabolize_time(message.timestamp)
        print(f"[Neuro] Time passed: {delta_minutes:.1f} min. New State: {self.neuromodulation.state}")
        
        # --- ZOMBIE MODE ---
        if mode == "ZOMBIE":
            simple_response, _ = await self.llm.generate_response( 
                 "prefrontal", message.text, "", "", user_mode="formal"
            )
            latency = (datetime.now() - start_time).total_seconds() * 1000
            
            return CoreResponse(
                actions=[CoreAction(type="send_text", payload={"text": str(simple_response)})],
                winning_agent=AgentType.PREFRONTAL,
                current_mood=MoodVector(),
                processing_mode=ProcessingMode.FAST_PATH,
                internal_stats={"latency_ms": int(latency), "mode": "ZOMBIE"}
            )


        # --- CORTICAL MODE (Full Architecture) ---
        
        # === ✨ RESTORE IDENTITY: Fetch Active Agent Profile from DB ===
        bot_description = ""
        try:
            async with AsyncSessionLocal() as session:
                # 1. Fetch Agent Profile
                print(f"[Identity] Searching for profile: '{self.config.name}'")
                
                # Try to find by config name first
                stmt = select(AgentProfileModel).where(AgentProfileModel.name == self.config.name)
                result = await session.execute(stmt)
                agent_profile = result.scalar_one_or_none()
                
                # FALLBACK: If specific name not found, try to load the single "Main" profile from DB
                # This handles cases where config has default "R-Bot" but DB has "Lyutik"
                if not agent_profile:
                     print(f"[Identity] Profile '{self.config.name}' not found. Falling back to first available profile.")
                     stmt = select(AgentProfileModel).limit(1)
                     result = await session.execute(stmt)
                     agent_profile = result.scalar_one_or_none()

                if agent_profile:
                    print(f"[Identity] Loaded Profile: {agent_profile.name} (Gender: {agent_profile.gender})")
                    # Update Config in Runtime
                    self.config.name = agent_profile.name
                    self.config.gender = agent_profile.gender or "Neutral"
                    if agent_profile.description:
                        bot_description = agent_profile.description
                        print(f"[Identity] Loaded description preview: {bot_description[:50]}...")
                    
                    # Update Experimental Controls
                    if hasattr(agent_profile, "intuition_gain"):
                        self.config.intuition_gain = agent_profile.intuition_gain
                    if hasattr(agent_profile, "use_unified_council"):
                        self.config.use_unified_council = agent_profile.use_unified_council
                    
                    # Update Sliders (if present and valid)
                    if agent_profile.sliders_preset:
                        try:
                            # Assuming sliders_preset matches Schema structure partially
                            for k, v in agent_profile.sliders_preset.items():
                                if hasattr(self.config.sliders, k):
                                    setattr(self.config.sliders, k, float(v))
                        except Exception as e:
                            print(f"[Identity] Failed to apply sliders: {e}")
                else:
                    print(f"[Identity] No agent profile found in DB. Using defaults.")

        except Exception as e:
            print(f"[Identity] DB Fetch Failed: {e}")


        # 0. Precompute Embedding 
        current_embedding = None
        try:
            current_embedding = await self.llm.get_embedding(message.text)
        except Exception as e:
            print(f"[Pipeline] Embedding failed early: {e}")
        
        
        # === ✨ PREDICTIVE PROCESSING: Verify Last Prediction (Step 1) ===
        prediction_error = 0.0
        last_prediction = await self.hippocampus.get_last_prediction(message.session_id)
        
        if last_prediction:
            # 1. Determine Logic
            is_phatic = is_phatic_message(message.text)
            
            predicted_vec = last_prediction.get("predicted_embedding")
            if isinstance(predicted_vec, str):
                import json as j_loader
                try:
                    predicted_vec = j_loader.loads(predicted_vec)
                except:
                    predicted_vec = None
            
            # 2. Calculate Error
            if not is_phatic and predicted_vec and current_embedding:
                dist = cosine_distance(predicted_vec, current_embedding)
                prediction_error = float(dist)
                print(f"[Predictive] Error Calculated: {prediction_error:.4f} (Prev: '{last_prediction['predicted_reaction']}' vs Real: '{message.text}')")
            elif is_phatic:
                print(f"[Predictive] Phatic message detected ('{message.text}'). Force PE=0.0.")
                prediction_error = 0.0 
            else:
                 print("[Predictive] Embeddings missing or invalid, default PE=0.0.")


            # 3. ALWAYS Verify in DB (Close the loop)
            try:
                print(f"[Predictive] Closing Loop for PredID={last_prediction['id']}. Writing actual_msg='{message.text}'")
                await self.hippocampus.verify_prediction(
                    prediction_id=last_prediction["id"],
                    actual_message=message.text,
                    actual_embedding=current_embedding,
                    prediction_error=prediction_error
                )
            except Exception as e:
                print(f"[Predictive] ❌ DB WRITE ERROR: Failed to verify prediction {last_prediction['id']}: {e}")


        # 2. Retrieval 
        context = await self.memory.recall_context(
            message.user_id, 
            message.text, 
            session_id=message.session_id,
            precomputed_embedding=current_embedding
        )
        
        # Inject Prediction Error into Context for Agents
        context["prediction_error"] = prediction_error
        
        user_profile = context.get("user_profile", {})
        
        raw_mode = user_profile.get("preferred_mode", "formal") if user_profile else "formal"
        if raw_mode and raw_mode.lower() in ["ты", "informal", "casual", "friendly"]:
            preferred_mode = "informal"
        else:
            preferred_mode = "formal"


        # === 3. PERCEPTION & VOLITIONAL DETECTION (Revised) ===
        # Now that we have context (history), we can run the Volitional Detector
        extraction_result = await self._perception_stage(message, context.get("chat_history", []))

        # === HIPPOCAMPUS TRIGGER ===
        asyncio.create_task(self._check_and_trigger_hippocampus(message.user_id))


        # 4. Parliament Debate
        council_context_str = self._format_context_for_llm(
            context, 
            limit_history=self.COUNCIL_CONTEXT_DEPTH,
            exclude_episodic=True,   
            exclude_semantic=True    
        )
        
        # ✨ Conditional Council Mode
        has_affective = any(keyword in message.text.lower() for keyword in self.AFFECTIVE_KEYWORDS)
        
        if has_affective:
            print("[Council] Using FULL mode (Affective Extraction enabled)")
            council_report = await self.llm.generate_council_report_full(message.text, council_context_str)
        else:
            print("[Council] Using LIGHT mode (agents only)")
            council_report = await self.llm.generate_council_report_light(message.text, council_context_str)
        
        # ✨ Affective Extraction Processing
        affective_extracts = council_report.get("affective_extraction", [])
        affective_triggers_count = 0
        if affective_extracts:
            await self._process_affective_extraction(message, affective_extracts)
            affective_triggers_count = len(affective_extracts)
        
        # ✨ Unified Council + Uncertainty Agent
        if self.config.use_unified_council:
            signals = await self._process_unified_council(council_report, message, context) 
            print(f"[Pipeline] Using UNIFIED COUNCIL mode (intuition_gain={self.config.intuition_gain})")
        else:
            signals = await self._process_legacy_council(council_report, message, context)
            print(f"[Pipeline] Using LEGACY mode")


        # === ✨ VOLITIONAL GATING (Step 1: Selection) ===
        volitional_patterns = context.get("volitional_patterns", [])
        dominant_volition = self._select_dominant_volition(volitional_patterns, message.user_id)
        
        volitional_instruction = ""
        if dominant_volition:
            impulse = dominant_volition.get("impulse", "UNKNOWN")
            fuel = dominant_volition.get("fuel", 0.5)
            
            volitional_instruction = (
                f"\\nVOLITIONAL DIRECTIVE (Focus):\\n"
                f"- TARGET: {dominant_volition.get('target')}\\n"
                f"- IMPULSE: {impulse} (Fuel Level: {fuel:.2f})\\n"
                f"- STRATEGY: {dominant_volition.get('resolution_strategy')}\\n"
            )
            print(f"[Volition] Selected dominant pattern: {impulse} (fuel={fuel:.2f})")


        # ✨ Apply Hormonal Modulation BEFORE arbitration
        signals = self._apply_hormonal_modulation(signals)
        
        # === ✨ VOLITIONAL MODULATION (Step 2: Matrix Application) ===
        # This applies the 'Matrix' multipliers to agent scores
        if dominant_volition:
            signals = self._apply_volitional_modulation(signals, dominant_volition)
        
        # ✨ Apply CHAOS Injection (Entropy) BEFORE arbitration
        signals = self._apply_chaos(signals)


        # 4. Arbitration & Mood Update
        signals.sort(key=lambda s: s.score, reverse=True)
        winner = signals[0]
        
        strong_losers = [s for s in signals if s.score > 5.0 and s.agent_name != winner.agent_name]
        
        adverb_instructions = []
        for loser in strong_losers:
            if loser.style_instruction:
                adverb_instructions.append(f"- {loser.agent_name.name}: {loser.style_instruction}")
        
        adverb_context_str = ""
        if adverb_instructions:
            adverb_context_str = "\\nSECONDARY STYLE MODIFIERS (Neuro-Modulation):\\n" + "\\n".join(adverb_instructions)
        
        self._update_mood(winner)
        
        # Hormonal Reactive Update
        implied_pe = prediction_error 
        if implied_pe < 0.3:
            if winner.agent_name == AgentType.AMYGDALA: implied_pe = 0.9 
            elif winner.agent_name == AgentType.INTUITION: implied_pe = 0.2 
            elif winner.agent_name == AgentType.STRIATUM: implied_pe = 0.1 
        
        self.neuromodulation.update_from_stimuli(implied_pe, winner.agent_name)
        
        
        # 5. Response Generation 
        response_context_str = self._format_context_for_llm(context)
        bot_gender = getattr(self.config, "gender", "Neutral")
        
        mechanical_style_instruction = self.neuromodulation.get_style_instruction()
        final_style_instructions = mechanical_style_instruction + "\\n" + adverb_context_str + volitional_instruction
        
        # Affective Context for LLM
        affective_warnings = context.get("affective_context", [])
        affective_context_str = self._format_affective_context(affective_warnings)
        
        # ✨ Generate Response + Prediction
        response_text, predicted_reaction = await self.llm.generate_response(
            agent_name=winner.agent_name.value,
            user_text=message.text,
            context_str=response_context_str, 
            rationale=winner.rationale_short,
            bot_name=self.config.name,
            bot_gender=bot_gender,
            bot_description=bot_description, # ✨ NEW: Pass the DB description
            user_mode=preferred_mode,
            style_instructions=final_style_instructions, 
            affective_context=affective_context_str
        )
        
        # === 6.1 SAVE MEMORY with REAL Emotion Score (Moved from start) ===
        # Calculate max intensity from emotional agents (Amygdala, Striatum, Social)
        hot_scores = [
            s.score for s in signals 
            if s.agent_name in [AgentType.AMYGDALA, AgentType.STRIATUM, AgentType.SOCIAL]
        ]
        max_hot = max(hot_scores) if hot_scores else 0.0
        real_emotion_score = max_hot / 10.0
        
        # Ensure extraction_result uses this real score if possible, or override in save
        # Actually memorize_event takes the whole extraction object.
        # We update it here:
        if extraction_result["anchors"]:
             extraction_result["anchors"][0]["emotion_score"] = real_emotion_score
        
        await self.memory.memorize_event(
            message, 
            extraction_result,
            precomputed_embedding=current_embedding
        )
        
        # === 6.2 SAVE BOT RESPONSE ===
        await self.memory.memorize_bot_response(
            message.user_id, 
            message.session_id, 
            response_text
        )
        
        # === 6.3 SAVE PREDICTION ===
        if predicted_reaction:
            try:
                pred_emb = await self.llm.get_embedding(predicted_reaction)
                
                await self.hippocampus.save_prediction(
                    user_id=message.user_id,
                    session_id=message.session_id,
                    bot_message=response_text,
                    predicted_reaction=predicted_reaction,
                    predicted_embedding=pred_emb
                )
                print(f"[Predictive] Saved hypothesis: '{predicted_reaction}'")
            except Exception as e:
                print(f"[Predictive] Failed to save prediction: {e}")
        
        latency = (datetime.now() - start_time).total_seconds() * 1000
        
        internal_stats = {
            "latency_ms": int(latency),
            "winner_agent": winner.agent_name.value, # ✨ FIXED: Explicitly save winner name
            "winner_score": winner.score,
            "winner_reason": winner.rationale_short,
            "all_scores": {s.agent_name.value: round(s.score, 2) for s in signals},
            "mood_state": str(self.current_mood),
            "hormonal_state": str(self.neuromodulation.state), 
            "hormonal_archetype": self.neuromodulation.get_archetype(),
            "active_style": final_style_instructions,
            "affective_triggers_detected": affective_triggers_count,
            "sentiment_context_used": bool(affective_warnings),
            "volition_selected": dominant_volition.get("impulse") if dominant_volition else None,
            "volition_persistence_active": self.active_focus["turns_remaining"] > 0,
            "modulators": [s.agent_name.value for s in strong_losers],
            "mode": "UNIFIED" if self.config.use_unified_council else "LEGACY",
            "council_mode": "FULL" if has_affective else "LIGHT",
            "prediction_error": prediction_error, 
            "next_prediction": predicted_reaction,
            "user_emotion_score": real_emotion_score # ✨ Log for debug
        }


        await log_turn_metrics(message.user_id, message.session_id, internal_stats)
        
        return CoreResponse(
            actions=[CoreAction(type="send_text", payload={"text": response_text})],
            winning_agent=winner.agent_name,
            current_mood=self.current_mood, 
            current_hormones=self.neuromodulation.state, 
            processing_mode=ProcessingMode.SLOW_PATH,
            internal_stats=internal_stats
        )


    # === HELPER METHODS ===
    
    def _format_affective_context(self, warnings: List[str]) -> str: 
        """
        Formats list of affective warnings into a single string for LLM prompt.
        """
        if not warnings:
            return ""
        
        warning_str = "\\nAFFECTIVE MEMORY WARNING:\\n"
        for w in warnings:
            warning_str += f"⚠️ {w}\\n"
        return warning_str

    
    def _apply_chaos(self, signals: List[AgentSignal]) -> List[AgentSignal]:
        """
        🌀 CHAOS INJECTION (Entropy)
        """
        chaos = getattr(self.config.sliders, "chaos_level", 0.0)
        
        if chaos <= 0.05: return signals
        
        print(f"[Chaos] Injecting entropy (level={chaos:.2f})")
        
        for s in signals:
            noise = (random.random() - 0.5) * (chaos * 4.0) 
            s.score = max(0.0, min(10.0, s.score + noise))
            if abs(noise) > 0.5:
                s.rationale_short += f" [Entropy {noise:+.1f}]"
                
        return signals
    
    def _select_dominant_volition(self, patterns: List[Dict], user_id: int) -> Optional[Dict]:
        """
        Winner-Takes-Volition mechanism.
        """
        if not patterns: return None
        now = datetime.utcnow()
        candidates = []
        current_focus_id = None
        
        # Check focus persistence
        if self.active_focus["user_id"] == user_id and self.active_focus["turns_remaining"] > 0:
            current_focus_id = self.active_focus["pattern_id"]
            self.active_focus["turns_remaining"] -= 1
        else:
            self.active_focus = {"pattern_id": None, "turns_remaining": 0, "user_id": user_id}
        
        for p in patterns:
            if not p.get("is_active", True): continue
            
            # Base Score
            score = p.get("intensity", 0.5) + p.get("learned_delta", 0.0)
            
            # Decay
            last_active = p.get("last_activated_at")
            if last_active and isinstance(last_active, datetime):
                days_passed = (now - last_active).days
                decay_rate = p.get("decay_rate") or self.VOLITION_DECAY_PER_DAY
                decay_penalty = days_passed * decay_rate
                score -= decay_penalty
            
            # Persistence Bonus
            if p["id"] == current_focus_id: score += self.VOLITION_PERSISTENCE_BONUS
            
            # Affective Filter
            if self.current_mood.arousal > 0.7 and self.current_mood.dominance < -0.3: score *= 0.2
            if self.current_mood.arousal > 0.7 and self.current_mood.dominance > 0.5: score *= 1.2
            
            candidates.append({**p, "effective_score": score})
            
        if not candidates: return None
        candidates.sort(key=lambda x: x["effective_score"], reverse=True)
        winner = candidates[0]
        
        # Set new focus if strong enough
        if winner["effective_score"] > 0.6:
            if winner["id"] != current_focus_id:
                self.active_focus["pattern_id"] = winner["id"]
                self.active_focus["turns_remaining"] = self.VOLITION_FOCUS_DURATION
                print(f"[Volition] New Focus Acquired: {winner['impulse']} (for {self.VOLITION_FOCUS_DURATION} turns)")
        
        return winner

    def _apply_volitional_modulation(self, signals: List[AgentSignal], pattern: Dict) -> List[AgentSignal]:
        """
        ⚖️ VOLITIONAL STRATEGY MATRIX IMPLEMENTATION
        Applies multipliers to agents based on Impulse Type and Fuel Level.
        Ref: docs/volitional_matrix.md
        """
        impulse = pattern.get("impulse", "").upper()
        fuel = pattern.get("fuel", 0.5)
        
        # Default Multipliers (No change)
        multipliers = {
            AgentType.INTUITION: 1.0,
            AgentType.AMYGDALA: 1.0,
            AgentType.PREFRONTAL: 1.0,
            AgentType.SOCIAL: 1.0,
            AgentType.STRIATUM: 1.0
        }
        
        strategy_name = "Standard"

        # === 1. LAZINESS / PROCRASTINATION ===
        if "LAZI" in impulse or "PROCRAST" in impulse or "APATHY" in impulse:
            if fuel < 0.4: # Low Fuel -> Baby Steps
                strategy_name = "Baby Steps (Low Fuel)"
                multipliers[AgentType.SOCIAL] = 1.5
                multipliers[AgentType.INTUITION] = 1.3
                multipliers[AgentType.PREFRONTAL] = 0.5 # Don't push logic
            elif fuel > 0.7: # High Fuel -> Challenge
                strategy_name = "Challenge (High Fuel)"
                multipliers[AgentType.PREFRONTAL] = 1.4
                multipliers[AgentType.STRIATUM] = 1.2
                multipliers[AgentType.SOCIAL] = 0.6
        
        # === 2. FEAR / ANXIETY ===
        elif "FEAR" in impulse or "ANXI" in impulse or "SCARE" in impulse:
            if fuel < 0.4: # Low Fuel -> Safe Space
                strategy_name = "Safe Space (Low Fuel)"
                multipliers[AgentType.SOCIAL] = 1.6
                multipliers[AgentType.AMYGDALA] = 1.2 # Validate fear
                multipliers[AgentType.PREFRONTAL] = 0.4
            elif fuel > 0.7: # High Fuel -> Deconstruction
                strategy_name = "Rationalization (High Fuel)"
                multipliers[AgentType.PREFRONTAL] = 1.5
                multipliers[AgentType.INTUITION] = 1.3
        
        # === 3. ANGER / RAGE ===
        elif "ANGER" in impulse or "RAGE" in impulse or "HATE" in impulse:
            if fuel < 0.4: # Low Fuel -> Ventilation
                strategy_name = "Ventilation (Low Fuel)"
                multipliers[AgentType.SOCIAL] = 1.8
                multipliers[AgentType.PREFRONTAL] = 0.2 # Do not argue
            elif fuel > 0.7: # High Fuel -> Redirection
                strategy_name = "Redirection (High Fuel)"
                multipliers[AgentType.AMYGDALA] = 1.3
                multipliers[AgentType.STRIATUM] = 1.4

        # === 4. BOREDOM ===
        elif "BORED" in impulse or "ROUTINE" in impulse:
            strategy_name = "Gamification"
            multipliers[AgentType.STRIATUM] = 1.5
            multipliers[AgentType.INTUITION] = 1.5
            multipliers[AgentType.PREFRONTAL] = 0.7

        print(f"[Volition] Applying Strategy: {strategy_name} (Fuel={fuel:.2f})")
        
        # Apply multipliers
        for s in signals:
            mult = multipliers.get(s.agent_name, 1.0)
            if mult != 1.0:
                s.score = max(0.0, min(10.0, s.score * mult))
                s.rationale_short += f" [Volition x{mult}]"
                
        return signals

    async def _process_affective_extraction(self, message: IncomingMessage, extracts: List[Dict]):
        """Helper to process extracted emotions"""
        for item in extracts:
            intensity = item.get("intensity", 0.5)
            predicate = item.get("predicate", "UNKNOWN")
            
            if predicate in ["HATES", "DESPISES", "FEARS"]: valence = -intensity
            elif predicate in ["LOVES", "ENJOYS", "ADORES"]: valence = intensity
            else: valence = 0.0
            
            sentiment_vad = {
                "valence": valence,
                "arousal": 0.5 if predicate == "FEARS" else 0.3,
                "dominance": -0.2 if predicate == "FEARS" else 0.0
            }
            
            # ✨ NEW: Compute embedding
            fact_text = f"{item.get('subject', 'User')} {predicate} {item.get('object', '')}"
            try:
                embedding = await self.llm.get_embedding(fact_text)
            except Exception as e:
                print(f"[Pipeline] Embedding generation failed for affective extraction: {e}")
                embedding = None

            triple = SemanticTriple(
                subject=item.get("subject", "User"),
                predicate=predicate,
                object=item.get("object", ""),
                confidence=intensity,
                source_message_id=message.message_id,
                sentiment=sentiment_vad,
                embedding=embedding 
            )
            
            await self.memory.store.save_semantic(message.user_id, triple)
            print(f"[Affective ToM] Saved: {triple.subject} {triple.predicate} {triple.object}")


    def _format_context_for_llm(self, context: Dict, limit_history: Optional[int] = None, exclude_episodic: bool = False, exclude_semantic: bool = False) -> str:
        lines = []
        profile = context.get("user_profile")
        if profile:
            lines.append("USER PROFILE (Core Identity):")
            if profile.get("name"): lines.append(f"- Name: {profile['name']}")
            if profile.get("gender"): lines.append(f"- Gender: {profile['gender']}")
            if profile.get("preferred_mode"): lines.append(f"- Address Style: {profile['preferred_mode']}")
            lines.append("")
            
        relevant_traits = context.get("relevant_traits", [])
        if relevant_traits:
            lines.append("CONTEXTUALLY RELEVANT TRAITS:")
            for trait in relevant_traits:
                lines.append(f"- {trait}")
            lines.append("")


        if context.get("chat_history"):
            chat_history = context["chat_history"]
            if limit_history is not None:
                chat_history = chat_history[-limit_history:]
            if chat_history:
                lines.append("RECENT DIALOGUE:")
                for msg in chat_history:
                    role = "User" if msg["role"] == "user" else "Assistant"
                    lines.append(f"{role}: {msg['content']}")
                lines.append("") 
        
        if not exclude_episodic and context.get("episodic_memory"):
            lines.append("PAST EPISODES (Long-term memory):")
            for ep in context["episodic_memory"]:
                lines.append(f"- {ep.get('raw_text', '')}")
            lines.append("")
        
        if not exclude_semantic and context.get("semantic_facts"):
            lines.append("KNOWN FACTS:")
            for fact in context["semantic_facts"]:
                lines.append(f"- {fact.get('subject')} {fact.get('predicate')} {fact.get('object')}")
            lines.append("")
                
        return "\\n".join(lines) if lines else "No prior context."


    async def _check_and_trigger_hippocampus(self, user_id: int):
        try:
            async with AsyncSessionLocal() as session:
                await session.execute(
                    text("UPDATE user_profiles SET short_term_memory_load = short_term_memory_load + 1 WHERE user_id = :uid"),
                    {"uid": user_id}
                )
                await session.commit()
                result = await session.execute(
                    text("SELECT short_term_memory_load FROM user_profiles WHERE user_id = :uid"),
                    {"uid": user_id}
                )
                load = result.scalar() or 0
                
                THRESHOLD = 10 
                
                if load >= THRESHOLD:
                    print(f"[Hippocampus] Triggered consolidation for user {user_id} (load={load})")
                    await self.hippocampus.consolidate(user_id)
        except Exception as e:
            print(f"[Pipeline] Hippocampus trigger failed: {e}")


    def _apply_hormonal_modulation(self, signals: List[AgentSignal]) -> List[AgentSignal]:
        archetype = self.neuromodulation.get_archetype()
        
        MODULATION_MAP = self.HORMONAL_MODULATION_RULES
        
        if archetype not in MODULATION_MAP: return signals
        print(f"[Hormonal Override] {archetype} is modulating agent scores")
        
        modifiers = MODULATION_MAP[archetype]
        default_mod = 0.8 if archetype == "SHAME" else 1.0
        
        for signal in signals:
            mod = modifiers.get(signal.agent_name, default_mod)
            signal.score = max(0.0, min(10.0, signal.score * mod))
        return signals


    async def _process_unified_council(self, council_report: Dict, message: IncomingMessage, context: Dict) -> List[AgentSignal]: 
        signals = []
        agent_map = {
            "intuition": (self.agents[0], AgentType.INTUITION),
            "amygdala": (self.agents[1], AgentType.AMYGDALA),
            "prefrontal": (self.agents[2], AgentType.PREFRONTAL),
            "social": (self.agents[3], AgentType.SOCIAL),
            "striatum": (self.agents[4], AgentType.STRIATUM)
        }
        
        uncertainty_agent = self.agents[5] 
        u_signal = await uncertainty_agent.process(message, context, self.config.sliders) 
        if u_signal:
             signals.append(u_signal)


        for key, (agent, agent_type) in agent_map.items():
            report_data = council_report.get(key, {"score": 0.0, "rationale": "No signal", "confidence": 0.5})
            base_score = report_data.get("score", 0.0)
            final_score = base_score * self.config.intuition_gain if key == "intuition" else base_score
            final_score = max(0.0, min(10.0, final_score))
            signal = agent.process_from_report(report_data, self.config.sliders)
            signal.score = final_score
            signals.append(signal)
            
        return signals


    async def _process_legacy_council(self, council_report: Dict, message: IncomingMessage, context: Dict) -> List[AgentSignal]:
        intuition_signal = await self.agents[0].process(message, context, self.config.sliders)
        signals = [intuition_signal]
        agent_map = {
            "amygdala": self.agents[1],
            "prefrontal": self.agents[2],
            "social": self.agents[3],
            "striatum": self.agents[4]
        }
        for key, agent in agent_map.items():
            report_data = council_report.get(key, {"score": 0.0, "rationale": "No signal"})
            signals.append(agent.process_from_report(report_data, self.config.sliders))
            
        uncertainty_agent = self.agents[5]
        u_signal = await uncertainty_agent.process(message, context, self.config.sliders) 
        if u_signal:
             signals.append(u_signal)
             
        return signals


    def _update_mood(self, winner_signal):
        INERTIA = 0.7
        SENSITIVITY = 0.3
        impact_map = {
            AgentType.AMYGDALA:  MoodVector(valence=-0.8, arousal=0.9, dominance=0.8),
            AgentType.STRIATUM:  MoodVector(valence=0.8, arousal=0.7, dominance=0.3),
            AgentType.SOCIAL:    MoodVector(valence=0.5, arousal=-0.2, dominance=-0.1),
            AgentType.PREFRONTAL:MoodVector(valence=0.0, arousal=-0.5, dominance=0.1),
            AgentType.INTUITION: MoodVector(valence=0.0, arousal=0.1, dominance=0.0),
            AgentType.UNCERTAINTY: MoodVector(valence=-0.2, arousal=0.4, dominance=-0.3) 
        }
        impact = impact_map.get(winner_signal.agent_name, MoodVector())
        force = SENSITIVITY if winner_signal.score > 4.0 else 0.05
        
        self.current_mood.valence = max(-1.0, min(1.0, (self.current_mood.valence * INERTIA) + (impact.valence * force)))
        self.current_mood.arousal = max(-1.0, min(1.0, (self.current_mood.arousal * INERTIA) + (impact.arousal * force)))
        self.current_mood.dominance = max(-1.0, min(1.0, (self.current_mood.dominance * INERTIA) + (impact.dominance * force)))


    async def _mock_perception(self, message: IncomingMessage) -> Dict:
        await asyncio.sleep(0.05)
        return {
            "triples": [], 
            "anchors": [{"raw_text": message.text, "emotion_score": 0.5, "tags": ["auto"]}], 
            "volitional_pattern": None
        }

    async def _perception_stage(self, message: IncomingMessage, chat_history: List[Dict]) -> Dict:
        """
        🔍 Perception Stage:
        1. Mock implementation for triples/anchors (Legacy)
        2. Real Volitional Detection using LLM (NEW)
        """
        # Format history string for LLM
        history_lines = [f"{m['role']}: {m['content']}" for m in chat_history[-6:]]
        history_str = "\\n".join(history_lines)
        
        volitional_pattern = None
        # Only run detection if history is sufficient
        if len(chat_history) >= 2:
             print("[Pipeline] Scanning for volitional patterns...")
             volitional_pattern = await self.llm.detect_volitional_pattern(message.text, history_str)
             if volitional_pattern:
                 print(f"[Pipeline] Pattern DETECTED: {volitional_pattern['trigger']} -> {volitional_pattern['impulse']}")
        
        return {
            "triples": [], 
            "anchors": [{"raw_text": message.text, "emotion_score": 0.5, "tags": ["auto"]}], 
            "volitional_pattern": volitional_pattern
        }
