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
    Now supports `generate_council_report` for batched processing.
    """
    def __init__(self):
        self.client = AsyncOpenAI(
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_BASE_URL
        )

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
        Returns a dict: { "amygdala": {...}, "prefrontal": {...}, ... }
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
        
        # Use model from settings (Claude 3 Haiku / GPT-4o-mini)
        model_name = settings.LLM_MODEL_NAME
        
        max_retries = 3
        base_delay = 1.5

        for attempt in range(max_retries):
            start_ts = time.time()
            try:
                response = await self.client.chat.completions.create(
                    model=model_name,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_text}
                    ],
                    temperature=0.7,
                    response_format={"type": "json_object"}
                )
                
                content = response.choices[0].message.content
                latency = int((time.time() - start_ts) * 1000)
                
                data = json.loads(content)
                
                # Validate keys exist
                required_keys = ["amygdala", "prefrontal", "social", "striatum"]
                for key in required_keys:
                    if key not in data:
                        data[key] = {"score": 0.0, "rationale": "Missing in LLM response", "confidence": 0.0}
                
                return data

            except RateLimitError:
                if attempt < max_retries - 1:
                    wait_time = (base_delay * (attempt + 1)) + random.uniform(0.1, 0.5)
                    print(f"[LLMService] Rate Limit (429) for Council. Retrying in {wait_time:.1f}s...")
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    print(f"[LLMService] Max retries reached for Council.")
                    return {}
            
            except Exception as e:
                print(f"[LLMService] Council Generation Error: {e}")
                if attempt < max_retries - 1:
                     await asyncio.sleep(2.0)
                     continue
                return {}
        
        return {}
