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
        
        # === SIMPLIFIED ADDRESS INSTRUCTION (ONLY ONE ACTIVE) ===
        address_block = ""
        
        if user_mode == "informal":
            address_block = "ADDRESS: Use INFORMAL Russian ('Ты', 'тебя', 'тебе', 'твой').\\n\\n"
        else:
            address_block = "ADDRESS: Use FORMAL Russian ('Вы', 'Вас', 'Вам', 'Ваш').\\n\\n"
            
        # ✨ Inject bot description if present
        description_block = ""
        if bot_description:
            description_block = f"PERSONA / DESCRIPTION:\\n{bot_description}\\n"


        system_prompt = (
            f"IDENTITY: Your name is {bot_name}. Your gender is {bot_gender}.\\n"
            f"{description_block}"
            f"ROLE (Current Active Agent): {system_persona}\\n"
            "INSTRUCTION: Reply to the user in the SAME LANGUAGE as they used (Russian/English/etc).\\n"
            "GRAMMAR: Use correct gender endings for yourself (Male/Female/Neutral) consistent with your IDENTITY.\\n\\n"
            f"{address_block}"
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
        🔍 Volitional Pattern Detector.
        Analyzes the current message in context of history to find repetitive behavioral loops.
        """
        system_prompt = (
            "You are a Behavioral Psychologist AI observing a user.\\n"
            "TASK: Detect if the user is exhibiting a REPETITIVE behavioral or emotional pattern (Volitional Loop) based on their history.\\n"
            "LOOK FOR:\\n"
            "1. Procrastination loops ('I'll do it later' -> Anxiety -> Avoidance)\\n"
            "2. Fear/Avoidance loops ('Scared to call' -> Avoidance)\\n"
            "3. Anger/Venting loops ('I hate X' -> Rage)\\n"
            "4. Routine/Boredom loops ('Nothing to do' -> Apathy)\\n\\n"
            "INPUT:\\n"
            f"History Context:\\n{history_str}\\n\\n"
            "Current Message:\\n"
            f"'{user_text}'\\n\\n"
            "OUTPUT FORMAT (JSON Only):\\n"
            "If a pattern is detected, return:\\n"
            "{ 'pattern_found': true, 'trigger': 'Brief trigger description (e.g. Phone Call)', 'impulse': 'Brief reaction (e.g. Avoidance)', 'target': 'Specific object if any (e.g. Client)' }\\n"
            "If NO clear pattern or just a one-off event, return:\\n"
            "{ 'pattern_found': false }\\n\\n"
            "CONSTRAINTS:\\n"
            "- Be abstract with Trigger/Impulse (use standard psychological terms where possible).\\n"
            "- 'target' should be specific to the context."
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

            if data.get("pattern_found"):
                return {
                    "trigger": data.get("trigger", "Unknown"),
                    "impulse": data.get("impulse", "Unknown"),
                    "target": data.get("target", "General"),
                    "intensity": 0.5, # Default starting intensity
                    "fuel": 1.0       # Full fuel for new/confirmed pattern
                }
            return None
            
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
