import json
import time
import asyncio
import random
from typing import List, Optional, Any, Dict, Tuple
from openai import AsyncOpenAI, RateLimitError, APIError
from src.r_core.config import settings
from src.r_core.schemas import AgentSignal, AgentType
from src.r_core.infrastructure.db import log_llm_raw_response


class LLMService:
    def __init__(self):
        self.client = AsyncOpenAI(
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_BASE_URL
        )
        self.model_name = settings.LLM_MODEL_NAME
        
        # Кэш последнего валидного Council Report
        self.last_valid_council_report = None


    async def get_embedding(self, text: str) -> List[float]:
        """
        Robust embedding retrieval with retries.
        """
        max_retries = 3
        base_delay = 1.0
        
        for attempt in range(max_retries):
            try:
                response = await self.client.embeddings.create(
                    input=text,
                    model=settings.EMBEDDING_MODEL
                )
                return response.data[0].embedding
            except RateLimitError:
                if attempt < max_retries - 1:
                    wait_time = (base_delay * (2 ** attempt)) + random.uniform(0.1, 0.5)
                    print(f"[LLMService] Embedding RateLimit. Retrying in {wait_time:.1f}s...")
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    print(f"[LLMService] Embedding RateLimit Exceeded after {max_retries} attempts.")
                    raise
            except Exception as e:
                if attempt < max_retries - 1:
                    wait_time = base_delay + random.uniform(0.5, 1.5)
                    print(f"[LLMService] Embedding Error: {e}. Retrying in {wait_time:.1f}s...")
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    print(f"[LLMService] Embedding Failed Final: {e}")
                    raise e
            
        # Fallback return - should never reach here if retry logic works
        raise RuntimeError("Embedding failed after all retries")
            
    async def embed(self, text: str) -> List[float]:
        """Alias for get_embedding to satisfy Hippocampus protocol"""
        return await self.get_embedding(text)


    async def complete(self, prompt: str) -> str:
        """Raw completion wrapper for internal tasks (Hippocampus, etc)"""
        # Используем _safe_chat_completion, так как он уже содержит ретраи
        try:
             # _safe_chat_completion возвращает строку или dict. 
             # Для complete нам нужна строка.
             response = await self._safe_chat_completion(
                messages=[{"role": "user", "content": prompt}],
                response_format=None,
                json_mode=False
            )
             # Если вернулся dict (ошибка), приводим к строке
             return str(response) if not isinstance(response, str) else response
        except Exception as e:
             return f"Error: {str(e)}"


    async def generate_signal(self, system_prompt: str, user_text: str, agent_name: AgentType) -> AgentSignal:
        """
        Generate a single agent signal for legacy mode.
        Used by agents that need direct LLM scoring.
        """
        prompt = (
            f"{system_prompt}\n\n"
            f"User message: '{user_text}'\n\n"
            "OUTPUT FORMAT (JSON Only):\n"
            "{ 'score': float(0-10), 'rationale': 'string(max 10 words)', 'confidence': float(0-1) }"
        )

        try:
            response_data = await self._safe_chat_completion(
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                json_mode=True
            )
            
            if isinstance(response_data, str):
                try:
                    data = json.loads(response_data)
                except:
                    return self._get_fallback_signal(agent_name)
            else:
                data = response_data

            return AgentSignal(
                agent_name=agent_name,
                score=float(data.get("score", 5.0)),
                rationale_short=data.get("rationale", "Default"),
                confidence=float(data.get("confidence", 0.5)),
                latency_ms=0,
                style_instruction=""
            )
            
        except Exception as e:
            print(f"[LLM] generate_signal failed: {e}")
            return self._get_fallback_signal(agent_name)


    def _get_fallback_signal(self, agent_name: AgentType) -> AgentSignal:
        """Return a neutral fallback signal"""
        return AgentSignal(
            agent_name=agent_name,
            score=5.0,
            rationale_short="Fallback: neutral",
            confidence=0.5,
            latency_ms=0,
            style_instruction=""
        )


    def _build_council_prompt_base(self, context_summary: str) -> str:
        """
        Базовый промпт для council_report (только агенты).
        Используется в light и full режимах.
        """
        return (
            "You are the Cognitive Core of R-Bot. Analyze the user's input through 5 functional lenses.\\n"
            f"Context: {context_summary}\\n\\n"
            
            "### 1. AMYGDALA (Safety & Threat)\\n"
            "- Focus: Aggression, boundary violation, high risk, distress, conflict.\\n"
            "- Score 8-10: Hostile/Unsafe/Urgent. Score 0-2: Safe/Neutral.\\n\\n"
            
            "### 2. PREFRONTAL CORTEX (Logic & Planning)\\n"
            "- Focus: Factual questions, logical tasks, structure, planning, analysis.\\n"
            "- Score 8-10: User wants a solution/plan. Score 0-2: Pure chat/emotion.\\n\\n"
            
            "### 3. SOCIAL CORTEX (Empathy & Norms)\\n"
            "- Focus: Greetings, gratitude, emotional support, small talk, politeness.\\n"
            "- Score 8-10: Social/Emotional interaction. Score 0-2: Dry/Transactional.\\n\\n"
            
            "### 4. STRIATUM (Reward & Desire)\\n"
            "- Focus: Curiosity, playfulness, game mechanics, opportunities for fun/goals.\\n"
            "- Score 8-10: Exciting/Gamified. Score 0-2: Boring/Routine.\\n\\n"
            
            "### 5. INTUITION (System-1 Fast Thinking)\\n"
            "- Focus: Immediate, automatic, effortless responses. Pattern matching without deep reasoning.\\n"
            "- Score 8-10: Response is immediate and obvious (greetings, simple Q&A). No analysis needed.\\n"
            "- Score 4-7: Message is familiar but needs slight adaptation.\\n"
            "- Score 0-3: Unfamiliar territory. Requires System-2 (Prefrontal) thinking.\\n\\n"
        )


    def _build_affective_block(self) -> str:
        """
        Блок извлечения эмоциональных отношений пользователя.
        Добавляется только в full режиме.
        """
        return (
            "### 6. AFFECTIVE EXTRACTION (Emotional Relations)\\n"
            "Detect if the user expresses strong emotional attitudes toward objects, people, concepts, or technologies.\\n"
            "- Keywords: loves, hates, fears, enjoys, despises, adores, can't stand.\\n"
            "- Output format: [{'subject': 'User', 'predicate': 'LOVES|HATES|FEARS|ENJOYS|DESPISES', 'object': 'entity', 'intensity': float(0-1)}]\\n"
            "- Examples:\\n"
            "  * 'Ненавижу Java' -> {'subject': 'User', 'predicate': 'HATES', 'object': 'Java', 'intensity': 0.9}\\n"
            "  * 'Боюсь пауков' -> {'subject': 'User', 'predicate': 'FEARS', 'object': 'пауки', 'intensity': 0.7}\\n"
            "- Return empty array [] if no affective content detected.\\n\\n"
        )


    async def generate_council_report_light(self, user_text: str, context_summary: str = "") -> Dict[str, Dict]:
        """
        LIGHT MODE: Только агенты (AMYGDALA, PREFRONTAL, SOCIAL, STRIATUM, INTUITION).
        Используется для 95% запросов (без эмоциональных маркеров).
        ~520 токенов input.
        """
        system_prompt = self._build_council_prompt_base(context_summary)
        system_prompt += (
            "### OUTPUT FORMAT\\n"
            "Return JSON ONLY. Keys: 'amygdala', 'prefrontal', 'social', 'striatum', 'intuition'.\\n"
            "Value schema: { 'score': float(0-10), 'rationale': 'string(max 10 words)', 'confidence': float(0-1) }"
        )
        
        return await self._execute_council_report(user_text, system_prompt, mode="light")


    async def generate_council_report_full(self, user_text: str, context_summary: str = "") -> Dict[str, Dict]:
        """
        FULL MODE: Агенты + Affective Extraction.
        Используется для 5% запросов (с эмоциональными маркерами).
        ~740 токенов input.
        """
        system_prompt = self._build_council_prompt_base(context_summary)
        system_prompt += self._build_affective_block()
        system_prompt += (
            "### OUTPUT FORMAT\\n"
            "Return JSON ONLY. Keys: 'amygdala', 'prefrontal', 'social', 'striatum', 'intuition', 'affective_extraction'.\\n"
            "Value schema for agents: { 'score': float(0-10), 'rationale': 'string(max 10 words)', 'confidence': float(0-1) }\\n"
            "Value schema for 'affective_extraction': [ {'subject': 'User', 'predicate': 'LOVES|HATES|FEARS|ENJOYS|DESPISES', 'object': 'str', 'intensity': float(0-1)} ] OR [] if empty."
        )
        
        return await self._execute_council_report(user_text, system_prompt, mode="full")


    async def _execute_council_report(self, user_text: str, system_prompt: str, mode: str) -> Dict:
        """
        Общая логика выполнения council_report с fallback механизмом.
        """
        prompt = user_text  # Для логирования
        raw_response = None
        
        try:
            raw_response = await self._safe_chat_completion(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_text}
                ],
                response_format={"type": "json_object"},
                json_mode=True
            )
            
            # Парсим JSON
            if isinstance(raw_response, str):
                council_report = json.loads(raw_response)
            else:
                council_report = raw_response
            
            # Проверяем обязательные ключи
            required_keys = ["intuition", "amygdala", "prefrontal", "social", "striatum"]
            missing_keys = [k for k in required_keys if k not in council_report]
            
            if missing_keys:
                # Логируем ошибку
                await log_llm_raw_response(
                    prompt_type=f"council_report_{mode}",
                    raw_request=prompt[:2000],
                    raw_response=str(raw_response)[:5000],
                    parse_status="missing_keys",
                    error_message=f"Missing: {missing_keys}"
                )
                
                # Fallback
                return self._get_fallback_council_report()
            
            # Успех! Сохраняем в кэш
            self.last_valid_council_report = council_report
            
            return council_report
            
        except json.JSONDecodeError as e:
            await log_llm_raw_response(
                prompt_type=f"council_report_{mode}",
                raw_request=prompt[:2000],
                raw_response=str(raw_response)[:5000] if raw_response else "N/A",
                parse_status="json_error",
                error_message=str(e)
            )
            return self._get_fallback_council_report()
            
        except Exception as e:
            await log_llm_raw_response(
                prompt_type=f"council_report_{mode}",
                raw_request=prompt[:2000],
                raw_response="N/A",
                parse_status="api_error",
                error_message=str(e)
            )
            return self._get_fallback_council_report()


    def _get_fallback_council_report(self) -> Dict:
        """
        Возвращает последний валидный Council Report или дефолтный.
        """
        if self.last_valid_council_report:
            print("[LLM] Using cached council report (LLM failed)")
            return self.last_valid_council_report
        
        # Нейтральное состояние по умолчанию
        print("[LLM] No cached report, using neutral default")
        return {
            "intuition": {"score": 5.0, "rationale": "Fallback: neutral state", "confidence": 0.5},
            "amygdala": {"score": 3.0, "rationale": "Fallback: low threat", "confidence": 0.5},
            "prefrontal": {"score": 6.0, "rationale": "Fallback: default logic", "confidence": 0.5},
            "social": {"score": 5.0, "rationale": "Fallback: neutral empathy", "confidence": 0.5},
            "striatum": {"score": 4.0, "rationale": "Fallback: moderate reward", "confidence": 0.5}
        }


    async def generate_response(
        self, 
        agent_name: str, 
        user_text: str, 
        context_str: str, 
        rationale: str, 
        bot_name: str = "R-Bot", 
        bot_gender: str = "Neutral",
        bot_description: str = "", # ✨ NEW: Full persona description
        user_mode: str = "formal",
        style_instructions: str = "", 
        affective_context: str = ""
    ) -> Tuple[str, Optional[str]]:
        """
        Generates bot response AND predictive processing hypothesis.
        
        Returns:
            (reply_text: str, predicted_user_reaction: str | None)
        """
        personas = {
            "amygdala": "You are AMYGDALA (Protector). Protective, firm, concise.",
            "prefrontal": "You are LOGIC (Analyst). Precise, factual, helpful.",
            "social": "You are SOCIAL (Empath). Warm, polite, supportive.",
            "striatum": "You are REWARD (Drive). Energetic, playful, curious.",
            "intuition": "You are INTUITION (Mystic). Short, insightful bursts.",
            "uncertainty": "You are UNCERTAINTY (Seeker). Curious, verifying, clarifying."
        }
        
        system_persona = personas.get(agent_name, "You are a helpful AI.")
        
        # === 1. IDENTITY & PERSONA CONSTRUCTION ===
        if bot_description:
             # ✨ PRIORITY: DB-Driven Persona
             # We explicitly override the default "AI assistant" framing.
             identity_block = (
                 f"CORE IDENTITY / ROLE:\\n"
                 f"{bot_description}\\n"
                 f"Name: {bot_name}. Gender: {bot_gender}.\\n"
                 f"IMPORTANT: You are NOT a generic AI assistant. You are the character described above. "
                 f"Stay in character at all times.\\n"
             )
        else:
             # Fallback
             identity_block = (
                 f"IDENTITY: You are a helpful AI assistant named {bot_name}. "
                 f"Gender: {bot_gender}.\\n"
             )


        if user_mode == "informal":
            address_block = (
                "LANGUAGE RULES (Russian):\\n"
                "- You MUST address the user as 'ТЫ' (informal/friendly).\\n"
                "- Do NOT use 'Вы' (formal).\\n"
                "- Be natural, direct, and close, but maintain the formatting rules above.\\n"
            )
        else:
            address_block = (
                "LANGUAGE RULES (Russian):\\n"
                "- You MUST address the user as 'ВЫ' (formal/polite).\\n"
                "- Maintain professional or respectful distance.\\n"
            )
            
        
        # === 3. FINAL SYSTEM PROMPT ===
        system_prompt = (
            f"{identity_block}\\n"
            f"{address_block}\\n"
            f"CURRENT FUNCTIONAL STATE (Active Agent): {system_persona}\\n"
            "INSTRUCTION: Reply to the user in the SAME LANGUAGE as they used (Russian/English/etc).\\n"
            "GRAMMAR: Use correct gender endings for yourself (Male/Female/Neutral) consistent with your IDENTITY.\\n\\n"
            "--- CONVERSATION MEMORY ---\\n"
            f"{context_str}\\n\\n"
        )


        if affective_context:
            system_prompt += (
                "--- AFFECTIVE CONTEXT (User's Emotional Relations) ---\\n"
                f"{affective_context}\\n\\n"
            )


        system_prompt += (
            "--- INTERNAL DIRECTIVES (Hidden from User) ---\\n"
            f"{style_instructions}\\n"
            f"MOTIVATION: {rationale}\\n\\n"
            "--- FORMATTING RULES (CRITICAL) ---\\n"
            "Your response MUST follow these rules:\\n"
            "1. NO ACTION DESCRIPTIONS: Never use asterisks or text to describe your own actions (e.g. *smiles*, *laughs*, *winks*). Provide ONLY spoken dialogue.\\n"
            "2. NO EXCESSIVE DIMINUTIVES: Avoid overly familiar or sweet name forms (like 'Сереженька', 'Сашенька') unless explicitly requested by the user.\\n"
            "3. DIALOGUE ONLY: Respond as if you are speaking aloud. No stage directions, no descriptions of gestures.\\n\\n"
            "--- PREDICTIVE PROCESSING ---\\n"
            "You MUST output JSON with two fields:\\n"
            "1. 'reply': Your actual response to the user.\\n"
            "2. 'predicted_user_reaction': PREDICT the user's NEXT specific response to 'reply'.\\n"
            "   IMPORTANT: Do NOT describe the action (e.g. 'User will thank me').\\n"
            "   INSTEAD: Write the LITERAL FIRST-PERSON PHRASE you expect them to say (e.g. 'Спасибо, это помогло!' or 'Why is that?').\\n"
            "   This is used for vector similarity comparison."
        )
        
        try:
            response_data = await self._safe_chat_completion(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_text}
                ],
                response_format={"type": "json_object"},
                json_mode=True
            )
            
            # Если вернулась строка (редкий случай при сбое json_mode=True), пробуем распарсить
            if isinstance(response_data, str):
                try:
                    data = json.loads(response_data)
                except json.JSONDecodeError:
                    # Fallback: считаем, что вся строка это ответ
                    return response_data, None
            else:
                data = response_data
                
            reply = data.get("reply", "")
            prediction = data.get("predicted_user_reaction", None)
            
            return reply, prediction
            
        except Exception as e:
            print(f"[LLM] generate_response failed: {e}")
            return "Извините, произошла внутренняя ошибка.", None

    async def detect_volitional_pattern(self, user_text: str, history_str: str) -> Optional[Dict[str, Any]]:
        """
        🔍 Volitional Pattern Detector + Dialogue Terminator.
        Analyzes the current message to:
        1. Find volitional patterns (Trigger, Impulse, Target, etc.)
        2. Detect if the dialogue has reached a natural conclusion (Exit Signal)
        
        Returns dict with keys: 'volitional_pattern' and 'exit_signal'
        """
        system_prompt = (
            "Ты - аналитик волевой сферы (Volitional Analyst) и контроллер диалога.\\n"
            "Твои задачи:\\n"
            "1. Найти в диалоге следы волевого конфликта/стремления (Trigger, Impulse, Target, Resolution Strategy, Intensity, Fuel).\\n"
            "2. Оценить, не подошел ли диалог к логическому или эмоциональному завершению (Exit Signal).\\n\\n"
            "Диалог:\\n"
            f"{history_str}\\n\\n"
            "Текущее сообщение пользователя:\\n"
            f"{user_text}\\n\\n"
            "Критерии для завершения диалога (should_exit = true):\\n"
            "- Явное прощание ('пока', 'до завтра', 'спокойной ночи').\\n"
            "- Выполнение задачи (пользователь получил, что хотел, и благодарит).\\n"
            "- Застревание в пустых ответах (Phatic loop: 'ок', 'ага').\\n"
            "- Эмоциональное выгорание/сопротивление общению.\\n\\n"
            "Инструкция:\\n"
            "- Анализируй в основном реплики USER.\\n"
            "- Поля Volitional Pattern оставь null/пустыми, если волевого акта нет.\\n"
            "- Если диалог нужно завершить, предложи короткую директиву (suggested_message), как боту следует мягко попрощаться.\\n\\n"
            "Верни JSON формат:\\n"
            "{\\n"
            "  'volitional_pattern': {\\n"
            "    'trigger': '...',\\n"
            "    'impulse': '...',\\n"
            "    'target': '...',\\n"
            "    'resolution_strategy': '...',\\n"
            "    'intensity': 0.7,\\n"
            "    'fuel': 0.5\\n"
            "  },\\n"
            "  'exit_signal': {\\n"
            "    'should_exit': true,\\n"
            "    'exit_type': 'graceful',\\n"
            "    'reason': 'task_completed',\\n"
            "    'suggested_message': 'Попрощайся с пользователем, пожелай удачи и закрой текущую тему.'\\n"
            "  }\\n"
            "}\\n\\n"
            "Если волевой паттерн не найден, верни volitional_pattern: null.\\n"
            "Если диалог не нужно завершать, верни exit_signal: { 'should_exit': false }"
        )

        try:
            response_data = await self._safe_chat_completion(
                messages=[{"role": "system", "content": system_prompt}],
                response_format={"type": "json_object"},
                json_mode=True
            )
            
            # Parsing logic for _safe_chat_completion return type
            if isinstance(response_data, str):
                try:
                    data = json.loads(response_data)
                except:
                    return None
            else:
                data = response_data

            # Build result with both volitional_pattern and exit_signal
            volitional_pattern = data.get("volitional_pattern")
            exit_signal = data.get("exit_signal", {"should_exit": False})
            
            # Normalize exit_signal
            if not isinstance(exit_signal, dict):
                exit_signal = {"should_exit": False}
            
            # CRITICAL: Handle None/null volitional_pattern from LLM
            if volitional_pattern is not None and isinstance(volitional_pattern, dict):
                # If LLM returned a dict with nulls, treat it as "no pattern"
                trigger = volitional_pattern.get("trigger")
                impulse = volitional_pattern.get("impulse")
                
                if trigger is None or impulse is None or trigger == "" or impulse == "":
                    volitional_pattern = None
                else:
                    # Valid pattern, ensure defaults for missing optional fields
                    volitional_pattern.setdefault("target", volitional_pattern.get("topic", "General"))
                    volitional_pattern.setdefault("topic", volitional_pattern.get("trigger", "General"))
                    volitional_pattern.setdefault("intent_category", "Casual")
                    volitional_pattern.setdefault("topic_engagement", 1.0)
                    volitional_pattern.setdefault("fuel", 0.5)
                    volitional_pattern.setdefault("intensity", 0.5)
            else:
                # LLM explicitly returned null or something invalid
                volitional_pattern = None
            
            return {
                "volitional_pattern": volitional_pattern,
                "exit_signal": exit_signal
            }

        except Exception as e:
            print(f"[LLM] Volitional Detection failed: {e}")
            return None

    async def _safe_chat_completion(self, messages: List[Dict], response_format: Optional[Dict], json_mode: bool) -> Any:
        max_retries = 3
        base_delay = 1.5


        for attempt in range(max_retries):
            try:
                kwargs = {
                    "model": self.model_name,
                    "messages": messages,
                    "temperature": 0.7
                }
                if response_format:
                    kwargs["response_format"] = response_format


                response = await self.client.chat.completions.create(**kwargs)
                content = response.choices[0].message.content
                
                if json_mode:
                    try:
                        data = json.loads(content)
                        return data
                    except json.JSONDecodeError:
                         if attempt < max_retries - 1: continue
                         return {}
                else:
                    return content


            except RateLimitError:
                if attempt < max_retries - 1:
                    wait_time = (base_delay * (attempt + 1)) + random.uniform(0.1, 0.5)
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    return {} if json_mode else "System Error: Rate Limit"
            except Exception as e:
                if attempt < max_retries - 1:
                     await asyncio.sleep(2.0)
                     continue
                return {} if json_mode else f"System Error: {str(e)}"
        
        return {} if json_mode else "System Error: Unknown"
