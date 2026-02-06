import json
import time
import asyncio
import random
from typing import List, Optional, Any
from openai import AsyncOpenAI, RateLimitError, APIError
from src.r_core.config import settings
from src.r_core.schemas import AgentSignal, AgentType

class LLMService:
    """
    Central service for LLM interactions (Chat & Embeddings).
    Wraps OpenAI-compatible API (VseGPT / DeepSeek / OpenAI).
    Includes automatic Retries for Rate Limits (429).
    """
    def __init__(self):
        self.client = AsyncOpenAI(
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_BASE_URL
        )

    async def get_embedding(self, text: str) -> List[float]:
        """
        Generates vector embedding for text.
        """
        try:
            response = await self.client.embeddings.create(
                input=text,
                model=settings.EMBEDDING_MODEL
            )
            return response.data[0].embedding
        except Exception as e:
            print(f"[LLMService] Embedding Error: {e}")
            raise e

    async def generate_signal(self, system_prompt: str, user_text: str, agent_name: AgentType) -> AgentSignal:
        """
        Generates a structured AgentSignal from LLM with Retry Logic for 429 errors.
        """
        
        # Enforce JSON output via prompt engineering
        json_schema = {
            "score": "float (0.0 - 10.0)",
            "rationale_short": "string (max 15 words)",
            "confidence": "float (0.0 - 1.0)"
        }
        
        full_system = (
            f"{system_prompt}\n\n"
            f"IMPORTANT: You are a cognitive module. Output JSON ONLY.\n"
            f"Schema: {json.dumps(json_schema)}"
        )
        
        model_name = "deepseek/deepseek-chat" if "vsegpt" in settings.OPENAI_BASE_URL else "gpt-4-turbo-preview"
        
        # --- RETRY LOGIC START ---
        max_retries = 4
        base_delay = 2.0 # Wait at least 2 seconds (VseGPT limit is 1 req/sec)

        for attempt in range(max_retries):
            start_ts = time.time()
            try:
                response = await self.client.chat.completions.create(
                    model=model_name,
                    messages=[
                        {"role": "system", "content": full_system},
                        {"role": "user", "content": user_text}
                    ],
                    temperature=0.7,
                    response_format={"type": "json_object"}
                )
                
                content = response.choices[0].message.content
                latency = int((time.time() - start_ts) * 1000)
                
                # Parse JSON
                try:
                    data = json.loads(content)
                    return AgentSignal(
                        agent_name=agent_name,
                        score=float(data.get("score", 0.0)),
                        rationale_short=data.get("rationale_short", "No rationale"),
                        confidence=float(data.get("confidence", 0.0)),
                        latency_ms=latency
                    )
                except json.JSONDecodeError:
                    print(f"[LLMService] JSON Parse Error for {agent_name}: {content[:50]}...")
                    # If JSON is bad, retrying usually doesn't help unless model is unstable.
                    # We return a fallback signal.
                    return self._fallback_signal(agent_name, latency, "Invalid JSON")

            except RateLimitError as e:
                # 429 Error caught here
                if attempt < max_retries - 1:
                    # Exponential backoff + Jitter to avoid thundering herd
                    # Attempt 0: 2.0s + rand
                    # Attempt 1: 4.0s + rand
                    wait_time = (base_delay * (attempt + 1)) + random.uniform(0.1, 1.0)
                    print(f"[LLMService] Rate Limit (429) for {agent_name}. Retrying in {wait_time:.1f}s...")
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    print(f"[LLMService] Max retries reached for {agent_name}.")
                    return self._fallback_signal(agent_name, 0, "Rate Limit Exceeded")
            
            except APIError as e:
                # VseGPT sometimes returns 502/503 on load
                print(f"[LLMService] API Error {e.code} for {agent_name}: {e.message}")
                if attempt < max_retries - 1:
                    wait_time = 3.0
                    await asyncio.sleep(wait_time)
                    continue
                return self._fallback_signal(agent_name, 0, f"API Error: {e.message}")
                
            except Exception as e:
                print(f"[LLMService] Critical Error for {agent_name}: {e}")
                return self._fallback_signal(agent_name, 0, f"Error: {str(e)}")
        
        return self._fallback_signal(agent_name, 0, "Unknown Error")

    def _fallback_signal(self, agent_name: AgentType, latency: int, reason: str) -> AgentSignal:
        return AgentSignal(
            agent_name=agent_name,
            score=0.0,
            rationale_short=f"System Fail: {reason}",
            confidence=0.0,
            latency_ms=latency
        )
