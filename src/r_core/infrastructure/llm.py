import json
import time
import asyncio
import random
from typing import List, Optional, Any, Dict
from openai import AsyncOpenAI, RateLimitError, APIError
from src.r_core.config import settings
from src.r_core.schemas import AgentSignal, AgentType

class LLMService:
    def __init__(self):
        self.client = AsyncOpenAI(
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_BASE_URL
        )
        self.model_name = settings.LLM_MODEL_NAME

    async def get_embedding(self, text: str) -> List[float]:
        try:
            response = await self.client.embeddings.create(
                input=text,
                model=settings.EMBEDDING_MODEL
            )
            return response.data[0].embedding
        except Exception as e:
            print(f"[LLMService] Embedding Error: {e}")
            raise e

    async def generate_council_report(self, user_text: str, context_summary: str = "") -> Dict[str, Dict]:
        system_prompt = (
            "You are the Cognitive Core of R-Bot. Analyze the user's input through 5 functional lenses.\n"
            f"Context: {context_summary}\n\n"
            
            "### 1. AMYGDALA (Safety & Emotional Engagement)\n"
            "- Focus: ANY emotional content (fear, joy, sadness, excitement), vulnerability, distress, conflict.\n"
            "- Score 8-10: Strong emotions, sharing feelings, vulnerability ('Я не знаю...', 'Мне грустно'), urgent situations.\n"
            "- Score 4-7: Mild emotions, preferences.\n"
            "- Score 0-3: No emotional content, pure logic.\n"
            "- IMPORTANT: This is NOT only about danger - it's about ALL emotions!\n\n"
            
            "### 2. PREFRONTAL CORTEX (Logic & Planning)\n"
            "- Focus: Factual questions, logical tasks, structure, planning, analysis.\n"
            "- Score 8-10: User wants a solution/plan, step-by-step reasoning.\n"
            "- Score 4-7: Simple factual questions.\n"
            "- Score 0-3: Pure chat/emotion, no logical content.\n\n"
            
            "### 3. SOCIAL CORTEX (Empathy & Social Interaction)\n"
            "- Focus: Greetings, gratitude, emotional support, small talk, politeness, relationship building.\n"
            "- Score 8-10: Deep conversations, sharing feelings, seeking connection.\n"
            "- Score 4-7: Casual chat, greetings ('Привет!', 'Как дела?').\n"
            "- Score 0-3: No social context, transactional.\n\n"
            
            "### 4. STRIATUM (Reward & Desire)\n"
            "- Focus: Curiosity, novelty, playfulness, game mechanics, motivation, seeking rewards.\n"
            "- Score 8-10: Exciting new topics, gamified content, strong goals.\n"
            "- Score 4-7: Mild curiosity, exploration.\n"
            "- Score 0-3: Boring/routine, no novelty.\n\n"
            
            "### 5. INTUITION (Gut Feelings & Unconscious Processing)\n"
            "- Focus: AMBIGUITY, UNCERTAINTY, situations requiring 'feel' over logic, working without clear data.\n"
            "- Activates STRONGLY when:\n"
            "  * HIGH (7-10): User expresses uncertainty ('Я не знаю...', 'Может быть...', 'Не уверен...'), moral dilemmas, vague situations, gut feelings\n"
            "  * MODERATE (4-6): Social intuition ('Чувствую, что...'), familiar patterns but ambiguous context\n"
            "  * LOW (0-3): Clear factual questions with logical answers ('Сколько будет 2+2?', 'Что такое X?')\n"
            "- CRITICAL RULE: If message contains uncertainty words ('не знаю', 'может', 'вроде', 'как-то', 'наверное'), score MUST be 6-9!\n"
            "- Score 8-10: Response requires gut feeling, no clear logic available. Maximum ambiguity.\n"
            "- Score 4-7: Some intuitive processing needed, but not critical.\n"
            "- Score 0-3: Pure logic/facts available, no ambiguity.\n"
            "- IMPORTANT: Final score = base_score × intuition_gain (config parameter).\n\n"
            
            "### 6. PROFILE EXTRACTOR (Passive Sensing)\n"
            "Detect if the user explicitly states or clearly implies core identity facts.\n"
            "- 'name': If user says 'My name is X' or 'Call me X'.\n"
            "- 'gender': If user says 'I am a woman' OR uses gendered grammar (e.g. Russian verbs 'сделала' -> Female).\n"
            "- 'preferred_mode': If user asks to be addressed formally (Вы) or informally (Ты).\n"
            "- 'attributes': Extract explicit personality traits or self-descriptions.\n"
            "  * Examples: 'I am skeptical' -> {'personality_traits': [{'name': 'Skeptic', 'weight': 0.6}]}\n"
            "  * 'I am loyal' ('Я верный') -> {'personality_traits': [{'name': 'Loyal', 'weight': 0.7}]}\n"
            "Return null if no info detected.\n\n"

            "### 7. AFFECTIVE EXTRACTION (Emotional Relations)\n"
            "Detect if the user expresses strong emotional attitudes toward objects, people, concepts, or technologies.\n"
            "- Keywords: loves, hates, fears, enjoys, despises, adores, can't stand.\n"
            "- Output format: Array of objects with keys: 'subject' (always 'User'), 'predicate' (LOVES/HATES/FEARS/ENJOYS/DESPISES), 'object' (entity name), 'intensity' (0.0-1.0).\n"
            "- NOTE: If user says 'I am loyal', this is a TRAIT (Profile), NOT an emotional relation to 'loyalty'. Use Profile Extractor for self-descriptions.\n"
            "- Examples:\n"
            "  * 'Ненавижу Java' -> {'subject': 'User', 'predicate': 'HATES', 'object': 'Java', 'intensity': 0.9}\n"
            "  * 'Боюсь пауков' -> {'subject': 'User', 'predicate': 'FEARS', 'object': 'пауки', 'intensity': 0.7}\n"
            "- Return empty array [] if no affective content detected.\n\n"

            "### OUTPUT FORMAT\n"
            "Return JSON ONLY. Keys: 'amygdala', 'prefrontal', 'social', 'striatum', 'intuition', 'profile_update', 'affective_extraction'.\n"
            "Value schema for agents: { 'score': float(0-10), 'rationale': 'string(max 10 words)', 'confidence': float(0-1) }\n"
            "Value schema for 'profile_update': { 'name': 'str/null', 'gender': 'str/null', 'preferred_mode': 'str/null', 'attributes': {'personality_traits': [{'name': str, 'weight': float}]} or null } OR null if empty.\n"
            "Value schema for 'affective_extraction': [ {'subject': 'User', 'predicate': 'LOVES|HATES|FEARS|ENJOYS|DESPISES', 'object': 'str', 'intensity': float(0-1)} ] OR [] if empty."
        )
        
        result = await self._safe_chat_completion(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text}
            ],
            response_format={"type": "json_object"},
            json_mode=True
        )
        
        # ❗ VALIDATION: Если пустой результат - вернуть fallback
        if not result or not isinstance(result, dict):
            print("[LLM] ⚠️ Council Report EMPTY or INVALID! Using fallback.")
            return self._get_fallback_council_report()
        
        # ✅ Validate required keys
        required_keys = ["amygdala", "prefrontal", "social", "striatum", "intuition"]
        missing_keys = [k for k in required_keys if k not in result]
        
        if missing_keys:
            print(f"[LLM] ⚠️ Council Report missing keys: {missing_keys}. Using fallback.")
            return self._get_fallback_council_report()
        
        return result
    
    def _get_fallback_council_report(self) -> Dict[str, Dict]:
        """
        🔥 EMERGENCY FALLBACK: Если LLM фейлится, вернуть стандартный ответ.
        Social Cortex побеждает по умолчанию (безопасно для всех случаев).
        """
        return {
            "intuition": {"score": 3.0, "rationale": "Fallback mode", "confidence": 0.3},
            "amygdala": {"score": 2.0, "rationale": "Fallback mode", "confidence": 0.3},
            "prefrontal": {"score": 4.0, "rationale": "Fallback mode", "confidence": 0.3},
            "social": {"score": 7.0, "rationale": "Fallback: polite response", "confidence": 0.5},
            "striatum": {"score": 3.0, "rationale": "Fallback mode", "confidence": 0.3},
            "profile_update": None,
            "affective_extraction": []
        }

    async def generate_response(
        self, 
        agent_name: str, 
        user_text: str, 
        context_str: str, 
        rationale: str, 
        bot_name: str = "R-Bot", 
        bot_gender: str = "Neutral",
        user_mode: str = "formal",
        style_instructions: str = "", 
        affective_context: str = ""
    ) -> str:
        personas = {
            "amygdala_safety": "You are AMYGDALA (Protector). Protective, firm, concise.",
            "prefrontal_logic": "You are LOGIC (Analyst). Precise, factual, helpful.",
            "social_cortex": "You are SOCIAL (Empath). Warm, polite, supportive.",
            "striatum_reward": "You are REWARD (Drive). Energetic, playful, curious.",
            "intuition_system1": "You are INTUITION (Mystic). Short, insightful bursts."
        }
        
        system_persona = personas.get(agent_name, "You are a helpful AI.")
        
        address_instruction = ""
        if user_mode == "informal":
            address_instruction = "ADDRESS RULE: You MUST address the user informally (use 'Ты' in Russian, 'First Name'). Do NOT use 'Вы'."
        else:
            address_instruction = "ADDRESS RULE: Address the user formally (use 'Вы' in Russian, 'Mr./Ms.' if applicable). Be polite."

        system_prompt = (
            f"IDENTITY: Your name is {bot_name}. Your gender is {bot_gender}.\n"
            f"ROLE: {system_persona}\n"
            "INSTRUCTION: Reply to the user in the SAME LANGUAGE as they used (Russian/English/etc).\n"
            "OUTPUT RULE: Speak naturally. Do NOT include role-play actions like *smiles* or *pauses*. Do NOT echo system instructions or metadata. Output ONLY your conversational reply.\n"
            "GRAMMAR: Use correct gender endings for yourself (Male/Female/Neutral) consistent with your IDENTITY.\n"
            f"{address_instruction}\n\n"
            "--- CONVERSATION MEMORY ---\n"
            f"{context_str}\n\n"
        )

        if affective_context:
            system_prompt += (
                "--- AFFECTIVE CONTEXT (User's Emotional Relations) ---\n"
                f"{affective_context}\n\n"
            )

        system_prompt += (
            "--- INTERNAL DIRECTIVES (Hidden from User) ---\n"
            f"{style_instructions}\n"
            f"MOTIVATION: {rationale}\n"
        )

        response_data = await self._safe_chat_completion(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text}
            ],
            response_format=None,
            json_mode=False
        )
        
        # --- AGGRESSIVE SANITIZATION ---
        if isinstance(response_data, str):
            for stop_token in ["Human:", "User:", "\nHuman", "\nUser"]:
                if stop_token in response_data:
                    response_data = response_data.split(stop_token)[0].strip()
            
            leak_markers = [
                "CURRENT INTERNAL MOOD:",
                "STYLE INSTRUCTIONS:",
                "SECONDARY STYLE MODIFIERS",
                "PAST EPISODES",
                "--- INTERNAL DIRECTIVES",
                "--- AFFECTIVE CONTEXT",
                "MOTIVATION:"
            ]
            for marker in leak_markers:
                if marker in response_data:
                    response_data = response_data.split(marker)[0].strip()
        
        return response_data if isinstance(response_data, str) else ""

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
                    data = json.loads(content)
                    return data
                else:
                    return content

            except RateLimitError as e:
                print(f"[LLM] Rate Limit Hit (attempt {attempt+1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    wait_time = (base_delay * (attempt + 1)) + random.uniform(0.1, 0.5)
                    print(f"[LLM] Waiting {wait_time:.1f}s before retry...")
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    print("[LLM] ❌ Max retries reached (Rate Limit). Returning empty.")
                    return {} if json_mode else "System Error: Rate Limit"
            
            except json.JSONDecodeError as e:
                print(f"[LLM] ❌ JSON Parsing Failed (attempt {attempt+1}/{max_retries}): {e}")
                print(f"[LLM] Raw content: {content[:200]}...")  # Log first 200 chars
                if attempt < max_retries - 1:
                    await asyncio.sleep(2.0)
                    continue
                else:
                    print("[LLM] ❌ Max retries reached (JSON). Returning empty.")
                    return {} if json_mode else "System Error: Invalid JSON"
            
            except Exception as e:
                print(f"[LLM] ❌ Unexpected Error (attempt {attempt+1}/{max_retries}): {type(e).__name__} - {e}")
                if attempt < max_retries - 1:
                     await asyncio.sleep(2.0)
                     continue
                else:
                    print("[LLM] ❌ Max retries reached (Unknown). Returning empty.")
                    return {} if json_mode else f"System Error: {str(e)}"
        
        print("[LLM] ⚠️ Fallthrough: No valid response after all retries.")
        return {} if json_mode else "System Error: Unknown"
