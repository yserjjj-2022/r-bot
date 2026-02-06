import json
import time
import asyncio
import random
from typing import List, Optional, Any, Dict
from openai import AsyncOpenAI, RateLimitError, APIError
from src.r_core.config import settings
from src.r_core.schemas import AgentSignal, AgentType

class LLMService:
    """
    Central service for LLM interactions.
    """
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
        """
        Single Batch Request to evaluate all agents at once.
        """
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
            
            "### OUTPUT FORMAT\n"
            "Return JSON ONLY. Keys: 'amygdala', 'prefrontal', 'social', 'striatum'.\n"
            "Value schema: { 'score': float(0-10), 'rationale': 'string(max 10 words)', 'confidence': float(0-1) }"
        )
        
        return await self._safe_chat_completion(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text}
            ],
            response_format={"type": "json_object"},
            json_mode=True
        )

    async def generate_response(self, agent_name: str, user_text: str, context_str: str, rationale: str) -> str:
        """
        Generates the final text response from the perspective of the winning agent.
        """
        personas = {
            "amygdala_safety": "You are the AMYGDALA (Protector). You are cautious, alert, and protective. If the user is aggressive, de-escalate firmly. If the user is distressed, warn them or set boundaries. Keep it brief and safe.",
            "prefrontal_logic": "You are the PREFRONTAL CORTEX (Logic). You are analytical, precise, and helpful. Focus on facts, plans, and solutions. Ignore emotional fluff if it's irrelevant to the task.",
            "social_cortex": "You are the SOCIAL CORTEX (Empathy). You are warm, polite, and emotionally intelligent. Validate the user's feelings. Use emoji if appropriate. Focus on connection.",
            "striatum_reward": "You are the STRIATUM (Drive). You are energetic, curious, and playful. You want to have fun, achieve goals, or get rewards. Be hype!",
            "intuition_system1": "You are INTUITION (System 1). You speak in short, insightful bursts. You noticed a pattern (deja vu). Be mysterious but helpful."
        }
        
        system_persona = personas.get(agent_name, "You are a helpful AI assistant.")
        
        system_prompt = (
            f"{system_persona}\n"
            f"Context from memory: {context_str}\n"
            f"Your internal rationale for speaking: {rationale}\n"
            "Respond naturally to the user. Do NOT start with '[AgentName]'. Just speak."
        )

        # No JSON mode here, just text
        response_data = await self._safe_chat_completion(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text}
            ],
            response_format=None,
            json_mode=False
        )
        
        return response_data if isinstance(response_data, str) else ""

    async def _safe_chat_completion(self, messages: List[Dict], response_format: Optional[Dict], json_mode: bool) -> Any:
        """
        Helper with Retry Logic for any chat completion
        """
        max_retries = 3
        base_delay = 1.5

        for attempt in range(max_retries):
            start_ts = time.time()
            try:
                # Prepare args
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
                    # Validate keys for council report if needed, but generic here
                    return data
                else:
                    return content

            except RateLimitError:
                if attempt < max_retries - 1:
                    wait_time = (base_delay * (attempt + 1)) + random.uniform(0.1, 0.5)
                    print(f"[LLMService] Rate Limit (429). Retrying in {wait_time:.1f}s...")
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    print(f"[LLMService] Max retries reached.")
                    return {} if json_mode else "System Error: Rate Limit"
            
            except Exception as e:
                print(f"[LLMService] Error: {e}")
                if attempt < max_retries - 1:
                     await asyncio.sleep(2.0)
                     continue
                return {} if json_mode else f"System Error: {str(e)}"
        
        return {} if json_mode else "System Error: Unknown"
