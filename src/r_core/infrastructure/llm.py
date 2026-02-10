import json
import time
import asyncio
import random
import re
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
            "You are the Cognitive Core of R-Bot. Analyze input through 5 lenses.\n"
            f"Context: {context_summary}\n\n"
            
            "### 1. AMYGDALA (Safety/Emotion)\n"
            "- Score 8-10: Strong emotions, vulnerability, urgency.\n"
            "- Score 0-3: Pure logic.\n\n"
            
            "### 2. PREFRONTAL (Logic/Plan)\n"
            "- Score 8-10: User wants a solution/plan, reasoning.\n"
            "- Score 0-3: Pure chat/emotion.\n\n"
            
            "### 3. SOCIAL (Rituals/Politeness)\n"
            "- Score 8-10: Greetings, small talk, gratitude.\n"
            "- CRITICAL: If user shares DEEP feelings/identity → score 0-3! That's Intuition.\n\n"
            
            "### 4. STRIATUM (Curiosity/Reward)\n"
            "- Score 8-10: Novelty, games, goals, fun.\n\n"
            
            "### 5. INTUITION (Ambiguity/Self)\n"
            "- Focus: AMBIGUITY, SELF-REFLECTION, IDENTITY.\n"
            "- Score 8-10: Deep self-reflection ('Who am I?'), existential questions.\n"
            "- Score 5-7: Uncertainty ('Maybe...').\n"
            "- Score 0-4: Factual/Clear inputs.\n"
            "- Important: Final score = base_score * intuition_gain.\n\n"
            
            "### 6. PROFILE EXTRACTOR\n"
            "Detect: 'name', 'gender', 'preferred_mode' (Ty/Vy), 'attributes' (traits).\n"
            "Return null if none.\n\n"

            "### 7. AFFECTIVE EXTRACTION\n"
            "Detect strong emotional attitudes: 'HATES X', 'LOVES Y', 'FEARS Z'.\n"
            "Format: {subject: 'User', predicate: 'LOVES', object: '...', intensity: 0.0-1.0}\n\n"

            "### OUTPUT JSON\n"
            "Keys: 'amygdala', 'prefrontal', 'social', 'striatum', 'intuition', 'profile_update', 'affective_extraction'.\n"
            "Agent schema: { 'score': float(0-10), 'rationale': 'short string', 'confidence': float(0-1) }"
        )
        
        result = await self._safe_chat_completion(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text}
            ],
            response_format={"type": "json_object"},
            json_mode=True
        )
        
        if not result or not isinstance(result, dict):
            print("[LLM] ⚠️ Council Report EMPTY/INVALID. Fallback.")
            return self._get_fallback_council_report()
        
        required_keys = ["amygdala", "prefrontal", "social", "striatum", "intuition"]
        if any(k not in result for k in required_keys):
            print(f"[LLM] ⚠️ Missing keys in Council Report. Fallback.")
            return self._get_fallback_council_report()
        
        return result
    
    def _get_fallback_council_report(self) -> Dict[str, Dict]:
        return {
            "intuition": {"score": 3.0, "rationale": "Fallback", "confidence": 0.3},
            "amygdala": {"score": 2.0, "rationale": "Fallback", "confidence": 0.3},
            "prefrontal": {"score": 4.0, "rationale": "Fallback", "confidence": 0.3},
            "social": {"score": 7.0, "rationale": "Fallback", "confidence": 0.5},
            "striatum": {"score": 3.0, "rationale": "Fallback", "confidence": 0.3},
            "profile_update": None,
            "affective_extraction": []
        }

    def _should_suppress_questions(self, agent_name: str, confidence: float, user_text: str) -> bool:
        uncertainty_markers = [
            "не знаю", "может быть", "наверное", "вроде", "как-то",
            "не уверен", "сомневаюсь", "don't know", "maybe", "not sure"
        ]
        if any(marker in user_text.lower() for marker in uncertainty_markers):
            return False
        
        if agent_name in ["social_cortex", "striatum_reward"]:
            return False
        
        if agent_name in ["intuition_system1", "prefrontal_logic", "amygdala_safety"]:
            if confidence > 0.7:
                return True
        
        return False

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
        affective_context: str = "",
        winner_confidence: float = 0.5
    ) -> str:
        personas = {
            "amygdala_safety": "Role: AMYGDALA (Protector). Protective, firm, concise.",
            "prefrontal_logic": "Role: LOGIC (Analyst). Precise, factual, helpful.",
            "social_cortex": "Role: SOCIAL (Empath). Warm, polite, supportive.",
            "striatum_reward": "Role: REWARD (Drive). Energetic, playful, curious.",
            "intuition_system1": "Role: INTUITION (Mystic). Short, insightful bursts."
        }
        
        system_persona = personas.get(agent_name, "Role: AI Assistant.")
        
        # 🔥 CRITICAL: Address Rule Logic
        if user_mode == "informal":
            address_instruction = "IMPORTANT: Use INFORMAL address ('Ты'). Do NOT use 'Вы'."
        else:
            address_instruction = "IMPORTANT: Use FORMAL address ('Вы'). Be polite."

        suppress_questions = self._should_suppress_questions(agent_name, winner_confidence, user_text)
        question_rule = ""
        if suppress_questions:
            question_rule = "NO QUESTIONS. State your insight and STOP."
            print(f"[LLM] 🚫 Questions suppressed for {agent_name}")
        else:
            print(f"[LLM] ✅ Questions allowed for {agent_name}")

        # ✨ COMPRESSED SYSTEM PROMPT
        system_prompt = (
            f"ID: {bot_name} ({bot_gender}).\n"
            f"{system_persona}\n"
            "Lang: Match user.\n"
            "Output: Natural speech only. No meta-tags.\n"
            f"{question_rule}\n\n"
            "### CONTEXT\n"
            f"{context_str}\n\n"
        )

        if affective_context:
            system_prompt += (
                "### EMOTIONS\n"
                f"{affective_context}\n"
            )

        # 🔥 STYLE & FINAL OVERRIDES
        system_prompt += (
            "### INSTRUCTIONS\n"
            f"{style_instructions}\n"
            f"Goal: {rationale}\n\n"
            f"🔥 CRITICAL OVERRIDE: {address_instruction} This rule ignores all others.\n"
        )

        response_data = await self._safe_chat_completion(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text}
            ],
            response_format=None,
            json_mode=False
        )
        
        # --- Sanitization ---
        if isinstance(response_data, str):
            for stop_token in ["Human:", "User:", "\nHuman", "\nUser"]:
                if stop_token in response_data:
                    response_data = response_data.split(stop_token)[0].strip()
            
            leak_markers = [
                "MOOD_STATE:", "STYLE_TOKENS:", "### INSTRUCTIONS", "Goal:", "🔥 CRITICAL"
            ]
            for marker in leak_markers:
                if marker in response_data:
                    response_data = response_data.split(marker)[0].strip()
            
            if suppress_questions:
                question_tails = ["Что ты думаешь?", "Как ты относишься?", "What do you think?"]
                for tail in question_tails:
                    if response_data.strip().endswith(tail):
                        response_data = response_data.rsplit(tail, 1)[0].strip()
        
        return response_data if isinstance(response_data, str) else ""

    def _strip_markdown_json(self, content: str) -> str:
        content = content.strip()
        if content.startswith("```"):
            lines = content.split("\n", 1)
            content = lines[1] if len(lines) > 1 else ""
        if content.rstrip().endswith("```"):
            content = content.rstrip()[:-3].rstrip()
        
        content = content.strip()
        if not content.startswith("{"):
            return content
        
        brace_count = 0
        in_string = False
        escape = False
        
        for i, char in enumerate(content):
            if char == '"' and not escape:
                in_string = not in_string
            elif char == '\\' and not escape:
                escape = True
                continue
            
            if not in_string:
                if char == '{': brace_count += 1
                elif char == '}': brace_count -= 1
                    
                if brace_count == 0:
                    return content[:i+1]
            escape = False
        return content

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
                    clean_content = self._strip_markdown_json(content)
                    return json.loads(clean_content)
                else:
                    return content

            except Exception as e:
                print(f"[LLM] ❌ Error (attempt {attempt+1}): {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(base_delay * (attempt + 1))
                else:
                    return {} if json_mode else f"Error: {str(e)}"
        
        return {} if json_mode else "Error: Unknown"
