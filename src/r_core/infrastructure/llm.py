import json
import time
from typing import List, Optional, Any
from openai import AsyncOpenAI
# FIX: Absolute import instead of relative
from src.r_core.config import settings
# FIX: Absolute import
from src.r_core.schemas import AgentSignal, AgentType

class LLMService:
    """
    Central service for LLM interactions (Chat & Embeddings).
    Wraps OpenAI-compatible API (VseGPT / DeepSeek / OpenAI).
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
            start_ts = time.time()
            response = await self.client.embeddings.create(
                input=text,
                model=settings.EMBEDDING_MODEL
            )
            # Log metrics here if needed, or return meta
            return response.data[0].embedding
        except Exception as e:
            print(f"[LLMService] Embedding Error: {e}")
            # Return zero vector or raise? Raising is better for now.
            raise e

    async def generate_signal(self, system_prompt: str, user_text: str, agent_name: AgentType) -> AgentSignal:
        """
        Generates a structured AgentSignal from LLM.
        """
        start_ts = time.time()
        
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
        
        # Determine model based on config or agent needs
        # For VseGPT, we often use specific model names
        model_name = "deepseek/deepseek-chat" if "vsegpt" in settings.OPENAI_BASE_URL else "gpt-4-turbo-preview"

        try:
            response = await self.client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": full_system},
                    {"role": "user", "content": user_text}
                ],
                temperature=0.7,
                response_format={"type": "json_object"} # Hints to the API to output JSON
            )
            
            content = response.choices[0].message.content
            latency = int((time.time() - start_ts) * 1000)
            
            # Parse JSON
            try:
                data = json.loads(content)
            except json.JSONDecodeError:
                # Fallback if model chatters
                print(f"[LLMService] JSON Parse Error. Raw: {content}")
                return AgentSignal(
                    agent_name=agent_name,
                    score=0.0,
                    rationale_short="Error: Invalid JSON response",
                    confidence=0.0,
                    latency_ms=latency
                )

            return AgentSignal(
                agent_name=agent_name,
                score=float(data.get("score", 0.0)),
                rationale_short=data.get("rationale_short", "No rationale"),
                confidence=float(data.get("confidence", 0.0)),
                latency_ms=latency
            )

        except Exception as e:
            print(f"[LLMService] Generation Error: {e}")
            return AgentSignal(
                agent_name=agent_name,
                score=0.0,
                rationale_short=f"LLM Error: {str(e)}",
                confidence=0.0,
                latency_ms=0
            )
