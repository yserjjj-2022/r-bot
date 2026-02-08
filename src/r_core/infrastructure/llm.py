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
            "You are the Cognitive Core of R-Bot. Analyze the user's input through 4 functional lenses.\n"
            f"Context: {context_summary}\n\n"
            
            "### 1. AMYGDALA (Safety & Threat)\n"
            "- Focus: Aggression, boundary violation, high risk, distress, conflict.\n"
            "- Score 8-10: Hostile/Unsafe/Urgent. Score 0-2: Safe/Neutral.\n\n"
            
            "### 2. PREFRONTAL CORTEX (Logic & Planning)\n"
            "- Focus: Factual questions, logical tasks, structure, planning, analysis.\n"
            "- Score 8-10: User wants a solution/plan. Score 0-2: Pure chat/emotion.\n\n"
            
            "### 3. SOCIAL CORTEX (Empathy & Norms)\n"
            "- Focus: Greetings, gratitude, emotional support, small talk, politeness.\n"
            "- Score 8-10: Social/Emotional interaction. Score 0-2: Dry/Transactional.\n\n"
            
            "### 4. STRIATUM (Reward & Desire)\n"
            "- Focus: Curiosity, playfulness, game mechanics, opportunities for fun/goals.\n"
            "- Score 8-10: Exciting/Gamified. Score 0-2: Boring/Routine.\n\n"
            
            "### 5. PROFILE EXTRACTOR (Passive Sensing)\n"
            "Detect if the user explicitly states or clearly implies core identity facts.\n"
            "- 'name': If user says 'My name is X' or 'Call me X'.\n"
            "- 'gender': If user says 'I am a woman' OR uses gendered grammar (e.g. Russian verbs 'сделала', 'устала' -> Female; 'сделал' -> Male).\n"
            "- 'preferred_mode': If user asks to be addressed formally (Вы) or informally (Ты).\n"
            "Return null if no info detected.\n\n"

            "### 6. AFFECTIVE EXTRACTION (Emotional Relations)\n"
            "Detect if the user expresses strong emotional attitudes toward objects, people, concepts, or technologies.\n"
            "- Keywords: loves, hates, fears, enjoys, despises, adores, can't stand, passionate about, disgusted by.\n"
            "- Output format: Array of objects with keys: 'subject' (always 'User'), 'predicate' (LOVES/HATES/FEARS/ENJOYS/DESPISES), 'object' (entity name), 'intensity' (0.0-1.0).\n"
            "- Examples:\n"
            "  * 'Ненавижу Java' → {'subject': 'User', 'predicate': 'HATES', 'object': 'Java', 'intensity': 0.9}\n"
            "  * 'Обожаю Python' → {'subject': 'User', 'predicate': 'LOVES', 'object': 'Python', 'intensity': 0.85}\n"
            "  * 'Боюсь пауков' → {'subject': 'User', 'predicate': 'FEARS', 'object': 'пауки', 'intensity': 0.7}\n"
            "- Return empty array [] if no affective content detected.\n\n"

            "### OUTPUT FORMAT\n"
            "Return JSON ONLY. Keys: 'amygdala', 'prefrontal', 'social', 'striatum', 'profile_update', 'affective_extraction'.\n"
            "Value schema for agents: { 'score': float(0-10), 'rationale': 'string(max 10 words)', 'confidence': float(0-1) }\n"
            "Value schema for 'profile_update': { 'name': 'str or null', 'gender': 'Male/Female/Neutral or null', 'preferred_mode': 'formal/informal or null' } OR null if empty.\n"
            "Value schema for 'affective_extraction': [ {'subject': 'User', 'predicate': 'LOVES|HATES|FEARS|ENJOYS|DESPISES', 'object': 'str', 'intensity': float(0-1)} ] OR [] if empty."
        )
        
        return await self._safe_chat_completion(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text}
            ],
            response_format={"type": "json_object"},
            json_mode=True
        )

    async def generate_response(
        self, 
        agent_name: str, 
        user_text: str, 
        context_str: str, 
        rationale: str, 
        bot_name: str = "R-Bot", 
        bot_gender: str = "Neutral",
        user_mode: str = "formal",
        style_instructions: str = "",  # NEW: Separate parameter to prevent leakage
        affective_context: str = ""  # ✨ NEW: Affective warnings from memory
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

        # --- CRITICAL FIX: Separate style from context ---
        # Context is for memory/facts. Style is for tone modulation.
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

        # ✨ NEW: Add affective context warnings
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
            # Stop leakage of simulated turns
            for stop_token in ["Human:", "User:", "\nHuman", "\nUser"]:
                if stop_token in response_data:
                    response_data = response_data.split(stop_token)[0].strip()
            
            # Stop leakage of metadata blocks (if LLM echoes system prompt)
            leak_markers = [
                "CURRENT INTERNAL MOOD:",
                "STYLE INSTRUCTIONS:",
                "SECONDARY STYLE MODIFIERS", # NEW: Caught you!
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
