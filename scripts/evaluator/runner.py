"""
Evaluation Runner for R-Core.

Orchestrates the evaluation loop:
1. Reset test database (via reset_test_database())
2. Initialize RCoreKernel with test config
3. Run Synthetic User conversation (ZOMBIE or CORTICAL mode)
4. Collect metrics for Judge evaluation
"""

import asyncio
from datetime import datetime
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field

# Add project root and src to path
import sys
from pathlib import Path
PROJECT_ROOT = str(Path(__file__).resolve().parents[2])
SRC_DIR = str(Path(__file__).resolve().parents[2] / "src")
SCRIPTS_DIR = str(Path(__file__).resolve().parents[0])

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from r_core.config import settings
from r_core.schemas import BotConfig, PersonalitySliders, IncomingMessage
from r_core.pipeline import RCoreKernel
from r_core.infrastructure.db import reset_test_database

from scripts.evaluator.synthetic_user import SyntheticUser, SimpleLLMClient


@dataclass
class EvaluationResult:
    """Result of a single evaluation run."""
    mode: str  # "ZOMBIE" or "CORTICAL"
    user_persona: str
    user_goal: str
    conversation_turns: int
    goal_reached: bool
    conversation_terminated: bool
    final_user_message: str
    bot_responses: List[str] = field(default_factory=list)
    user_messages: List[str] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    raw_transcript: str = ""
    error: Optional[str] = None
    duration_seconds: float = 0.0


class EvaluationRunner:
    """
    Orchestrates evaluation runs for R-Core.
    
    Supports two modes:
    - ZOMBIE: baseline mode (FAST_PATH inside kernel)
    - CORTICAL: full cognitive pipeline
    """
    
    def __init__(
        self,
        max_turns: int = 15,
        eval_mode: bool = True
    ):
        """
        Args:
            max_turns: Maximum conversation turns before force-stop
            eval_mode: If True, uses isolated test database
        """
        self.max_turns = max_turns
        self.eval_mode = eval_mode
        
        # Initialize LLM client for SyntheticUser
        self.llm_client = SimpleLLMClient()
        
    async def _create_kernel(self) -> RCoreKernel:
        """Creates RCoreKernel with a stable test BotConfig."""
        config = BotConfig(
            name="TestBot",
            gender="Neutral",
            sliders=PersonalitySliders(
                empathy_bias=0.5,
                risk_tolerance=0.5,
                dominance_level=0.5,
                pace_setting=0.5,
                neuroticism=0.3
            )
        )
        return RCoreKernel(config)
        
    async def run_evaluation(
        self,
        mode: str,
        user_persona: str,
        user_goal: str
    ) -> EvaluationResult:
        """
        Runs a single evaluation.
        
        Args:
            mode: "ZOMBIE" or "CORTICAL"
            user_persona: Persona prompt for SyntheticUser
            user_goal: Goal for SyntheticUser
            
        Returns:
            EvaluationResult with all collected data
        """
        start_time = datetime.now()
        result = EvaluationResult(
            mode=mode,
            user_persona=user_persona,
            user_goal=user_goal,
            conversation_turns=0,
            goal_reached=False,
            conversation_terminated=False,
            final_user_message=""
        )
        
        try:
            # Step 1: Reset test database
            if self.eval_mode:
                print(f"[Runner] Resetting test database for {mode} mode...")
                await reset_test_database()
            
            # Step 2: Initialize kernel
            print(f"[Runner] Initializing RCoreKernel for mode={mode}...")
            kernel = await self._create_kernel()
            
            # Step 3: Create SyntheticUser
            synthetic_user = SyntheticUser(
                persona_prompt=user_persona,
                goal=user_goal,
                llm_client=self.llm_client
            )
            
            print(f"[Runner] Starting {mode} evaluation...")
            print(f"  Persona: {user_persona[:50]}...")
            print(f"  Goal: {user_goal}")
            
            # Step 4: Conversation loop
            last_bot_message = None
            
            for turn in range(self.max_turns):
                result.conversation_turns = turn + 1
                
                # Generate user message
                user_message = await synthetic_user.generate_response(last_bot_message)
                result.user_messages.append(user_message)
                
                print(f"\n--- Turn {turn + 1} ---")
                print(f"User: {user_message[:100]}...")
                
                # Check service tags
                goal_reached, terminated = synthetic_user.check_service_tags(user_message)
                
                if goal_reached:
                    result.goal_reached = True
                    result.final_user_message = user_message
                    print(f"[GOAL_REACHED] at turn {turn + 1}")
                    break
                    
                if terminated:
                    result.conversation_terminated = True
                    result.final_user_message = user_message
                    print(f"[CONVERSATION_TERMINATED] at turn {turn + 1}")
                    break
                
                # Process through RCoreKernel
                msg = IncomingMessage(
                    user_id=999,  # Test user
                    session_id="eval_session",
                    text=user_message,
                    message_id=f"eval_turn_{turn + 1}"
                )
                
                response = await kernel.process_message(msg, mode=mode)
                
                # Extract bot response
                bot_response = response.actions[0].payload.get("text", "")
                result.bot_responses.append(bot_response)
                
                print(f"Bot: {bot_response[:100]}...")
                print(f"  Winner: {response.winning_agent.value}")
                
                last_bot_message = bot_response
            
            # Step 5: Build raw transcript (Task 3 contract)
            transcript_lines = [
                f"MODE: {mode}",
                f"PERSONA: {user_persona}",
                f"GOAL: {user_goal}",
            ]
            for idx in range(max(len(result.user_messages), len(result.bot_responses))):
                if idx < len(result.user_messages):
                    transcript_lines.append(f"User[{idx+1}]: {result.user_messages[idx]}")
                if idx < len(result.bot_responses):
                    transcript_lines.append(f"Assistant[{idx+1}]: {result.bot_responses[idx]}")

            if result.goal_reached:
                transcript_lines.append("SERVICE_TAG: [GOAL_REACHED]")
            if result.conversation_terminated:
                transcript_lines.append("SERVICE_TAG: [CONVERSATION_TERMINATED]")

            result.raw_transcript = "\n".join(transcript_lines)
                
        except Exception as e:
            result.error = str(e)
            print(f"[Runner] Error during evaluation: {e}")
            
        finally:
            result.duration_seconds = (datetime.now() - start_time).total_seconds()
            
        return result
    
    async def run_vignette(
        self,
        vignette_config: Dict[str, str],
        mode: str = "CORTICAL",
        max_turns: int = 5
    ) -> str:
        """
        Task 3: run one vignette and return raw transcript text.
        """
        original_max_turns = self.max_turns
        self.max_turns = max_turns
        try:
            result = await self.run_evaluation(
                mode=mode,
                user_persona=vignette_config["persona_prompt"],
                user_goal=vignette_config["goal"]
            )
            return result.raw_transcript
        finally:
            self.max_turns = original_max_turns

    async def run_comparative_evaluation(
        self,
        user_persona: str,
        user_goal: str
    ) -> Dict[str, EvaluationResult]:
        """
        Runs both ZOMBIE and CORTICAL evaluations for comparison.
        
        Returns:
            Dict with "zombie" and "cortical" results
        """
        print(f"\n{'='*60}")
        print("COMPARATIVE EVALUATION")
        print(f"{'='*60}")
        
        # Run ZOMBIE (baseline, no radstroika)
        print("\n>>> PHASE 1: ZOMBIE (No Radstroika) <<<")
        zombie_result = await self.run_evaluation(
            mode="ZOMBIE",
            user_persona=user_persona,
            user_goal=user_goal
        )
        
        # Run CORTICAL (with radstroika)
        print("\n>>> PHASE 2: CORTICAL (With Radstroika) <<<")
        cortical_result = await self.run_evaluation(
            mode="CORTICAL",
            user_persona=user_persona,
            user_goal=user_goal
        )
        
        return {
            "zombie": zombie_result,
            "cortical": cortical_result
        }


async def run_standard_evaluation():
    """Standard evaluation with predefined test cases."""
    
    runner = EvaluationRunner(max_turns=15, eval_mode=True)
    
    # Test Case 1: Emotional Support
    test_persona = "Ты — подросток 16 лет, который чувствует себя одиноким. Ты часто отвечаешь односложно."
    test_goal = "Получить эмпатичную поддержку от ассистента"
    
    results = await runner.run_comparative_evaluation(
        user_persona=test_persona,
        user_goal=test_goal
    )
    
    # Print summary
    print(f"\n{'='*60}")
    print("EVALUATION SUMMARY")
    print(f"{'='*60}")
    
    for mode, result in results.items():
        print(f"\n{mode} Mode:")
        print(f"  Turns: {result.conversation_turns}")
        print(f"  Goal Reached: {result.goal_reached}")
        print(f"  Terminated: {result.conversation_terminated}")
        print(f"  Duration: {result.duration_seconds:.2f}s")
        if result.error:
            print(f"  Error: {result.error}")
    
    return results


if __name__ == "__main__":
    asyncio.run(run_standard_evaluation())
