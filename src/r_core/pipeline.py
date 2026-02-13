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
<<<<<<< HEAD
from .neuromodulation import NeuroModulationSystem
from .hippocampus import Hippocampus

class RCoreKernel:
    # === КОНФИГУРАЦИЯ КОНТЕКСТА ===
    COUNCIL_CONTEXT_DEPTH = 1  
    
    # === AFFECTIVE KEYWORDS ===
=======
from .neuromodulation import NeuroModulationSystem 

class RCoreKernel:
    # === КОНФИГУРАЦИЯ КОНТЕКСТА ===
    # Сколько последних сообщений передавать в council_report для анализа агентами.
    # Рациональ: Эмоциональное сглаживание происходит через Hormonal Physics (NE, DA, 5-HT, CORT),
    # поэтому council_report должен анализировать ТОЛЬКО текущий момент, без усреднения истории.
    COUNCIL_CONTEXT_DEPTH = 1  # 1 = только последнее сообщение бота (для минимального контекста)
                                # 2 = последнее сообщение бота + предыдущее юзера
                                # 3 = полная мини-цепочка диалога
    
    # === AFFECTIVE KEYWORDS ===
    # Ключевые слова для определения, нужен ли полный council (с Affective Extraction).
    # Если сообщение содержит хотя бы одно из этих слов → используем full mode.
>>>>>>> feature/neuro-modulation-v1
    AFFECTIVE_KEYWORDS = [
        "ненавижу", "боюсь", "люблю", "обожаю", "презираю", "терпеть не могу", "не выношу",
        "hate", "fear", "love", "enjoy", "despise", "adore", "can't stand"
    ]
    
<<<<<<< HEAD
    # === VOLITIONAL CONSTANTS ===
    VOLITION_PERSISTENCE_BONUS = 0.3  # Бонус для текущего фокуса
    VOLITION_DECAY_PER_DAY = 0.1      # Штраф за давность (если decay_rate не задан)
    VOLITION_FOCUS_DURATION = 3       # Сколько ходов длится фокус по умолчанию
    
=======
>>>>>>> feature/neuro-modulation-v1
    def __init__(self, config: BotConfig):
        self.config = config
        self.llm = LLMService() 
        self.memory = MemorySystem(store=None)
        
        # --- EHS: Internal State ---
        self.current_mood = MoodVector(valence=0.1, arousal=0.1, dominance=0.0) 
        
        # --- Neuro-Modulation System (Hormonal Physics) ---
        self.neuromodulation = NeuroModulationSystem()
        
<<<<<<< HEAD
        # --- Hippocampus (Lazy Consolidation) ---
        self.hippocampus = Hippocampus(
            llm_client=self.llm,
            embedding_client=self.llm
        )
        
=======
>>>>>>> feature/neuro-modulation-v1
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
<<<<<<< HEAD
        delta_minutes = self.neuromodulation.metabolize_time(message.timestamp)
        print(f"[Neuro] Time passed: {delta_minutes:.1f} min. New State: {self.neuromodulation.state}")
        
        # --- ZOMBIE MODE ---
=======
        # Calculate delta_t and apply decay BEFORE any cognitive processing
        delta_minutes = self.neuromodulation.metabolize_time(message.timestamp)
        print(f"[Neuro] Time passed: {delta_minutes:.1f} min. New State: {self.neuromodulation.state}")
        
        # --- ZOMBIE MODE (Bypass Everything) ---
>>>>>>> feature/neuro-modulation-v1
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
        
<<<<<<< HEAD
        # Normalize user mode
=======
        # === FIX: Normalize user mode (DB has "ты", code expects "informal") ===
>>>>>>> feature/neuro-modulation-v1
        raw_mode = user_profile.get("preferred_mode", "formal") if user_profile else "formal"
        if raw_mode and raw_mode.lower() in ["ты", "informal", "casual", "friendly"]:
            preferred_mode = "informal"
        else:
            preferred_mode = "formal"
<<<<<<< HEAD
=======
            
        print(f"[Pipeline] Mode Normalized: '{raw_mode}' -> '{preferred_mode}'")
>>>>>>> feature/neuro-modulation-v1

        # Save memory
        await self.memory.memorize_event(
            message, 
            extraction_result,
            precomputed_embedding=current_embedding
        )

        # === HIPPOCAMPUS TRIGGER ===
        asyncio.create_task(self._check_and_trigger_hippocampus(message.user_id))

        # 3. Parliament Debate
<<<<<<< HEAD
        council_context_str = self._format_context_for_llm(
            context, 
            limit_history=self.COUNCIL_CONTEXT_DEPTH,
            exclude_episodic=True,   
            exclude_semantic=True    
        )
        
        # ✨ Conditional Council Mode
=======
        # Council: минимальный контекст (управляется через COUNCIL_CONTEXT_DEPTH)
        council_context_str = self._format_context_for_llm(
            context, 
            limit_history=self.COUNCIL_CONTEXT_DEPTH,
            exclude_episodic=True,   # Убираем episodic memory из council (не влияет на оценку агентов)
            exclude_semantic=True    # Убираем semantic facts из council (не влияет на оценку агентов)
        )
        
        # ✨ Conditional Council Mode: Light (95%) vs Full (5%)
        # Проверяем, есть ли эмоциональные маркеры в сообщении
>>>>>>> feature/neuro-modulation-v1
        has_affective = any(keyword in message.text.lower() for keyword in self.AFFECTIVE_KEYWORDS)
        
        if has_affective:
            print("[Council] Using FULL mode (Affective Extraction enabled)")
            council_report = await self.llm.generate_council_report_full(message.text, council_context_str)
        else:
            print("[Council] Using LIGHT mode (agents only)")
            council_report = await self.llm.generate_council_report_light(message.text, council_context_str)
        
<<<<<<< HEAD
        # ✨ Affective Extraction Processing
=======
        # ✨ Affective Extraction Processing (только если был full mode)
>>>>>>> feature/neuro-modulation-v1
        affective_extracts = council_report.get("affective_extraction", [])
        affective_triggers_count = 0
        if affective_extracts:
            await self._process_affective_extraction(message, affective_extracts)
            affective_triggers_count = len(affective_extracts)
        
<<<<<<< HEAD
        # ✨ Unified Council
=======
        # ✨ Feature Flag - Unified Council vs Legacy
>>>>>>> feature/neuro-modulation-v1
        if self.config.use_unified_council:
            signals = self._process_unified_council(council_report, message, context)
            print(f"[Pipeline] Using UNIFIED COUNCIL mode (intuition_gain={self.config.intuition_gain})")
        else:
            signals = await self._process_legacy_council(council_report, message, context)
            print(f"[Pipeline] Using LEGACY mode")

        # ✨ Apply Hormonal Modulation BEFORE arbitration
        signals = self._apply_hormonal_modulation(signals)

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
<<<<<<< HEAD
=======
            print(f"[Neuro-Modulation] Applied styles from: {[s.agent_name for s in strong_losers]}")
>>>>>>> feature/neuro-modulation-v1
        
        # --- Hormonal Reactive Update ---
        # Update hormones based on who won and implicit Prediction Error
        # TODO: Implement real PE calculation. For now, infer from winner.
        implied_pe = 0.5
        if winner.agent_name == AgentType.AMYGDALA: implied_pe = 0.9 # Threat = Surprise
        elif winner.agent_name == AgentType.INTUITION: implied_pe = 0.2 # Intuition = High Confidence match
        elif winner.agent_name == AgentType.STRIATUM: implied_pe = 0.1 # Reward = Everything good
        
        self.neuromodulation.update_from_stimuli(implied_pe, winner.agent_name)
        
        # NEW: Update VAD Mood directly from Hormones (Physics consistency)
        self._update_mood_from_hormones()
        
        # Hormonal Reactive Update
        implied_pe = 0.5
        if winner.agent_name == AgentType.AMYGDALA: implied_pe = 0.9 
        elif winner.agent_name == AgentType.INTUITION: implied_pe = 0.2 
        elif winner.agent_name == AgentType.STRIATUM: implied_pe = 0.1 
        
<<<<<<< HEAD
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
=======
        # 5. Response Generation (Inject Mood Styles)
        # Response: полный контекст (без ограничений, нужен для содержательного ответа)
        response_context_str = self._format_context_for_llm(context)

        bot_gender = getattr(self.config, "gender", "Neutral")
        
        # --- STYLE GENERATION ---
        # 1. Semantic Style (Archetype) - WHAT to play (e.g. "Aggressive")
        mechanical_style_instruction = self.neuromodulation.get_style_instruction()
        
        # 2. Syntactic Style (VAD) - HOW to play (e.g. "Short sentences")
        vad_technical_instruction = self._generate_style_from_mood(self.current_mood)
        
        # Combine: Archetype + VAD Constraints + Agent Adverbs
        final_style_instructions = (
            f"{mechanical_style_instruction}\n"
            f"SYNTAX & PACING CONTROLS (VAD System):\n"
            f"{vad_technical_instruction}\n"
            f"{adverb_context_str}"
        )
        
        # ✨ Формируем affective_context_str из context["affective_context"]
        affective_warnings = context.get("affective_context", [])
        affective_context_str = ""
        
        if affective_warnings:
            affective_context_str = "⚠️ EMOTIONAL RELATIONS (User's Preferences):\\n"
            for warn in affective_warnings:
                entity = warn["entity"]
                predicate = warn["predicate"]
                feeling = warn["user_feeling"]
                intensity = warn["intensity"]
                
                if feeling == "NEGATIVE":
                    affective_context_str += f"- ⚠️ AVOID mentioning '{entity}' (User {predicate} it, intensity={intensity:.2f}). Do not use it as an example.\\n"
                else:
                    affective_context_str += f"- 💚 User {predicate} '{entity}' (intensity={intensity:.2f}). You may reference it positively.\\n"
>>>>>>> feature/neuro-modulation-v1
        
        response_text = await self.llm.generate_response(
            agent_name=winner.agent_name.value,
            user_text=message.text,
<<<<<<< HEAD
            context_str=response_context_str, 
=======
            context_str=response_context_str,  # Full context for response generation
>>>>>>> feature/neuro-modulation-v1
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
<<<<<<< HEAD
            "hormonal_state": str(self.neuromodulation.state), 
=======
            "hormonal_state": str(self.neuromodulation.state), # Log hormones
>>>>>>> feature/neuro-modulation-v1
            "hormonal_archetype": self.neuromodulation.get_archetype(),
            "active_style": final_style_instructions,
            "affective_triggers_detected": affective_triggers_count,
            "sentiment_context_used": bool(affective_warnings),
            "volition_selected": dominant_volition.get("impulse") if dominant_volition else None,
            "volition_persistence_active": self.active_focus["turns_remaining"] > 0,
            "modulators": [s.agent_name.value for s in strong_losers],
            "mode": "UNIFIED" if self.config.use_unified_council else "LEGACY",
<<<<<<< HEAD
            "council_mode": "FULL" if has_affective else "LIGHT" 
=======
            "intuition_gain": self.config.intuition_gain,
            "council_context_depth": self.COUNCIL_CONTEXT_DEPTH,  # Log for analytics
            "council_mode": "FULL" if has_affective else "LIGHT"  # NEW: Track council mode
>>>>>>> feature/neuro-modulation-v1
        }

        await log_turn_metrics(message.user_id, message.session_id, internal_stats)
        
        return CoreResponse(
            actions=[CoreAction(type="send_text", payload={"text": response_text})],
            winning_agent=winner.agent_name,
            current_mood=self.current_mood, 
<<<<<<< HEAD
            current_hormones=self.neuromodulation.state, 
=======
            current_hormones=self.neuromodulation.state, # Pass to UI
>>>>>>> feature/neuro-modulation-v1
            processing_mode=ProcessingMode.SLOW_PATH,
            internal_stats=internal_stats
        )

<<<<<<< HEAD
    # === HELPER METHODS (RESTORED) ===
    
    def _select_dominant_volition(self, patterns: List[Dict], user_id: int) -> Optional[Dict]:
=======
    def _apply_hormonal_modulation(self, signals: List[AgentSignal]) -> List[AgentSignal]:
        """
        Модулирует Scores агентов на основе гормонального архетипа.
        Применяется ТОЛЬКО для экстремальных состояний (RAGE, FEAR, BURNOUT, SHAME, TRIUMPH).
        
        Returns: Modified list of AgentSignals.
        """
        archetype = self.neuromodulation.get_archetype()
        
        # Таблица модификаторов для экстремальных состояний
        MODULATION_MAP = {
            "RAGE": {
                AgentType.AMYGDALA: 1.6,
                AgentType.PREFRONTAL: 0.6,
                AgentType.SOCIAL: 0.8
            },
            "FEAR": {
                AgentType.AMYGDALA: 1.8,
                AgentType.STRIATUM: 0.4,
                AgentType.PREFRONTAL: 0.7
            },
            "BURNOUT": {
                AgentType.PREFRONTAL: 0.3,
                AgentType.INTUITION: 1.5,
                AgentType.AMYGDALA: 1.2
            },
            "SHAME": {
                AgentType.INTUITION: 1.3
                # Все остальные: 0.8 (см. ниже)
            },
            "TRIUMPH": {
                AgentType.STRIATUM: 1.3,
                AgentType.AMYGDALA: 0.5,
                AgentType.PREFRONTAL: 1.1
            }
        }
        
        if archetype not in MODULATION_MAP:
            # Не экстремальное состояние → без модуляции
            return signals
        
        print(f"[Hormonal Override] {archetype} is modulating agent scores")
        
        modifiers = MODULATION_MAP[archetype]
        default_mod = 0.8 if archetype == "SHAME" else 1.0
        
        for signal in signals:
            mod = modifiers.get(signal.agent_name, default_mod)
            old_score = signal.score
            signal.score *= mod
            signal.score = max(0.0, min(10.0, signal.score))  # Clamp to [0, 10]
            
            if mod != 1.0:
                print(f"  - {signal.agent_name.name}: {old_score:.2f} → {signal.score:.2f} (×{mod})")
        
        return signals

    def _process_unified_council(self, council_report: Dict, message: IncomingMessage, context: Dict) -> List[AgentSignal]:
>>>>>>> feature/neuro-modulation-v1
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
                if load >= 20:
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

<<<<<<< HEAD
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
=======
    def _update_mood_from_hormones(self):
        """
        Recalculates VAD mood directly from Hormonal State (Lovheim mapping).
        Ensures internal consistency: Mood IS Hormones.
        """
        s = self.neuromodulation.state
        
        # 1. VALENCE (Pleasure/Positivity)
        # Positive: DA (Reward), 5HT (Satisfaction)
        # Negative: CORT (Stress), NE (Stress/Anger)
        raw_valence = (s.da * 0.6 + s.ht * 0.4) - (s.cort * 0.6 + s.ne * 0.4)
        
        # 2. AROUSAL (Energy/Activation)
        # High: NE (Adrenaline), DA (Drive)
        # Low: 5HT (Calm)
        raw_arousal = (s.ne * 0.7 + s.da * 0.3) - (s.ht * 0.5)
        
        # 3. DOMINANCE (Control/Power)
        # High: DA (Confidence), NE (Power)
        # Low: CORT (Fear/Submission)
        raw_dominance = (s.da * 0.5 + s.ne * 0.5) - (s.cort * 0.8)

        # Normalize to [-1.0, 1.0]
        self.current_mood.valence = max(-1.0, min(1.0, raw_valence))
        self.current_mood.arousal = max(-1.0, min(1.0, raw_arousal))
        self.current_mood.dominance = max(-1.0, min(1.0, raw_dominance))

    def _generate_style_from_mood(self, mood: MoodVector) -> str:
        """
        Translates VAD numeric vectors into TECHNICAL constraints (Syntax/Pacing).
        Uses 'pace_setting' slider to modulate verbosity.
        """
        instructions = []
        
        # Получаем настройку Pace из конфига
        pace = self.config.sliders.pace_setting
        
        print(f"[VAD Style] Pace: {pace:.2f}, Arousal: {mood.arousal:.2f}")

        # 1. AROUSAL (Tempo & Length) + PACE MODIFIER
        # RELAXED Thresholds (было 0.6, стало 0.7)
        if mood.arousal > 0.7 or pace > 0.7:
            instructions.append("🔴 [HIGH TEMPO] Max 2 sentences. Be concise.")
        elif mood.arousal < -0.7 or pace < 0.3:
            instructions.append("🔵 [LOW TEMPO] Long, flowing sentences. Elaborate thoughts.")
        else:
            # RELAXED Neutral: убрали "STRICT LIMIT"
            instructions.append("🟢 [NEUTRAL PACING] Conversational brevity. Keep it natural (2-4 sentences). Avoid huge paragraphs, but don't be robotic.")
            
        # 2. DOMINANCE (Stance)
        if mood.dominance > 0.6:
            instructions.append("🦁 [DOMINANT] Imperative mood. State absolute facts.")
        elif mood.dominance < -0.6:
            instructions.append("🐰 [SUBMISSIVE] Hesitant tone. Ask for validation.")
            
        # 3. VALENCE (Tone modifiers - auxiliary to Archetype)
        if mood.valence < -0.7:
             instructions.append("⚫ [NEGATIVE] Dry, cold punctuation.")
        
        final_instruction = " ".join(instructions)
        print(f"[VAD Style] Result: {final_instruction}")
        return final_instruction

    def _format_context_for_llm(
        self, 
        context: Dict, 
        limit_history: Optional[int] = None,
        exclude_episodic: bool = False,
        exclude_semantic: bool = False
    ) -> str:
        """
        Формирует контекст для LLM.
        
        Args:
            context: Словарь с user_profile, chat_history, episodic_memory, semantic_facts
            limit_history: Ограничение на количество последних сообщений из chat_history.
                           None = все сообщения, 1 = только последнее сообщение, 2 = последние 2, и т.д.
            exclude_episodic: Если True, не включать episodic_memory (используется для council)
            exclude_semantic: Если True, не включать semantic_facts (используется для council)
        """
        lines = []
        
        # 1. USER PROFILE (всегда включаем, это важно для персонализации)
>>>>>>> feature/neuro-modulation-v1
        profile = context.get("user_profile")
        if profile:
            lines.append("USER PROFILE (Core Identity):")
            if profile.get("name"): lines.append(f"- Name: {profile['name']}")
            if profile.get("gender"): lines.append(f"- Gender: {profile['gender']}")
            if profile.get("preferred_mode"): lines.append(f"- Address Style: {profile['preferred_mode']}")
            lines.append("")

        # 2. CHAT HISTORY (с ограничением для council)
        if context.get("chat_history"):
            chat_history = context["chat_history"]
<<<<<<< HEAD
            if limit_history is not None:
                chat_history = chat_history[-limit_history:]
            if chat_history:
=======
            
            # Ограничиваем, если задан лимит
            if limit_history is not None:
                chat_history = chat_history[-limit_history:]
            
            if chat_history:  # Проверяем, что после ограничения что-то осталось
>>>>>>> feature/neuro-modulation-v1
                lines.append("RECENT DIALOGUE:")
                for msg in chat_history:
                    role = "User" if msg["role"] == "user" else "Assistant"
                    lines.append(f"{role}: {msg['content']}")
                lines.append("") 
        
<<<<<<< HEAD
=======
        # 3. EPISODIC MEMORY (пропускаем для council, оставляем для response)
>>>>>>> feature/neuro-modulation-v1
        if not exclude_episodic and context.get("episodic_memory"):
            lines.append("PAST EPISODES (Long-term memory):")
            for ep in context["episodic_memory"]:
                lines.append(f"- {ep.get('raw_text', '')}")
            lines.append("")
        
<<<<<<< HEAD
=======
        # 4. SEMANTIC FACTS (пропускаем для council, оставляем для response)
>>>>>>> feature/neuro-modulation-v1
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
