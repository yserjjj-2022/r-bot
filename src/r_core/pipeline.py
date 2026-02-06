import asyncio
from typing import Dict, List, Optional
from datetime import datetime

from .schemas import (
    IncomingMessage, 
    CoreResponse, 
    CoreAction, 
    BotConfig, 
    ProcessingMode,
    AgentType
)
from .memory import MemorySystem
from .infrastructure.llm import LLMService
from .agents import (
    IntuitionAgent,
    AmygdalaAgent,
    PrefrontalAgent,
    SocialAgent,
    StriatumAgent
)

class RCoreKernel:
    def __init__(self, config: BotConfig):
        self.config = config
        self.llm = LLMService() 
        self.memory = MemorySystem(store=None)
        
        # Init agents (now they don't need direct LLM calls usually, but we keep structure)
        self.agents = [
            IntuitionAgent(self.llm),
            AmygdalaAgent(self.llm),
            PrefrontalAgent(self.llm),
            SocialAgent(self.llm),
            StriatumAgent(self.llm)
        ]

    async def process_message(self, message: IncomingMessage) -> CoreResponse:
        start_time = datetime.now()
        
        # 1. Perception (Mock for now, Parallel)
        perception_task = self._mock_perception(message)
        
        # 2. Retrieval
        context = await self.memory.recall_context(message.user_id, message.text)
        
        # Save memory (fire and forget or wait)
        extraction_result = await perception_task
        await self.memory.memorize_event(message, extraction_result)

        # 3. Parliament Debate (OPTIMIZED: Single Batch Request)
        # Instead of 4 separate calls, we ask LLM once for all agents.
        
        # Prepare context string for LLM
        context_str = f"Found {len(context['episodic_memory'])} past episodes."
        
        # SINGLE CALL to LLM
        council_report = await self.llm.generate_council_report(message.text, context_str)
        
        # Distribute results to agents
        # Intuition still runs separately because it doesn't use LLM (System 1)
        intuition_signal = await self.agents[0].process(message, context, self.config.sliders)
        
        signals = [intuition_signal]
        
        # Map JSON report to other agents
        agent_map = {
            "amygdala": self.agents[1],
            "prefrontal": self.agents[2],
            "social": self.agents[3],
            "striatum": self.agents[4]
        }
        
        for key, agent in agent_map.items():
            report_data = council_report.get(key, {"score": 0.0, "rationale": "No signal"})
            # We inject the pre-calculated signal into the agent (or let agent verify it)
            # For now, we update the agent to accept 'external_signal_data'
            signal = agent.process_from_report(report_data, self.config.sliders)
            signals.append(signal)

        # 4. Arbitration
        signals.sort(key=lambda s: s.score, reverse=True)
        winner = signals[0]
        
        # 5. Response
        response_text = await self._generate_response(winner.agent_name, message.text)
        
        latency = (datetime.now() - start_time).total_seconds() * 1000
        
        return CoreResponse(
            actions=[
                CoreAction(type="send_text", payload={"text": response_text})
            ],
            winning_agent=winner.agent_name,
            processing_mode=ProcessingMode.SLOW_PATH,
            internal_stats={
                "latency_ms": int(latency),
                "winner_score": winner.score,
                "winner_reason": winner.rationale_short
            }
        )

    async def _mock_perception(self, message: IncomingMessage) -> Dict:
        await asyncio.sleep(0.05)
        return {
            "triples": [], 
            "anchors": [{"raw_text": message.text, "emotion_score": 0.5, "tags": ["auto"]}],
            "volitional_pattern": None
        }

    async def _generate_response(self, agent_name: AgentType, user_text: str) -> str:
        styles = {
            AgentType.AMYGDALA: f"⚠️ [Amygdala] ОСТОРОЖНО! Я чувствую напряжение: '{user_text}'.",
            AgentType.SOCIAL: f"❤️ [Social] Ох, я понимаю... '{user_text}' звучит важно. Я с тобой!",
            AgentType.PREFRONTAL: f"🧠 [Logic] Принято. Анализирую: '{user_text}'.",
            AgentType.STRIATUM: f"🔥 [Striatum] Ого! '{user_text}'?! Звучит хайпово!",
            AgentType.INTUITION: f"🔮 [Intuition] Хм... '{user_text}'... дежавю."
        }
        return styles.get(agent_name, "Я здесь.")
