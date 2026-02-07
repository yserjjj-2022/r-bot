import asyncio
from typing import Dict, List, Optional
from datetime import datetime

from .schemas import (
    IncomingMessage, 
    CoreResponse, 
    CoreAction, 
    BotConfig, 
    ProcessingMode,
    AgentType,
    MoodVector  # <--- Imported MoodVector
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
        
        # --- EHS: Internal State ---
        self.current_mood = MoodVector(valence=0.1, arousal=0.1, dominance=0.0) # Neutral-positive start
        
        # Init agents
        self.agents = [
            IntuitionAgent(self.llm),
            AmygdalaAgent(self.llm),
            PrefrontalAgent(self.llm),
            SocialAgent(self.llm),
            StriatumAgent(self.llm)
        ]

    async def process_message(self, message: IncomingMessage) -> CoreResponse:
        start_time = datetime.now()
        
        # 0. Precompute Embedding
        current_embedding = None
        try:
            current_embedding = await self.llm.get_embedding(message.text)
        except Exception as e:
            print(f"[Pipeline] Embedding failed early: {e}")
        
        # 1. Perception
        perception_task = self._mock_perception(message)
        
        # 2. Retrieval (Time-Aware TODO: Implement decay ranking here)
        context = await self.memory.recall_context(
            message.user_id, 
            message.text, 
            session_id=message.session_id,
            precomputed_embedding=current_embedding
        )
        
        user_profile = context.get("user_profile", {})
        preferred_mode = user_profile.get("preferred_mode", "formal") if user_profile else "formal"

        # Save memory
        extraction_result = await perception_task
        await self.memory.memorize_event(
            message, 
            extraction_result,
            precomputed_embedding=current_embedding
        )

        # 3. Parliament Debate
        context_str = self._format_context_for_llm(context)
        
        # Council Report now effectively acts as "Hormonal Trigger" source
        council_report = await self.llm.generate_council_report(message.text, context_str)
        
        # --- Passive Profiling Update ---
        profile_update = council_report.get("profile_update")
        if profile_update:
            cleaned_update = {k: v for k, v in profile_update.items() if v is not None}
            if cleaned_update:
                print(f"[Profiling] Detected user identity update: {cleaned_update}")
                await self.memory.update_user_profile(message.user_id, cleaned_update)
        
        # Distribute results
        intuition_signal = await self.agents[0].process(message, context, self.config.sliders)
        
        signals = [intuition_signal]
        
        agent_map = {
            "amygdala": self.agents[1],
            "prefrontal": self.agents[2],
            "social": self.agents[3],
            "striatum": self.agents[4]
        }
        
        for key, agent in agent_map.items():
            report_data = council_report.get(key, {"score": 0.0, "rationale": "No signal"})
            signal = agent.process_from_report(report_data, self.config.sliders)
            signals.append(signal)

        # 4. Arbitration & Mood Update
        signals.sort(key=lambda s: s.score, reverse=True)
        winner = signals[0]
        
        # --- EHS: Update Mood based on Winner ---
        self._update_mood(winner)
        
        all_scores = {s.agent_name.value: round(s.score, 2) for s in signals}
        
        # 5. Response Generation (Inject Mood)
        if profile_update:
             context_str += f"\n[SYSTEM NOTICE: User just updated profile: {cleaned_update}]"

        bot_gender = getattr(self.config, "gender", "Neutral")
        
        # EHS: Serialize Mood for LLM
        mood_instruction = f"CURRENT MOOD: {self.current_mood} (Valence: Neg<->Pos, Arousal: Calm<->Excited). Adjust tone accordingly."

        response_text = await self.llm.generate_response(
            agent_name=winner.agent_name.value,
            user_text=message.text,
            context_str=context_str + f"\n{mood_instruction}",
            rationale=winner.rationale_short,
            bot_name=self.config.name,
            bot_gender=bot_gender,
            user_mode=preferred_mode
        )
        
        await self.memory.memorize_bot_response(
            message.user_id, 
            message.session_id, 
            response_text
        )
        
        latency = (datetime.now() - start_time).total_seconds() * 1000
        
        return CoreResponse(
            actions=[
                CoreAction(type="send_text", payload={"text": response_text})
            ],
            winning_agent=winner.agent_name,
            current_mood=self.current_mood, # <--- Return mood in response for debugging
            processing_mode=ProcessingMode.SLOW_PATH,
            internal_stats={
                "latency_ms": int(latency),
                "winner_score": winner.score,
                "winner_reason": winner.rationale_short,
                "all_scores": all_scores,
                "mood_state": str(self.current_mood)
            }
        )

    def _update_mood(self, winner_signal):
        """
        Hormonal Physics:
        NewMood = (OldMood * Inertia) + (AgentImpact * Sensitivity)
        """
        INERTIA = 0.7
        SENSITIVITY = 0.3
        
        # Define agent impacts (This could be moved to config later)
        # VAD: Valence (Good/Bad), Arousal (Calm/Excited), Dominance (Sub/Dom)
        impact_map = {
            AgentType.AMYGDALA:  MoodVector(valence=-0.8, arousal=0.9, dominance=0.8), # Fear/Aggression
            AgentType.STRIATUM:  MoodVector(valence=0.8, arousal=0.7, dominance=0.3),  # Joy/Excitement
            AgentType.SOCIAL:    MoodVector(valence=0.5, arousal=-0.2, dominance=-0.1),# Warmth/Calm
            AgentType.PREFRONTAL:MoodVector(valence=0.0, arousal=-0.5, dominance=0.1), # Cold Logic
            AgentType.INTUITION: MoodVector(valence=0.0, arousal=0.1, dominance=0.0)   # Neutral
        }
        
        impact = impact_map.get(winner_signal.agent_name, MoodVector())
        
        # Apply physics
        # Only update if the winner signal is strong enough (> 5.0)
        # Otherwise, we just drift towards neutral? Or stay inert?
        # Let's say strong signal moves us, weak signal lets us drift to baseline.
        
        force = SENSITIVITY if winner_signal.score > 4.0 else 0.05
        
        self.current_mood.valence = (self.current_mood.valence * INERTIA) + (impact.valence * force)
        self.current_mood.arousal = (self.current_mood.arousal * INERTIA) + (impact.arousal * force)
        self.current_mood.dominance = (self.current_mood.dominance * INERTIA) + (impact.dominance * force)
        
        # Clamp values -1 to 1
        for attr in ["valence", "arousal", "dominance"]:
            val = getattr(self.current_mood, attr)
            setattr(self.current_mood, attr, max(-1.0, min(1.0, val)))

    def _format_context_for_llm(self, context: Dict) -> str:
        lines = []
        
        # 0. User Profile (Crucial Identity Data)
        profile = context.get("user_profile")
        if profile:
            lines.append("USER PROFILE (Core Identity):")
            if profile.get("name"): lines.append(f"- Name: {profile['name']}")
            if profile.get("gender"): lines.append(f"- Gender: {profile['gender']}")
            if profile.get("preferred_mode"): lines.append(f"- Address Style: {profile['preferred_mode']}")
            lines.append("")

        # 1. Chat History
        if context.get("chat_history"):
            lines.append("RECENT DIALOGUE:")
            for msg in context["chat_history"]:
                role = "User" if msg["role"] == "user" else "Assistant"
                lines.append(f"{role}: {msg['content']}")
            lines.append("") 
            
        # 2. Episodes (RAG)
        if context.get("episodic_memory"):
            lines.append("PAST EPISODES (Long-term memory):")
            for ep in context["episodic_memory"]:
                lines.append(f"- {ep.get('raw_text', '')}")
        
        # 3. Facts
        if context.get("semantic_facts"):
            lines.append("KNOWN FACTS:")
            for fact in context["semantic_facts"]:
                lines.append(f"- {fact.get('subject')} {fact.get('predicate')} {fact.get('object')}")
                
        return "\n".join(lines) if lines else "No prior context."

    async def _mock_perception(self, message: IncomingMessage) -> Dict:
        await asyncio.sleep(0.05)
        return {
            "triples": [], 
            "anchors": [{"raw_text": message.text, "emotion_score": 0.5, "tags": ["auto"]}],
            "volitional_pattern": None
        }
