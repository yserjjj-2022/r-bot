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
    StriatumAgent
)
from .neuromodulation import NeuroModulationSystem
from .hippocampus import Hippocampus

class RCoreKernel:
    # === КОНФИГУРАЦИЯ КОНТЕКСТА ===
    COUNCIL_CONTEXT_DEPTH = 1  
    
    # === AFFECTIVE KEYWORDS ===
    AFFECTIVE_KEYWORDS = [
        "ненавижу", "боюсь", "люблю", "обожаю", "презираю", "терпеть не могу", "не выношу",
        "hate", "fear", "love", "enjoy", "despise", "adore", "can't stand"
    ]
    
    # === VOLITIONAL CONSTANTS ===
    VOLITION_PERSISTENCE_BONUS = 0.3  # Бонус для текущего фокуса
    VOLITION_DECAY_PER_DAY = 0.1      # Штраф за давность (если decay_rate не задан)
    VOLITION_FOCUS_DURATION = 3       # Сколько ходов длится фокус по умолчанию
    
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
            StriatumAgent(self.llm)
        ]
        
        # Volitional State (In-memory cache for session persistence)
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
        
        # --- 0. Temporal Metabolism (Sense of Time) ---
        delta_minutes = self.neuromodulation.metabolize_time(message.timestamp)
        print(f"[Neuro] Time passed: {delta_minutes:.1f} min. New State: {self.neuromodulation.state}")
        
        # --- ZOMBIE MODE ---
        if mode == "ZOMBIE":
            simple_response = await self.llm._safe_chat_completion(
                messages=[
                    {"role": "system", "content": "You are a helpful AI assistant. Answer concisely."},
                    {"role": "user", "content": message.text}
                ],
                response_format=None,
                json_mode=False
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
        # FIX: Await immediately to avoid RuntimeWarning
        extraction_result = await self._mock_perception(message)
        
        # 2. Retrieval 
        context = await self.memory.recall_context(
            message.user_id, 
            message.text, 
            session_id=message.session_id,
            precomputed_embedding=current_embedding
        )
        
        user_profile = context.get("user_profile", {})
        
        # Normalize user mode
        raw_mode = user_profile.get("preferred_mode", "formal") if user_profile else "formal"
        if raw_mode and raw_mode.lower() in ["ты", "informal", "casual", "friendly"]:
            preferred_mode = "informal"
        else:
            preferred_mode = "formal"

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
        
        # ✨ Unified Council
        if self.config.use_unified_council:
            signals = self._process_unified_council(council_report, message, context)
            print(f"[Pipeline] Using UNIFIED COUNCIL mode (intuition_gain={self.config.intuition_gain})")
        else:
            signals = await self._process_legacy_council(council_report, message, context)
            print(f"[Pipeline] Using LEGACY mode")

        # ✨ Apply Hormonal Modulation BEFORE arbitration
        signals = self._apply_hormonal_modulation(signals)

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
        implied_pe = 0.5
        if winner.agent_name == AgentType.AMYGDALA: implied_pe = 0.9 
        elif winner.agent_name == AgentType.INTUITION: implied_pe = 0.2 
        elif winner.agent_name == AgentType.STRIATUM: implied_pe = 0.1 
        
        self.neuromodulation.update_from_stimuli(implied_pe, winner.agent_name)
        
        # === ✨ VOLITIONAL GATING (New Feature) ===
        volitional_patterns = context.get("volitional_patterns", [])
        dominant_volition = self._select_dominant_volition(volitional_patterns, message.user_id)
        
        volitional_instruction = ""
        if dominant_volition:
            volitional_instruction = (
                f"\\nVOLITIONAL DIRECTIVE (Focus):\\n"
                f"- TRIGGER: {dominant_volition.get('trigger')}\\n"
                f"- IMPULSE: {dominant_volition.get('impulse')}\\n"
                f"- STRATEGY: {dominant_volition.get('resolution_strategy')}\\n"
                f"- NOTE: {dominant_volition.get('action_taken')}\\n"
            )
            print(f"[Volition] Selected dominant pattern: {dominant_volition.get('impulse')} (score={dominant_volition.get('effective_score', 0):.2f})")
        
        # 5. Response Generation
        response_context_str = self._format_context_for_llm(context)
        bot_gender = getattr(self.config, "gender", "Neutral")
        
        mechanical_style_instruction = self.neuromodulation.get_style_instruction()
        final_style_instructions = mechanical_style_instruction + "\\n" + adverb_context_str + volitional_instruction
        
        # Affective Context for LLM
        affective_warnings = context.get("affective_context", [])
        affective_context_str = self._format_affective_context(affective_warnings)
        
        response_text = await self.llm.generate_response(
            agent_name=winner.agent_name.value,
            user_text=message.text,
            context_str=response_context_str, 
            rationale=winner.rationale_short,
            bot_name=self.config.name,
            bot_gender=bot_gender,
            user_mode=preferred_mode,
            style_instructions=final_style_instructions, 
            affective_context=affective_context_str
        )
        
        await self.memory.memorize_bot_response(
            message.user_id, 
            message.session_id, 
            response_text
        )
        
        latency = (datetime.now() - start_time).total_seconds() * 1000
        
        internal_stats = {
            "latency_ms": int(latency),
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
            "council_mode": "FULL" if has_affective else "LIGHT" 
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

    # === HELPER METHODS (RESTORED) ===
    
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
            
            triple = SemanticTriple(
                subject=item.get("subject", "User"),
                predicate=predicate,
                object=item.get("object", ""),
                confidence=intensity,
                source_message_id=message.message_id,
                sentiment=sentiment_vad
            )
            
            await self.memory.store.save_semantic(message.user_id, triple)
            print(f"[Affective ToM] Saved: {triple.subject} {triple.predicate} {triple.object}")

    def _format_affective_context(self, warnings: List[Dict]) -> str:
        if not warnings: return ""
        s = "⚠️ EMOTIONAL RELATIONS (User's Preferences):\\n"
        for warn in warnings:
            entity = warn["entity"]
            predicate = warn["predicate"]
            feeling = warn["user_feeling"]
            intensity = warn["intensity"]
            if feeling == "NEGATIVE":
                s += f"- ⚠️ AVOID mentioning '{entity}' (User {predicate} it, intensity={intensity:.2f}).\\n"
            else:
                s += f"- 💚 User {predicate} '{entity}' (intensity={intensity:.2f}).\\n"
        return s

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
                
                # FIX: Set threshold to 10
                THRESHOLD = 10 
                
                if load >= THRESHOLD:
                    print(f"[Hippocampus] Triggered consolidation for user {user_id} (load={load})")
                    await self.hippocampus.consolidate(user_id)
        except Exception as e:
            print(f"[Pipeline] Hippocampus trigger failed: {e}")

    def _apply_hormonal_modulation(self, signals: List[AgentSignal]) -> List[AgentSignal]:
        archetype = self.neuromodulation.get_archetype()
        MODULATION_MAP = {
            "RAGE": {AgentType.AMYGDALA: 1.6, AgentType.PREFRONTAL: 0.6, AgentType.SOCIAL: 0.8},
            "FEAR": {AgentType.AMYGDALA: 1.8, AgentType.STRIATUM: 0.4, AgentType.PREFRONTAL: 0.7},
            "BURNOUT": {AgentType.PREFRONTAL: 0.3, AgentType.INTUITION: 1.5, AgentType.AMYGDALA: 1.2},
            "SHAME": {AgentType.INTUITION: 1.3},
            "TRIUMPH": {AgentType.STRIATUM: 1.3, AgentType.AMYGDALA: 0.5, AgentType.PREFRONTAL: 1.1}
        }
        
        if archetype not in MODULATION_MAP: return signals
        print(f"[Hormonal Override] {archetype} is modulating agent scores")
        
        modifiers = MODULATION_MAP[archetype]
        default_mod = 0.8 if archetype == "SHAME" else 1.0
        
        for signal in signals:
            mod = modifiers.get(signal.agent_name, default_mod)
            signal.score = max(0.0, min(10.0, signal.score * mod))
        return signals

    def _process_unified_council(self, council_report: Dict, message: IncomingMessage, context: Dict) -> List[AgentSignal]:
        signals = []
        agent_map = {
            "intuition": (self.agents[0], AgentType.INTUITION),
            "amygdala": (self.agents[1], AgentType.AMYGDALA),
            "prefrontal": (self.agents[2], AgentType.PREFRONTAL),
            "social": (self.agents[3], AgentType.SOCIAL),
            "striatum": (self.agents[4], AgentType.STRIATUM)
        }
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
        return signals

    def _update_mood(self, winner_signal):
        INERTIA = 0.7
        SENSITIVITY = 0.3
        impact_map = {
            AgentType.AMYGDALA:  MoodVector(valence=-0.8, arousal=0.9, dominance=0.8),
            AgentType.STRIATUM:  MoodVector(valence=0.8, arousal=0.7, dominance=0.3),
            AgentType.SOCIAL:    MoodVector(valence=0.5, arousal=-0.2, dominance=-0.1),
            AgentType.PREFRONTAL:MoodVector(valence=0.0, arousal=-0.5, dominance=0.1),
            AgentType.INTUITION: MoodVector(valence=0.0, arousal=0.1, dominance=0.0)
        }
        impact = impact_map.get(winner_signal.agent_name, MoodVector())
        force = SENSITIVITY if winner_signal.score > 4.0 else 0.05
        
        self.current_mood.valence = max(-1.0, min(1.0, (self.current_mood.valence * INERTIA) + (impact.valence * force)))
        self.current_mood.arousal = max(-1.0, min(1.0, (self.current_mood.arousal * INERTIA) + (impact.arousal * force)))
        self.current_mood.dominance = max(-1.0, min(1.0, (self.current_mood.dominance * INERTIA) + (impact.dominance * force)))

    def _format_context_for_llm(self, context: Dict, limit_history: Optional[int] = None, exclude_episodic: bool = False, exclude_semantic: bool = False) -> str:
        lines = []
        profile = context.get("user_profile")
        if profile:
            lines.append("USER PROFILE (Core Identity):")
            if profile.get("name"): lines.append(f"- Name: {profile['name']}")
            if profile.get("gender"): lines.append(f"- Gender: {profile['gender']}")
            if profile.get("preferred_mode"): lines.append(f"- Address Style: {profile['preferred_mode']}")
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

    async def _mock_perception(self, message: IncomingMessage) -> Dict:
        await asyncio.sleep(0.05)
        return {
            "triples": [], 
            "anchors": [{"raw_text": message.text, "emotion_score": 0.5, "tags": ["auto"]}], 
            "volitional_pattern": None
        }
