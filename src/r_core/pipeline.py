import asyncio
from typing import Dict, List, Optional
from datetime import datetime

from .schemas import (
    IncomingMessage, 
    CoreResponse, 
    CoreAction, 
    BotConfig, 
    ProcessingMode,
    AgentType,
    MoodVector,
    SemanticTriple,
    AgentSignal
)
from .memory import MemorySystem
from .infrastructure.llm import LLMService
from .infrastructure.db import log_turn_metrics
from .agents import (
    IntuitionAgent,
    AmygdalaAgent,
    PrefrontalAgent,
    SocialAgent,
    StriatumAgent
)

class RCoreKernel:
    def __init__(self, config: BotConfig):
        self.config = config
        self.llm = LLMService() 
        self.memory = MemorySystem(store=None)
        
        # --- EHS: Internal State ---
        self.current_mood = MoodVector(valence=0.1, arousal=0.1, dominance=0.0) 
        
        # Init agents
        self.agents = [
            IntuitionAgent(self.llm),
            AmygdalaAgent(self.llm),
            PrefrontalAgent(self.llm),
            SocialAgent(self.llm),
            StriatumAgent(self.llm)
        ]

    async def process_message(self, message: IncomingMessage, mode: str = "CORTICAL") -> CoreResponse:
        """
        Main pipeline entry point.
        mode="CORTICAL" -> Full cognitive architecture (RAG, Agents, Profiling).
        mode="ZOMBIE" -> Simple LLM pass-through (No memory, No personality).
        """
        start_time = datetime.now()
        
        # --- ZOMBIE MODE (Bypass Everything) ---
        if mode == "ZOMBIE":
            # Just call LLM directly without system prompt engineering or memory
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
                winning_agent=AgentType.PREFRONTAL, # Dummy
                current_mood=MoodVector(), # Neutral
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
        perception_task = self._mock_perception(message)
        
        # 2. Retrieval 
        context = await self.memory.recall_context(
            message.user_id, 
            message.text, 
            session_id=message.session_id,
            precomputed_embedding=current_embedding
        )
        
        user_profile = context.get("user_profile", {})
        preferred_mode = user_profile.get("preferred_mode", "formal") if user_profile else "formal"

        # Save memory
        extraction_result = await perception_task
        await self.memory.memorize_event(
            message, 
            extraction_result,
            precomputed_embedding=current_embedding
        )

        # 3. Parliament Debate
        context_str = self._format_context_for_llm(context)
        
        # Council Report 
        council_report = await self.llm.generate_council_report(message.text, context_str)
        
        # --- Passive Profiling Update ---
        profile_update = council_report.get("profile_update")
        if profile_update:
            cleaned_update = {k: v for k, v in profile_update.items() if v is not None}
            if cleaned_update:
                print(f"[Profiling] Detected user identity update: {cleaned_update}")
                await self.memory.update_user_profile(message.user_id, cleaned_update)
        
        # ✨ NEW: Affective Extraction Processing
        affective_extracts = council_report.get("affective_extraction", [])
        affective_triggers_count = 0
        
        if affective_extracts:
            print(f"[Affective ToM] Detected {len(affective_extracts)} emotional relations")
            for item in affective_extracts:
                # Преобразуем intensity в VAD-формат
                intensity = item.get("intensity", 0.5)
                predicate = item.get("predicate", "UNKNOWN")
                
                # Рассчитываем valence на основе predicate
                if predicate in ["HATES", "DESPISES", "FEARS"]:
                    valence = -intensity
                elif predicate in ["LOVES", "ENJOYS", "ADORES"]:
                    valence = intensity
                else:
                    valence = 0.0
                
                sentiment_vad = {
                    "valence": valence,
                    "arousal": 0.5 if predicate == "FEARS" else 0.3,  # Страх вызывает больше arousal
                    "dominance": -0.2 if predicate == "FEARS" else 0.0
                }
                
                # Сохраняем в граф знаний
                triple = SemanticTriple(
                    subject=item.get("subject", "User"),
                    predicate=predicate,
                    object=item.get("object", ""),
                    confidence=intensity,
                    source_message_id=message.message_id,
                    sentiment=sentiment_vad
                )
                
                await self.memory.store.save_semantic(message.user_id, triple)
                affective_triggers_count += 1
                print(f"[Affective ToM] Saved: {triple.subject} {triple.predicate} {triple.object} (valence={valence:.2f})")
        
        # ✨ Feature Flag - Unified Council vs Legacy
        # Рассчитываем intuition_gain из pace_setting (унифицированный подход)
        intuition_gain_calculated = 1.5 - self.config.sliders.pace_setting
        
        if self.config.use_unified_council:
            # NEW LOGIC: All agents processed through council_report (including Intuition)
            signals = self._process_unified_council(council_report, intuition_gain_calculated)
            print(f"[Pipeline] UNIFIED COUNCIL mode | pace={self.config.sliders.pace_setting:.2f} → intuition_gain={intuition_gain_calculated:.2f}")
        else:
            # OLD LOGIC: Intuition processed separately (uses modifiers from agents.py)
            signals = await self._process_legacy_council(council_report, message, context)
            print(f"[Pipeline] LEGACY mode | pace={self.config.sliders.pace_setting:.2f} (modifiers in agents.py)")

        # 4. Arbitration & Mood Update
        signals.sort(key=lambda s: s.score, reverse=True)
        winner = signals[0]
        
        # --- Neuro-Modulation (Adverbs) ---
        # Strong Losers: Score > 5.0 AND not the winner
        strong_losers = [s for s in signals if s.score > 5.0 and s.agent_name != winner.agent_name]
        
        adverb_instructions = []
        for loser in strong_losers:
            if loser.style_instruction:
                adverb_instructions.append(f"[{loser.agent_name.name}]: {loser.style_instruction}")
        
        adverb_context_str = ""
        if adverb_instructions:
            adverb_context_str = "\nADVERBS:\n" + "\n".join(adverb_instructions)
            print(f"[Neuro-Modulation] Applied styles from: {[s.agent_name for s in strong_losers]}")
        
        self._update_mood(winner)
        
        all_scores = {s.agent_name.value: round(s.score, 2) for s in signals}
        
        # 5. Response Generation (Inject Mood Styles)
        if profile_update:
             context_str += f"\n[SYSTEM: Profile Updated: {cleaned_update}]"

        bot_gender = getattr(self.config, "gender", "Neutral")
        
        # --- EHS: Generate Dynamic Style Instructions (SEPARATE from context) ---
        mood_style_prompt = self._generate_style_from_mood(self.current_mood)
        
        # Combine Mood + Neuro-Modulation
        final_style_instructions = mood_style_prompt + adverb_context_str
        
        # ✨ Формируем affective_context_str из context["affective_context"]
        affective_warnings = context.get("affective_context", [])
        affective_context_str = ""
        
        if affective_warnings:
            affective_context_str = "⚠️ EMOTIONAL CONTEXT:\n"
            for warn in affective_warnings:
                entity = warn["entity"]
                predicate = warn["predicate"]
                feeling = warn["user_feeling"]
                intensity = warn["intensity"]
                
                if feeling == "NEGATIVE":
                    affective_context_str += f"- AVOID '{entity}' (User {predicate}, int={intensity:.1f}).\n"
                else:
                    affective_context_str += f"- OK '{entity}' (User {predicate}, int={intensity:.1f}).\n"
        
        response_text = await self.llm.generate_response(
            agent_name=winner.agent_name.value,
            user_text=message.text,
            context_str=context_str,  # Clean context (no metadata)
            rationale=winner.rationale_short,
            bot_name=self.config.name,
            bot_gender=bot_gender,
            user_mode=preferred_mode,
            style_instructions=final_style_instructions,  # Pass combined styles
            affective_context=affective_context_str,
            winner_confidence=winner.confidence  # ✨ NEW: передаём confidence для умного подавления вопросов
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
            "all_scores": all_scores,
            "mood_state": str(self.current_mood),
            "active_style": final_style_instructions,
            "affective_triggers_detected": affective_triggers_count,
            "sentiment_context_used": bool(affective_warnings),
            "modulators": [s.agent_name.value for s in strong_losers],
            "mode": "UNIFIED" if self.config.use_unified_council else "LEGACY",
            "pace_setting": self.config.sliders.pace_setting,
            "calculated_intuition_gain": intuition_gain_calculated
        }

        await log_turn_metrics(message.user_id, message.session_id, internal_stats)
        
        return CoreResponse(
            actions=[
                CoreAction(type="send_text", payload={"text": response_text})
            ],
            winning_agent=winner.agent_name,
            current_mood=self.current_mood, 
            processing_mode=ProcessingMode.SLOW_PATH,
            internal_stats=internal_stats
        )

    def _process_unified_council(self, council_report: Dict, intuition_gain: float) -> List[AgentSignal]:
        """
        ✨ UPDATED: Unified processing - all 5 agents evaluated by LLM together.
        Intuition score is multiplied by calculated intuition_gain from pace_setting.
        """
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
            
            # Get base score from LLM
            base_score = report_data.get("score", 0.0)
            
            # ✨ Apply intuition_gain multiplier ONLY to Intuition
            if key == "intuition":
                final_score = base_score * intuition_gain
                final_score = max(0.0, min(10.0, final_score))  # Clamp to [0, 10]
                print(f"[Unified Council] Intuition: base_score={base_score:.2f} × gain={intuition_gain:.2f} = {final_score:.2f}")
            else:
                final_score = base_score
            
            # Create signal
            signal = agent.process_from_report(report_data, self.config.sliders)
            signal.score = final_score  # Override with adjusted score
            signals.append(signal)
        
        return signals

    async def _process_legacy_council(self, council_report: Dict, message: IncomingMessage, context: Dict) -> List[AgentSignal]:
        """
        🔒 OLD: Legacy processing - Intuition evaluated separately, others from council_report.
        Intuition uses modifiers from agents.py (based on pace_setting).
        Kept for backward compatibility and A/B testing.
        """
        # Intuition processed independently (uses _calculate_modifier in IntuitionAgent)
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
            signal = agent.process_from_report(report_data, self.config.sliders)
            signals.append(signal)
        
        return signals

    def _update_mood(self, winner_signal):
        """
        Hormonal Physics:
        NewMood = (OldMood * Inertia) + (AgentImpact * Sensitivity)
        """
        INERTIA = 0.7
        SENSITIVITY = 0.3
        
        impact_map = {
            AgentType.AMYGDALA:  MoodVector(valence=-0.8, arousal=0.9, dominance=0.8), # Fear/Aggression
            AgentType.STRIATUM:  MoodVector(valence=0.8, arousal=0.7, dominance=0.3),  # Joy/Excitement
            AgentType.SOCIAL:    MoodVector(valence=0.5, arousal=-0.2, dominance=-0.1),# Warmth/Calm
            AgentType.PREFRONTAL:MoodVector(valence=0.0, arousal=-0.5, dominance=0.1), # Cold Logic
            AgentType.INTUITION: MoodVector(valence=0.0, arousal=0.1, dominance=0.0)   # Neutral
        }
        
        impact = impact_map.get(winner_signal.agent_name, MoodVector())
        
        force = SENSITIVITY if winner_signal.score > 4.0 else 0.05
        
        self.current_mood.valence = (self.current_mood.valence * INERTIA) + (impact.valence * force)
        self.current_mood.arousal = (self.current_mood.arousal * INERTIA) + (impact.arousal * force)
        self.current_mood.dominance = (self.current_mood.dominance * INERTIA) + (impact.dominance * force)
        
        for attr in ["valence", "arousal", "dominance"]:
            val = getattr(self.current_mood, attr)
            setattr(self.current_mood, attr, max(-1.0, min(1.0, val)))

    def _generate_style_from_mood(self, mood: MoodVector) -> str:
        """
        Translates VAD vectors into minimal technical tokens.
        NO formality hints (PROFESSIONAL/FORMAL/POLITE) to avoid conflict with ADDRESS RULE.
        """
        instructions = []
        
        # 1. Arousal (Energy/Tempo)
        if mood.arousal > 0.6:
            instructions.append("TEMPO: FAST. Sentences: Short.")
        elif mood.arousal < -0.4:
            instructions.append("TEMPO: SLOW. Sentences: Flowing.")
        
        # 2. Valence (Emotional Tone)
        if mood.valence > 0.6:
            instructions.append("TONE: WARM. Emojis OK.")
        elif mood.valence < -0.5:
            instructions.append("TONE: COLD. Minimal punctuation.")
            
        # 3. Dominance (Assertiveness)
        if mood.dominance > 0.5:
            instructions.append("STANCE: ASSERTIVE.")
        elif mood.dominance < -0.3:
            instructions.append("STANCE: SUPPORTIVE.")
            
        # 4. Special States
        if mood.arousal > 0.5 and mood.valence < -0.4:
            instructions.append("STATE: STRESSED.")
        elif mood.arousal > 0.5 and mood.valence > 0.5:
            instructions.append("STATE: ENERGETIC.")

        base = f"MOOD: V={mood.valence:.1f} A={mood.arousal:.1f} D={mood.dominance:.1f}\n"
        if not instructions:
            return base + "STYLE: NEUTRAL."
        
        return base + "STYLE: " + " | ".join(instructions)

    def _format_context_for_llm(self, context: Dict) -> str:
        """
        Compact context formatter.
        """
        lines = []
        
        profile = context.get("user_profile")
        if profile:
            lines.append("### USER IDENTITY")
            if profile.get("name"): lines.append(f"Name: {profile['name']}")
            if profile.get("gender"): lines.append(f"Gender: {profile['gender']}")
            if profile.get("preferred_mode"): lines.append(f"Address: {profile['preferred_mode']}")
            lines.append("")

        if context.get("chat_history"):
            lines.append("### DIALOGUE")
            for msg in context["chat_history"]:
                role = "U" if msg["role"] == "user" else "A"
                lines.append(f"{role}: {msg['content']}")
            lines.append("") 
            
        if context.get("episodic_memory"):
            lines.append("### MEMORY")
            for ep in context["episodic_memory"]:
                lines.append(f"* {ep.get('raw_text', '')}")
        
        if context.get("semantic_facts"):
            lines.append("### FACTS")
            for fact in context["semantic_facts"]:
                lines.append(f"* {fact.get('subject')} {fact.get('predicate')} {fact.get('object')}")
                
        return "\n".join(lines) if lines else "No context."

    async def _mock_perception(self, message: IncomingMessage) -> Dict:
        await asyncio.sleep(0.05)
        return {
            "triples": [], 
            "anchors": [{"raw_text": message.text, "emotion_score": 0.5, "tags": ["auto"]}],
            "volitional_pattern": None
        }
