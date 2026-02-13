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
    AgentSignal,
    HormonalState 
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
    AFFECTIVE_KEYWORDS = [
        "ненавижу", "боюсь", "люблю", "обожаю", "презираю", "терпеть не могу", "не выношу",
        "hate", "fear", "love", "enjoy", "despise", "adore", "can't stand"
    ]
    
    def __init__(self, config: BotConfig):
        self.config = config
        self.llm = LLMService() 
        self.memory = MemorySystem(store=None)
        
        # --- EHS: Internal State ---
        self.current_mood = MoodVector(valence=0.1, arousal=0.1, dominance=0.0) 
        
        # --- Neuro-Modulation System (Hormonal Physics) ---
        self.neuromodulation = NeuroModulationSystem()
        
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
        
        # --- 0. Temporal Metabolism (Sense of Time) ---
        # Calculate delta_t and apply decay BEFORE any cognitive processing
        delta_minutes = self.neuromodulation.metabolize_time(message.timestamp)
        print(f"[Neuro] Time passed: {delta_minutes:.1f} min. New State: {self.neuromodulation.state}")
        
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
        
        # === FIX: Normalize user mode (DB has "ты", code expects "informal") ===
        raw_mode = user_profile.get("preferred_mode", "formal") if user_profile else "formal"
        if raw_mode and raw_mode.lower() in ["ты", "informal", "casual", "friendly"]:
            preferred_mode = "informal"
        else:
            preferred_mode = "formal"
            
        print(f"[Pipeline] Mode Normalized: '{raw_mode}' -> '{preferred_mode}'")

        # Save memory
        extraction_result = await perception_task
        await self.memory.memorize_event(
            message, 
            extraction_result,
            precomputed_embedding=current_embedding
        )

        # 3. Parliament Debate
        # Council: минимальный контекст (управляется через COUNCIL_CONTEXT_DEPTH)
        council_context_str = self._format_context_for_llm(
            context, 
            limit_history=self.COUNCIL_CONTEXT_DEPTH,
            exclude_episodic=True,   # Убираем episodic memory из council (не влияет на оценку агентов)
            exclude_semantic=True    # Убираем semantic facts из council (не влияет на оценку агентов)
        )
        
        # ✨ Conditional Council Mode: Light (95%) vs Full (5%)
        # Проверяем, есть ли эмоциональные маркеры в сообщении
        has_affective = any(keyword in message.text.lower() for keyword in self.AFFECTIVE_KEYWORDS)
        
        if has_affective:
            print("[Council] Using FULL mode (Affective Extraction enabled)")
            council_report = await self.llm.generate_council_report_full(message.text, council_context_str)
        else:
            print("[Council] Using LIGHT mode (agents only)")
            council_report = await self.llm.generate_council_report_light(message.text, council_context_str)
        
        # ✨ Affective Extraction Processing (только если был full mode)
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
        if self.config.use_unified_council:
            # NEW LOGIC: All agents processed through council_report (including Intuition)
            signals = self._process_unified_council(council_report, message, context)
            print(f"[Pipeline] Using UNIFIED COUNCIL mode (intuition_gain={self.config.intuition_gain})")
        else:
            # OLD LOGIC: Intuition processed separately
            signals = await self._process_legacy_council(council_report, message, context)
            print(f"[Pipeline] Using LEGACY mode (Intuition evaluated separately)")

        # ✨ Apply Hormonal Modulation BEFORE arbitration
        signals = self._apply_hormonal_modulation(signals)

        # 4. Arbitration & Mood Update
        signals.sort(key=lambda s: s.score, reverse=True)
        winner = signals[0]
        
        # --- Neuro-Modulation (Adverbs) ---
        # Strong Losers: Score > 5.0 AND not the winner
        strong_losers = [s for s in signals if s.score > 5.0 and s.agent_name != winner.agent_name]
        
        adverb_instructions = []
        for loser in strong_losers:
            if loser.style_instruction:
                adverb_instructions.append(f"- {loser.agent_name.name}: {loser.style_instruction}")
        
        adverb_context_str = ""
        if adverb_instructions:
            adverb_context_str = "\\nSECONDARY STYLE MODIFIERS (Neuro-Modulation):\\n" + "\\n".join(adverb_instructions)
            print(f"[Neuro-Modulation] Applied styles from: {[s.agent_name for s in strong_losers]}")
        
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
        
        all_scores = {s.agent_name.value: round(s.score, 2) for s in signals}
        
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
        
        response_text = await self.llm.generate_response(
            agent_name=winner.agent_name.value,
            user_text=message.text,
            context_str=response_context_str,  # Full context for response generation
            rationale=winner.rationale_short,
            bot_name=self.config.name,
            bot_gender=bot_gender,
            user_mode=preferred_mode,
            style_instructions=final_style_instructions,  # Pass combined styles
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
            "all_scores": all_scores,
            "mood_state": str(self.current_mood),
            "hormonal_state": str(self.neuromodulation.state), # Log hormones
            "hormonal_archetype": self.neuromodulation.get_archetype(),
            "active_style": final_style_instructions,
            "affective_triggers_detected": affective_triggers_count,
            "sentiment_context_used": bool(affective_warnings),
            "modulators": [s.agent_name.value for s in strong_losers],
            "mode": "UNIFIED" if self.config.use_unified_council else "LEGACY",
            "intuition_gain": self.config.intuition_gain,
            "council_context_depth": self.COUNCIL_CONTEXT_DEPTH,  # Log for analytics
            "council_mode": "FULL" if has_affective else "LIGHT"  # NEW: Track council mode
        }

        await log_turn_metrics(message.user_id, message.session_id, internal_stats)
        
        return CoreResponse(
            actions=[
                CoreAction(type="send_text", payload={"text": response_text})
            ],
            winning_agent=winner.agent_name,
            current_mood=self.current_mood, 
            current_hormones=self.neuromodulation.state, # Pass to UI
            processing_mode=ProcessingMode.SLOW_PATH,
            internal_stats=internal_stats
        )

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
        """
        ✨ NEW: Unified processing - all 5 agents evaluated by LLM together.
        Intuition score is multiplied by intuition_gain.
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
                final_score = base_score * self.config.intuition_gain
                final_score = max(0.0, min(10.0, final_score))  # Clamp to [0, 10]
                print(f"[Unified Council] Intuition: base_score={base_score:.2f} × gain={self.config.intuition_gain} = {final_score:.2f}")
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
        Kept for backward compatibility and A/B testing.
        """
        # Intuition processed independently
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
        """
        instructions = []
        
        # 1. AROUSAL (Tempo & Length)
        if mood.arousal > 0.6:
            instructions.append("🔴 [HIGH TEMPO] Short sentences (max 5-7 words). No complex grammar. Use '!' or caps if needed. Be abrupt.")
        elif mood.arousal < -0.6:
            instructions.append("🔵 [LOW TEMPO] Long, flowing sentences (20+ words). Use '...' and pauses. Passive voice allowed. Be slow.")
            
        # 2. DOMINANCE (Stance)
        if mood.dominance > 0.6:
            instructions.append("🦁 [DOMINANT] Imperative mood. No 'please', 'maybe', or 'I think'. Give orders or state absolute facts.")
        elif mood.dominance < -0.6:
            instructions.append("🐰 [SUBMISSIVE] Hesitant tone. Use 'sorry', 'if I may', 'perhaps'. Ask for validation.")
            
        # 3. VALENCE (Tone modifiers - auxiliary to Archetype)
        if mood.valence < -0.7:
             instructions.append("⚫ [NEGATIVE] Dry, cold punctuation. Use periods instead of commas. No pleasantries.")
        
        if not instructions:
            return "🟢 [NEUTRAL PACING] Natural sentence length and structure."
            
        return " ".join(instructions)

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
            
            # Ограничиваем, если задан лимит
            if limit_history is not None:
                chat_history = chat_history[-limit_history:]
            
            if chat_history:  # Проверяем, что после ограничения что-то осталось
                lines.append("RECENT DIALOGUE:")
                for msg in chat_history:
                    role = "User" if msg["role"] == "user" else "Assistant"
                    lines.append(f"{role}: {msg['content']}")
                lines.append("") 
        
        # 3. EPISODIC MEMORY (пропускаем для council, оставляем для response)
        if not exclude_episodic and context.get("episodic_memory"):
            lines.append("PAST EPISODES (Long-term memory):")
            for ep in context["episodic_memory"]:
                lines.append(f"- {ep.get('raw_text', '')}")
            lines.append("")
        
        # 4. SEMANTIC FACTS (пропускаем для council, оставляем для response)
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
