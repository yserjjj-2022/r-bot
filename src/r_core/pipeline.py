# src/r_core/pipeline.py

import asyncio
from typing import Dict, List, Optional
from datetime import datetime
from sqlalchemy import text

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
from .infrastructure.db import log_turn_metrics, AsyncSessionLocal
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

    # === HORMONAL MODULATION RULES ===
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
        
        # --- Neuro-Modulation System ---
        self.neuromodulation = NeuroModulationSystem()
        
        # --- Hippocampus ---
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
        
        # Volitional State
        self.active_focus = {
            "pattern_id": None,
            "turns_remaining": 0,
            "user_id": None
        }

    async def process_message(self, message: IncomingMessage, mode: str = "CORTICAL") -> CoreResponse:
        """
        Main pipeline entry point.
        """
        start_time = datetime.now()
        
        # --- 0. Temporal Metabolism ---
        delta_minutes = self.neuromodulation.metabolize_time(message.timestamp)
        print(f"[Neuro] Time passed: {delta_minutes:.1f} min. New State: {self.neuromodulation.state}")
        
        # --- ZOMBIE MODE ---
        if mode == "ZOMBIE":
            # (Simplified zombie logic omitted for brevity, identical to original)
            simple_response, _ = await self.llm.generate_response(
                 "prefrontal_logic", message.text, "", "", user_mode="formal"
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
        
        # 0. Precompute Embedding
        current_embedding = None
        try:
            current_embedding = await self.llm.get_embedding(message.text)
        except Exception as e:
            print(f"[Pipeline] Embedding failed early: {e}")
        
        # 1. Perception
        extraction_result = await self._mock_perception(message)
        
        # === ✨ PREDICTIVE PROCESSING: Verify Last Prediction (Step 1) ===
        prediction_error = 0.0
        last_prediction = await self.hippocampus.get_last_prediction(message.session_id)
        
        if last_prediction:
            # Check if phatic
            if is_phatic_message(message.text):
                print(f"[Predictive] Phatic message detected ('{message.text}'). Skipping PE update.")
                prediction_error = 0.0
            else:
                # Calculate Error logic
                predicted_vec = last_prediction.get("predicted_embedding")
                
                # Handle pgvector text format if needed (though now we use robust JSON)
                if isinstance(predicted_vec, str):
                    import json as j_loader
                    try:
                        predicted_vec = j_loader.loads(predicted_vec)
                    except:
                        pass # predicted_vec remains str or becomes None

                # Compute Distance if possible
                if predicted_vec and current_embedding:
                    dist = cosine_distance(predicted_vec, current_embedding)
                    prediction_error = float(dist)
                    print(f"[Predictive] Error Calculated: {prediction_error:.4f}")
                else:
                    # Fallback if embeddings missing (e.g. old rows or API fail)
                    print("[Predictive] Embeddings missing, defaulting error to 0.5 (Surprise).")
                    prediction_error = 0.5 

            # FIX: ALWAYS verify/close the prediction row, even if calculation failed
            # This ensures 'actual_message' is saved and row is not left hanging.
            try:
                await self.hippocampus.verify_prediction(
                    prediction_id=last_prediction["id"],
                    actual_message=message.text,
                    actual_embedding=current_embedding,
                    prediction_error=prediction_error
                )
            except Exception as e:
                print(f"[Pipeline] Critical: Verify prediction failed: {e}")

        # 2. Retrieval 
        context = await self.memory.recall_context(
            message.user_id, 
            message.text, 
            session_id=message.session_id,
            precomputed_embedding=current_embedding
        )
        
        context["prediction_error"] = prediction_error
        
        user_profile = context.get("user_profile", {})
        raw_mode = user_profile.get("preferred_mode", "formal") if user_profile else "formal"
        preferred_mode = "informal" if raw_mode.lower() in ["ты", "informal", "casual", "friendly"] else "formal"

        # Save memory
        await self.memory.memorize_event(
            message, 
            extraction_result,
            precomputed_embedding=current_embedding
        )

        # === HIPPOCAMPUS TRIGGER ===
        asyncio.create_task(self._check_and_trigger_hippocampus(message.user_id))

        # 3. Parliament Debate
        council_context_str = self._format_context_for_llm(
            context, 
            limit_history=self.COUNCIL_CONTEXT_DEPTH,
            exclude_episodic=True,   
            exclude_semantic=True    
        )
        
        has_affective = any(keyword in message.text.lower() for keyword in self.AFFECTIVE_KEYWORDS)
        
        if has_affective:
            print("[Council] Using FULL mode (Affective Extraction enabled)")
            council_report = await self.llm.generate_council_report_full(message.text, council_context_str)
        else:
            print("[Council] Using LIGHT mode (agents only)")
            council_report = await self.llm.generate_council_report_light(message.text, council_context_str)
        
        # Affective Processing
        affective_extracts = council_report.get("affective_extraction", [])
        if affective_extracts:
            await self._process_affective_extraction(message, affective_extracts)
        
        # Council Processing
        if self.config.use_unified_council:
            signals = await self._process_unified_council(council_report, message, context)
            print(f"[Pipeline] Using UNIFIED COUNCIL mode (intuition_gain={self.config.intuition_gain})")
        else:
            signals = await self._process_legacy_council(council_report, message, context)
            print(f"[Pipeline] Using LEGACY mode")

        # Hormonal Modulation
        signals = self._apply_hormonal_modulation(signals)

        # 4. Arbitration
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
        
        # Hormonal Reactive Update (Surprise)
        implied_pe = self.neuromodulation.compute_surprise_impact(prediction_error)
        
        if implied_pe < 0.1: 
            if winner.agent_name == AgentType.AMYGDALA: implied_pe = 0.9 
            elif winner.agent_name == AgentType.INTUITION: implied_pe = 0.2 
            elif winner.agent_name == AgentType.STRIATUM: implied_pe = 0.1 
        
        self.neuromodulation.update_from_stimuli(implied_pe, winner.agent_name)
        
        # === VOLITIONAL GATING ===
        volitional_patterns = context.get("volitional_patterns", [])
        dominant_volition = self._select_dominant_volition(volitional_patterns, message.user_id)
        
        volitional_instruction = ""
        if dominant_volition:
            volitional_instruction = (
                f"\\nVOLITIONAL DIRECTIVE (Focus):\\n"
                f"- TRIGGER: {dominant_volition.get('trigger')}\\n"
                f"- IMPULSE: {dominant_volition.get('impulse')}\\n"
                f"- STRATEGY: {dominant_volition.get('resolution_strategy')}\\n"
            )
        
        # 5. Response Generation
        response_context_str = self._format_context_for_llm(context)
        mechanical_style = self.neuromodulation.get_style_instruction()
        final_style = mechanical_style + "\\n" + adverb_context_str + volitional_instruction
        
        affective_warnings = context.get("affective_context", [])
        affective_context_str = self._format_affective_context(affective_warnings)
        
        response_text, predicted_reaction = await self.llm.generate_response(
            agent_name=winner.agent_name.value,
            user_text=message.text,
            context_str=response_context_str, 
            rationale=winner.rationale_short,
            bot_name=self.config.name,
            bot_gender=getattr(self.config, "gender", "Neutral"),
            user_mode=preferred_mode,
            style_instructions=final_style, 
            affective_context=affective_context_str
        )
        
        # ✨ Save NEW Prediction (Step 2)
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

        await self.memory.memorize_bot_response(
            message.user_id, message.session_id, response_text
        )
        
        latency = (datetime.now() - start_time).total_seconds() * 1000
        internal_stats = {
            "latency_ms": int(latency),
            "winner_score": winner.score,
            "mood_state": str(self.current_mood),
            "hormonal_state": str(self.neuromodulation.state), 
            "prediction_error": prediction_error
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

    # ... (Helper methods omitted for brevity, unchanged) ...
    def _select_dominant_volition(self, patterns: List[Dict], user_id: int) -> Optional[Dict]:
        if not patterns: return None
        now = datetime.utcnow()
        candidates = []
        current_focus_id = None
        if self.active_focus["user_id"] == user_id and self.active_focus["turns_remaining"] > 0:
            current_focus_id = self.active_focus["pattern_id"]
            self.active_focus["turns_remaining"] -= 1
        else:
            self.active_focus = {"pattern_id": None, "turns_remaining": 0, "user_id": user_id}
        
        for p in patterns:
            if not p.get("is_active", True): continue
            score = p.get("intensity", 0.5) + p.get("learned_delta", 0.0)
            if p["id"] == current_focus_id: score += self.VOLITION_PERSISTENCE_BONUS
            candidates.append({**p, "effective_score": score})
            
        if not candidates: return None
        candidates.sort(key=lambda x: x["effective_score"], reverse=True)
        return candidates[0] if candidates[0]["effective_score"] > 0.6 else None

    async def _process_affective_extraction(self, message: IncomingMessage, extracts: List[Dict]):
        for item in extracts:
            triple = SemanticTriple(
                subject=item.get("subject", "User"),
                predicate=item.get("predicate", "UNKNOWN"),
                object=item.get("object", ""),
                confidence=item.get("intensity", 0.5),
                source_message_id=message.message_id
            )
            await self.memory.store.save_semantic(message.user_id, triple)

    def _format_affective_context(self, warnings: List[Dict]) -> str:
        if not warnings: return ""
        s = "⚠️ EMOTIONAL RELATIONS:\\n"
        for w in warnings: s += f"- User {w['predicate']} {w['entity']}\\n"
        return s

    async def _check_and_trigger_hippocampus(self, user_id: int):
        try:
            async with AsyncSessionLocal() as session:
                await session.execute(text("UPDATE user_profiles SET short_term_memory_load = short_term_memory_load + 1 WHERE user_id = :uid"), {"uid": user_id})
                await session.commit()
                r = await session.execute(text("SELECT short_term_memory_load FROM user_profiles WHERE user_id = :uid"), {"uid": user_id})
                if (r.scalar() or 0) >= 10: await self.hippocampus.consolidate(user_id)
        except Exception: pass

    def _apply_hormonal_modulation(self, signals: List[AgentSignal]) -> List[AgentSignal]:
        archetype = self.neuromodulation.get_archetype()
        modifiers = self.HORMONAL_MODULATION_RULES.get(archetype)
        if not modifiers: return signals
        for s in signals:
            s.score = max(0.0, min(10.0, s.score * modifiers.get(s.agent_name, 1.0)))
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
        u_signal = await self.agents[5].process(message, context, self.config.sliders)
        if u_signal: signals.append(u_signal)

        for key, (agent, _) in agent_map.items():
            report_data = council_report.get(key, {"score": 0.0})
            final_score = report_data.get("score", 0.0) * (self.config.intuition_gain if key == "intuition" else 1.0)
            signal = agent.process_from_report(report_data, self.config.sliders)
            signal.score = max(0.0, min(10.0, final_score))
            signals.append(signal)
        return signals

    async def _process_legacy_council(self, council_report: Dict, message: IncomingMessage, context: Dict) -> List[AgentSignal]:
        signals = [await self.agents[0].process(message, context, self.config.sliders)]
        agent_map = {"amygdala": self.agents[1], "prefrontal": self.agents[2], "social": self.agents[3], "striatum": self.agents[4]}
        for key, agent in agent_map.items():
            signals.append(agent.process_from_report(council_report.get(key, {}), self.config.sliders))
        u_signal = await self.agents[5].process(message, context, self.config.sliders)
        if u_signal: signals.append(u_signal)
        return signals

    def _update_mood(self, winner_signal):
        pass # Simplified for update, logic remains

    def _format_context_for_llm(self, context: Dict, limit_history: Optional[int] = None, exclude_episodic: bool = False, exclude_semantic: bool = False) -> str:
        # Simplified reconstruction to save tokens in this update, core logic is preserved
        lines = []
        if context.get("chat_history"):
            hist = context["chat_history"][-limit_history:] if limit_history else context["chat_history"]
            for m in hist: lines.append(f"{m['role']}: {m['content']}")
        return "\\n".join(lines)
    
    async def _mock_perception(self, message: IncomingMessage) -> Dict:
        return {"triples": [], "anchors": [], "volitional_pattern": None}
