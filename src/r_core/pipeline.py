import asyncio
import random
from typing import Dict, List, Optional
from datetime import datetime
import numpy as np
from numpy import dot
from numpy.linalg import norm
from sqlalchemy import text, select, desc


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
        
        # Counter for Volitional Detection throttling
        self.volition_check_counter = 0

        # ✨ NEW: Topic Tracker (independent from volitional patterns)
        self.current_topic_state = {
            "topic_embedding": None,         # Усредненный вектор (Centroid) текущей темы
            "topic_text": "",                # Text summary of topic
            "tec": 1.0,                      # Topic Engagement Capacity [0.0, 1.0]
            "turns_on_topic": 0,             # Turns spent on this topic
            "messages_in_topic": 0,          # Счетчик сообщений для расчета центроида
            "intent_category": "Casual",     # Nature taxonomy: Phatic/Casual/Narrative/Deep/Task
            "last_prediction_error": 0.5     # PE from last turn (for decay calculation)
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
                # We prioritize the LATEST active profile in DB, ignoring config.name if it's default "R-Bot"
                # If config.name is NOT R-Bot, we try to fetch that specific one.
                
                agent_profile = None
                
                if self.config.name != "R-Bot":
                     print(f"[Identity] Searching for specific profile: '{self.config.name}'")
                     stmt = select(AgentProfileModel).where(AgentProfileModel.name == self.config.name)
                     result = await session.execute(stmt)
                     agent_profile = result.scalar_one_or_none()
                
                # FALLBACK: If specific name not found OR name is default "R-Bot", load the LATEST profile
                if not agent_profile:
                     print(f"[Identity] Config name '{self.config.name}' not found or default. Fetching LATEST profile.")
                     # Sort by updated_at desc to get the most recently active/edited bot
                     stmt = select(AgentProfileModel).order_by(desc(AgentProfileModel.updated_at)).limit(1)
                     result = await session.execute(stmt)
                     agent_profile = result.scalar_one_or_none()

                if agent_profile:
                    print(f"[Identity] Loaded Profile: {agent_profile.name} (Gender: {agent_profile.gender})")
                    # Update Config in Runtime
                    self.config.name = agent_profile.name
                    self.config.gender = agent_profile.gender or "Neutral"
                    if agent_profile.description:
                        bot_description = agent_profile.description
                        # print(f"[Identity] Loaded description preview: {bot_description[:50]}...")
                    
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

            # [Topic Tracker Update moved to after _perception_stage]


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
        
        # === ✨ USER PROFILE FIX: Respect preferred_mode from DB ===
        # If DB says "informal"/"ты", use it. Otherwise default to "formal".
        raw_mode = user_profile.get("preferred_mode", "formal") if user_profile else "formal"
        if raw_mode and str(raw_mode).lower() in ["ты", "informal", "casual", "friendly", "true"]:
            preferred_mode = "informal"
        else:
            preferred_mode = "formal"


        # === 3. PERCEPTION & VOLITIONAL DETECTION (Revised) ===
        # Now that we have context (history), we can run the Volitional Detector
        extraction_result = await self._perception_stage(message, context.get("chat_history", []))

        # ========== ✨ TOPIC TRACKER UPDATE (Centroid Architecture) ==========
        # Этот блок обновляет TEC на основе предсказания ошибки и плотности ответа
        # Использует архитектуру усредненного вектора темы (Topic Centroid)
        
        # Получаем intent_category из volitional detection
        intent_cat = "Casual"
        if extraction_result and extraction_result.get("volitional_pattern"):
            intent_cat = extraction_result["volitional_pattern"].get("intent_category", "Casual")

        # === Защита от коротких фраз (Phatic Bypass) ===
        is_short_or_phatic = False
        word_count = 0
        if message.text:
            word_count = len(message.text.split())
            # Список фатических фраз (phatic messages) - короткие ответы без смысловой нагрузки
            phatic_patterns = ["ага", "ясно", "ок", "да", "нет", "хм", "мм", "угу", "ну", "понятно", "окей", "ладно", "чё", "да?", "и что?", "и что теперь?"]
            is_phatic = any(pattern in message.text.lower() for pattern in phatic_patterns)
            if word_count < 4 or is_phatic:
                is_short_or_phatic = True

        # === Проверка смены темы ===
        topic_changed = False
        
        if self.current_topic_state["topic_embedding"] is not None and current_embedding is not None:
            if not is_short_or_phatic:
                # Вычисляем косинусное сходство с центроидом
                topic_emb = self.current_topic_state["topic_embedding"]
                similarity = dot(current_embedding, topic_emb) / (norm(current_embedding) * norm(topic_emb))

                # Новый порог 0.40 (ранее был 0.5)
                if similarity < 0.40:
                    topic_changed = True
                    print(f"[TopicTracker] 🔄 Topic Change Detected (similarity={similarity:.2f}). Resetting TEC.")
            else:
                # Пропускаем вычисление similarity для коротких фраз
                print(f"[TopicTracker] ⏭️ Skipping similarity check (short/phatic message: {word_count} words)")
        else:
            # Первый ход или нет embedding - инициализируем тему
            topic_changed = True

        # === Сброс или обновление состояния темы ===
        if topic_changed:
            self.current_topic_state = {
                "topic_embedding": current_embedding,
                "topic_text": message.text[:100] if message.text else "",
                "tec": 1.0,
                "turns_on_topic": 1,
                "messages_in_topic": 1,
                "intent_category": intent_cat,
                "last_prediction_error": prediction_error
            }
            print(f"[TopicTracker] 🔵 New Topic Started: TEC=1.0, intent={intent_cat}")
        else:
            # === Обновление центроида (Centroid Update) ===
            count = self.current_topic_state["messages_in_topic"]
            old_centroid = self.current_topic_state["topic_embedding"]
            
            old_arr = np.array(old_centroid)
            curr_arr = np.array(current_embedding)
            
            # Формула: new_centroid = (old_centroid * count + current_embedding) / (count + 1)
            new_centroid = ((old_arr * count) + curr_arr) / (count + 1)
            # Нормализация
            new_centroid = new_centroid / np.linalg.norm(new_centroid)
            
            self.current_topic_state["topic_embedding"] = new_centroid.tolist()
            self.current_topic_state["messages_in_topic"] += 1
            self.current_topic_state["turns_on_topic"] += 1

            # === Применяем decay формулу ===
            BASE_DECAY_MAP = {
                "Phatic": 1.0,      # Social rituals: instant burn
                "Casual": 0.4,      # Small talk: fast decay
                "Narrative": 0.15,  # Stories: moderate
                "Deep": 0.05,       # Deep topics: slow decay
                "Task": 0.0         # Task-oriented: no decay until resolved
            }

            intent = self.current_topic_state["intent_category"]
            base_decay = BASE_DECAY_MAP.get(intent, 0.3)

            # Situational multiplier
            response_density = min(len(message.text.split()) / 50.0, 1.0) if message.text else 0.0
            situational_multiplier = (0.5 + (1 - prediction_error) * 0.5) * (2.0 - response_density)

            effective_decay = base_decay * situational_multiplier

            old_tec = self.current_topic_state["tec"]
            self.current_topic_state["tec"] = max(0.0, old_tec - effective_decay)
            self.current_topic_state["last_prediction_error"] = prediction_error
            self.current_topic_state["intent_category"] = intent

            print(f"[TopicTracker] TEC: {old_tec:.2f} → {self.current_topic_state['tec']:.2f} "
                  f"(decay={effective_decay:.2f}, PE={prediction_error:.2f}, turns={self.current_topic_state['turns_on_topic']})")

        # Log Topic Tracker State
        print(f"[TopicTracker] State: topic='{self.current_topic_state['topic_text'][:30]}...', "
              f"intent={self.current_topic_state['intent_category']}, "
              f"TEC={self.current_topic_state['tec']:.2f}, "
              f"turns={self.current_topic_state['turns_on_topic']}, "
              f"messages={self.current_topic_state['messages_in_topic']}")
        # ========== END Topic Tracker Update ==========

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
        if affective_extracts and isinstance(affective_extracts, list):
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
        
        # === Task 2.1: Extract current TEC and determine LC Mode ===
        # ✨ FIX: Use Topic Tracker TEC instead of volitional pattern TEC
        current_tec = self.current_topic_state["tec"]
        lc_mode = "phasic"
        lc_mode = self.neuromodulation.get_lc_mode(current_tec)
        print(f"[LC-NE] TEC={current_tec:.2f}, Mode={lc_mode}")
        
        # === Stage 3: The Bifurcation Engine ===
        # Trigger when LC mode is "tonic" (low engagement, exploration needed)
        bifurcation_candidates = []
        predicted_bifurcation_topic = None
        semantic_candidates = []
        emotional_candidates = []
        zeigarnik_candidates = []
        
        if lc_mode == "tonic":
            print("[Bifurcation Engine] Tonic LC detected. Generating topic switch hypotheses...")
            
            try:
                # 1. Fetch all 3 vectors concurrently (check embedding exists)
                if current_embedding:
                    semantic_task = self.hippocampus.get_semantic_neighbors(message.user_id, current_embedding, limit=3)
                else:
                    async def empty_semantic():
                        return []
                    semantic_task = empty_semantic()
                    
                zeigarnik_task = self.hippocampus.get_zeigarnik_returns(message.user_id, limit=3)
                emotional_task = self.memory.get_emotional_anchors(message.user_id, limit=3)
                
                semantic_candidates, zeigarnik_candidates, emotional_candidates = await asyncio.gather(
                    semantic_task, zeigarnik_task, emotional_task
                )
                
                # 2. Score and combine candidates
                # Semantic: weight 0.5 (based on similarity: distance 0.35-0.65 is ideal)
                for item in semantic_candidates:
                    score = 0.5 * (1.0 - abs(item.get("distance", 0.5) - 0.5) * 2)  # Higher score for distance closer to 0.5
                    bifurcation_candidates.append({
                        "topic": item.get("topic", "Unknown"),
                        "content": item.get("content", ""),
                        "score": score,
                        "vector": "semantic_neighbor",
                        "distance": item.get("distance")
                    })
                
                # Emotional: weight 0.3 (based on intensity)
                for item in emotional_candidates:
                    score = 0.3 * item.get("intensity", 0.5)
                    bifurcation_candidates.append({
                        "topic": item.get("topic", "Unknown"),
                        "content": item.get("content", ""),
                        "score": score,
                        "vector": "emotional_anchor",
                        "intensity": item.get("intensity")
                    })
                
                # Zeigarnik: weight 0.2 (based on recency - more recent = higher score)
                for i, item in enumerate(zeigarnik_candidates):
                    recency_score = 1.0 / (i + 1)  # More recent = higher score
                    score = 0.2 * recency_score * item.get("prediction_error", 0.5)
                    bifurcation_candidates.append({
                        "topic": item.get("content", "Unknown")[:50],  # Use content as topic
                        "content": item.get("content", ""),
                        "score": score,
                        "vector": "zeigarnik_return",
                        "prediction_error": item.get("prediction_error")
                    })
                
                # 3. Sort by score and select top candidate
                if bifurcation_candidates:
                    bifurcation_candidates.sort(key=lambda x: x.get("score", 0), reverse=True)
                    predicted_bifurcation_topic = bifurcation_candidates[0].get("topic", "General")
                    print(f"[Bifurcation Engine] Selected topic: {predicted_bifurcation_topic} (score={bifurcation_candidates[0].get('score', 0):.3f})")
                    
            except Exception as e:
                print(f"[Bifurcation Engine] ❌ Error: {e}")
        
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

        # === Task 2.4: Modify Prefrontal Agent Score (Exploration Bias) ===
        # If lc_mode == "tonic", increase Prefrontal score by 10% (capped at 10.0)
        if lc_mode == "tonic":
            for signal in signals:
                if signal.agent_name == AgentType.PREFRONTAL:
                    signal.score = min(10.0, signal.score * 1.1)
                    signal.rationale_short += " [Tonic Exploration Boost]"
                    print(f"[LC-NE] Tonic mode: Prefrontal score boosted to {signal.score:.2f}")
                    break


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
        
        self.neuromodulation.update_from_stimuli(implied_pe, winner.agent_name, current_tec=current_tec)
        
        
        # 5. Response Generation 
        response_context_str = self._format_context_for_llm(context)
        
        # === ✨ CRITICAL FIX: Use config name (Loaded from DB) ===
        # If we loaded "Lyutik" from DB, self.config.name is "Lyutik".
        # If we failed and it's default, it's "R-Bot".
        
        bot_gender = getattr(self.config, "gender", "Neutral")
        
        mechanical_style_instruction = self.neuromodulation.get_style_instruction()
        
        # === Stage 3: Inject Bifurcation Directive into LLM Prompt ===
        bifurcation_instruction = ""
        if predicted_bifurcation_topic:
            bifurcation_instruction = (
                f"\\n\\nPROACTIVE MIRRORING (Topic Switch Recommended):\\n"
                f"- The user's engagement with the current topic is depleted (TEC={current_tec:.2f}).\\n"
                f"- Gently pivot the conversation towards: {predicted_bifurcation_topic}\\n"
                f"- Use natural transition, acknowledge the previous topic briefly, then bridge to the new one.\\n"
            )
            print(f"[Bifurcation Engine] Injecting directive: pivot to '{predicted_bifurcation_topic}'")
            
        final_style_instructions = mechanical_style_instruction + "\\n" + adverb_context_str + volitional_instruction + bifurcation_instruction
        
        # Affective Context for LLM
        affective_warnings = context.get("affective_context", [])
        affective_context_str = self._format_affective_context(affective_warnings)
        
        # ✨ Generate Response + Prediction
        # IMPORTANT: We pass self.config.name, which was updated from DB above.
        response_text, predicted_reaction = await self.llm.generate_response(
            agent_name=winner.agent_name.value,
            user_text=message.text,
            context_str=response_context_str, 
            rationale=winner.rationale_short,
            bot_name=self.config.name,        # <--- Uses DB-loaded name (e.g. "Lyutik")
            bot_gender=bot_gender,            # <--- Uses DB-loaded gender
            bot_description=bot_description,  # <--- Uses DB-loaded description ("трубадур")
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
            "user_emotion_score": real_emotion_score,
            # === Task 3: LC-NE Metrics Logging ===
            "lc_mode": lc_mode,
            "topic_engagement": current_tec,
            # === Stage 3: Bifurcation Metrics ===
            "bifurcation_triggered": lc_mode == "tonic",
            "bifurcation_target": predicted_bifurcation_topic,
            "bifurcation_candidates_count": len(bifurcation_candidates),
            "bifurcation_vectors": {
                "semantic": len(semantic_candidates) if lc_mode == "tonic" else 0,
                "emotional": len(emotional_candidates) if lc_mode == "tonic" else 0,
                "zeigarnik": len(zeigarnik_candidates) if lc_mode == "tonic" else 0,
            } if lc_mode == "tonic" else None,
        }

        # Debug: Print bifurcation summary
        if lc_mode == "tonic" and predicted_bifurcation_topic:
            print(f"[Bifurcation Engine] Summary: {len(bifurcation_candidates)} candidates, target='{predicted_bifurcation_topic}'")


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
        
        # Increase counter
        self.volition_check_counter += 1
        
        # Only run detection if history is sufficient AND Throttled (1 in 5)
        if len(chat_history) >= 2 and (self.volition_check_counter % 5 == 0):
             print(f"[Pipeline] Scanning for volitional patterns (Turn {self.volition_check_counter})...")
             volitional_pattern = await self.llm.detect_volitional_pattern(message.text, history_str)
             if volitional_pattern:
                 print(f"[Pipeline] Pattern DETECTED: {volitional_pattern['trigger']} -> {volitional_pattern['impulse']}")
        else:
             print(f"[Pipeline] Volition scan skipped (Turn {self.volition_check_counter})")
        
        return {
            "triples": [], 
            "anchors": [{"raw_text": message.text, "emotion_score": 0.5, "tags": ["auto"]}], 
            "volitional_pattern": volitional_pattern
        }
