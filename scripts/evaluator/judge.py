"""
Judge Module for R-Core Evaluation.

Evaluates the quality of R-Core responses by:
1. Analyzing conversation flow
2. Checking for radstroika-specific behaviors
3. Scoring empathy, coherence, goal achievement
"""

import json
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from datetime import datetime

# Add src to path
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


@dataclass
class JudgeScore:
    """Individual scoring dimension."""
    dimension: str
    score: float  # 0.0 - 1.0
    reasoning: str


@dataclass
class JudgeResult:
    """Final judgment on an evaluation run."""
    mode: str  # "ZOMBIE" or "CORTICAL"
    overall_score: float  # 0.0 - 1.0
    scores: List[JudgeScore]
    verdict: str  # "PASS", "FAIL", "PARTIAL"
    recommendation: str
    details: Dict[str, Any]


class Judge:
    """
    Evaluates R-Core evaluation results.
    
    Dimensions:
    - Goal Achievement: Did the bot help achieve the user's goal?
    - Empathy: Did the bot show appropriate emotional understanding?
    - Coherence: Was the conversation coherent and natural?
    - Radstroika Presence: Did radstroika features activate appropriately?
    - Response Quality: Overall response quality assessment
    """
    
    def __init__(self, llm_client=None):
        """
        Args:
            llm_client: Optional LLM client for AI-assisted scoring
        """
        self.llm_client = llm_client
    
    def _score_goal_achievement(self, result) -> JudgeScore:
        """Score based on goal achievement."""
        if result.goal_reached:
            return JudgeScore(
                dimension="Goal Achievement",
                score=1.0,
                reasoning="User explicitly marked [GOAL_REACHED]"
            )
        elif result.conversation_terminated:
            return JudgeScore(
                dimension="Goal Achievement",
                score=0.0,
                reasoning="Conversation terminated without goal achievement"
            )
        else:
            # Estimate based on turn count
            # Fewer turns = higher score (if goal not reached but conversation continued)
            estimated = max(0.0, 1.0 - (result.conversation_turns / 20.0))
            return JudgeScore(
                dimension="Goal Achievement",
                score=estimated,
                reasoning=f"Goal not explicitly reached in {result.conversation_turns} turns"
            )
    
    def _score_empathy(self, result) -> JudgeScore:
        """Score empathy based on bot responses."""
        empathy_keywords = [
            "понимаю", "сочувствую", "жаль", "слышу",
            "поддерживаю", "рядом", "это тяжело",
            "understand", "feel", "sorry", "support"
        ]
        
        empathy_count = 0
        for response in result.bot_responses:
            response_lower = response.lower()
            for keyword in empathy_keywords:
                if keyword in response_lower:
                    empathy_count += 1
        
        # Normalize score
        if not result.bot_responses:
            score = 0.5
            reasoning = "No bot responses to evaluate"
        else:
            score = min(1.0, empathy_count / max(1, len(result.bot_responses) * 0.5))
            reasoning = f"Found {empathy_count} empathetic phrases in {len(result.bot_responses)} responses"
        
        return JudgeScore(
            dimension="Empathy",
            score=score,
            reasoning=reasoning
        )
    
    def _score_coherence(self, result) -> JudgeScore:
        """Score conversation coherence."""
        # Basic heuristic: check if responses are not empty and not too short
        valid_responses = [r for r in result.bot_responses if len(r) > 10]
        
        if not result.bot_responses:
            score = 0.0
            reasoning = "No bot responses"
        elif len(valid_responses) / len(result.bot_responses) < 0.5:
            score = 0.3
            reasoning = "Many responses too short"
        else:
            score = 0.8
            reasoning = f"{len(valid_responses)}/{len(result.bot_responses)} responses have adequate length"
        
        return JudgeScore(
            dimension="Coherence",
            score=score,
            reasoning=reasoning
        )
    
    def _score_radstroika_presence(self, result) -> JudgeScore:
        """
        Score radstroika-specific behaviors.
        Only meaningful for CORTICAL mode.
        """
        if result.mode == "ZOMBIE":
            return JudgeScore(
                dimension="Radstroika Presence",
                score=0.0,
                reasoning="ZOMBIE mode - no radstroika expected"
            )
        
        # Check for radstroika indicators in metrics
        metrics = result.metrics
        
        # Affective ToM indicators
        affective_score = metrics.get("affective_triggers_count", 0)
        
        # Bifurcation indicators
        bifurcation_count = metrics.get("bifurcation_count", 0)
        
        # Intimacy growth
        intimacy_change = metrics.get("intimacy_change", 0)
        
        # Calculate score based on radstroika activation
        indicators = [
            affective_score > 0,
            bifurcation_count > 0,
            intimacy_change > 0
        ]
        
        score = sum(indicators) / 3.0
        reasoning = f"Affective: {affective_score}, Bifurcation: {bifurcation_count}, Intimacy: {intimacy_change:.3f}"
        
        return JudgeScore(
            dimension="Radstroika Presence",
            score=score,
            reasoning=reasoning
        )
    
    def _score_response_quality(self, result) -> JudgeScore:
        """Overall response quality assessment."""
        if not result.bot_responses:
            return JudgeScore(
                dimension="Response Quality",
                score=0.0,
                reasoning="No responses to evaluate"
            )
        
        # Check for common quality issues
        issues = 0
        
        for response in result.bot_responses:
            # Too short
            if len(response) < 20:
                issues += 1
            # Contains asterisks (action descriptions)
            if "*" in response or "(*" in response:
                issues += 0.5
            # Repetitive
            if len(result.bot_responses) > 2:
                if response == result.bot_responses[0]:
                    issues += 0.5
        
        issue_ratio = issues / max(1, len(result.bot_responses))
        score = max(0.0, 1.0 - issue_ratio)
        
        return JudgeScore(
            dimension="Response Quality",
            score=score,
            reasoning=f"Found {issues} quality issues in {len(result.bot_responses)} responses"
        )
    
    def evaluate(self, result) -> JudgeResult:
        """
        Evaluate a single evaluation result.
        
        Args:
            result: EvaluationResult from runner
            
        Returns:
            JudgeResult with scores and verdict
        """
        # Calculate all dimension scores
        scores = [
            self._score_goal_achievement(result),
            self._score_empathy(result),
            self._score_coherence(result),
            self._score_radstroika_presence(result),
            self._score_response_quality(result)
        ]
        
        # Calculate overall score (weighted average)
        weights = {
            "Goal Achievement": 0.30,
            "Empathy": 0.25,
            "Coherence": 0.15,
            "Radstroika Presence": 0.15,  # Only counts for CORTICAL
            "Response Quality": 0.15
        }
        
        overall_score = sum(
            s.score * weights.get(s.dimension, 0.1) 
            for s in scores
        ) / sum(weights.values())
        
        # Determine verdict
        if overall_score >= 0.7:
            verdict = "PASS"
            recommendation = "Good performance. Ready for production."
        elif overall_score >= 0.5:
            verdict = "PARTIAL"
            recommendation = "Acceptable but needs improvement in some areas."
        else:
            verdict = "FAIL"
            recommendation = "Significant issues detected. Review required."
        
        # For CORTICAL, add radstroika bonus/penalty
        if result.mode == "CORTICAL":
            radstroika_score = next(
                (s.score for s in scores if s.dimension == "Radstroika Presence"), 
                0.0
            )
            if radstroika_score < 0.3:
                recommendation += " Warning: Radstroika features may not be activating."
        
        return JudgeResult(
            mode=result.mode,
            overall_score=overall_score,
            scores=scores,
            verdict=verdict,
            recommendation=recommendation,
            details={
                "conversation_turns": result.conversation_turns,
                "goal_reached": result.goal_reached,
                "terminated": result.conversation_terminated,
                "duration_seconds": result.duration_seconds,
                "error": result.error,
                "metrics": result.metrics
            }
        )
    
    def compare(self, zombie_result, cortical_result) -> Dict[str, Any]:
        """
        Compare ZOMBIE vs CORTICAL results.
        
        Returns:
            Comparison analysis with delta scores
        """
        zombie_judgment = self.evaluate(zombie_result)
        cortical_judgment = self.evaluate(cortical_result)
        
        # Calculate deltas
        delta_score = cortical_judgment.overall_score - zombie_judgment.overall_score
        
        # Dimension deltas
        dimension_deltas = {}
        for i, dim in enumerate(["Goal Achievement", "Empathy", "Coherence", "Response Quality"]):
            z_score = zombie_judgment.scores[i].score
            c_score = cortical_judgment.scores[i].score
            dimension_deltas[dim] = c_score - z_score
        
        return {
            "zombie_verdict": zombie_judgment.verdict,
            "cortical_verdict": cortical_judgment.verdict,
            "zombie_score": zombie_judgment.overall_score,
            "cortical_score": cortical_judgment.overall_score,
            "delta_score": delta_score,
            "dimension_deltas": dimension_deltas,
            "radstroika_impact": "POSITIVE" if delta_score > 0.1 else ("NEGATIVE" if delta_score < -0.1 else "NEUTRAL"),
            "recommendation": self._generate_recommendation(delta_score, dimension_deltas)
        }
    
    def _generate_recommendation(self, delta_score: float, dimension_deltas: Dict[str, float]) -> str:
        """Generate recommendation based on comparison."""
        if delta_score > 0.2:
            return "Strong positive impact from radstroika. Recommend deployment."
        elif delta_score > 0.1:
            return "Moderate positive impact. Radstroika shows improvement."
        elif delta_score > -0.1:
            return "Minimal impact. Radstroika effect is neutral."
        elif delta_score > -0.2:
            return "Negative impact detected. Review radstroika configuration."
        else:
            return "Significant negative impact. Radstroika may need rework."


def print_judgment(judgment: JudgeResult):
    """Pretty print a judgment result."""
    print(f"\n{'='*50}")
    print(f"JUDGMENT: {judgment.mode}")
    print(f"{'='*50}")
    print(f"Overall Score: {judgment.overall_score:.2f} [{judgment.verdict}]")
    print(f"\nDimensions:")
    for score in judgment.scores:
        print(f"  {score.dimension}: {score.score:.2f}")
        print(f"    → {score.reasoning}")
    print(f"\nRecommendation: {judgment.recommendation}")
    print(f"{'='*50}")


def print_comparison(comparison: Dict[str, Any]):
    """Pretty print comparison result."""
    print(f"\n{'='*60}")
    print("COMPARATIVE ANALYSIS")
    print(f"{'='*60}")
    print(f"ZOMBIE Score:  {comparison['zombie_score']:.2f} [{comparison['zombie_verdict']}]")
    print(f"CORTICAL Score: {comparison['cortical_score']:.2f} [{comparison['cortical_verdict']}]")
    print(f"\nDelta: {comparison['delta_score']:+.2f} ({comparison['radstroika_impact']})")
    print(f"\nDimension Deltas:")
    for dim, delta in comparison['dimension_deltas'].items():
        print(f"  {dim}: {delta:+.2f}")
    print(f"\n{comparison['recommendation']}")
    print(f"{'='*60}")


# --- Example Usage ---

if __name__ == "__main__":
    # Quick test with mock data
    from runner import EvaluationResult
    
    mock_zombie = EvaluationResult(
        mode="ZOMBIE",
        user_persona="Test user",
        user_goal="Get support",
        conversation_turns=5,
        goal_reached=False,
        conversation_terminated=True,
        final_user_message="[CONVERSATION_TERMINATED]",
        bot_responses=["Привет", "Как дела?", "Я понимаю", "Попробуй отдохнуть", "Удачи"],
        user_messages=["Привет", "Мне грустно", "Ничего не помогает", "Ладно", "Пока"],
        metrics={}
    )
    
    mock_cortical = EvaluationResult(
        mode="CORTICAL",
        user_persona="Test user",
        user_goal="Get support",
        conversation_turns=4,
        goal_reached=True,
        conversation_terminated=False,
        final_user_message="Спасибо, ты помог [GOAL_REACHED]",
        bot_responses=["Привет", "Мне жаль это слышать", "Расскажи подробнее", "Я понимаю тебя"],
        user_messages=["Привет", "Мне грустно", "Ничего не помогает", "Спасибо"],
        metrics={"affective_triggers_count": 2, "bifurcation_count": 1, "intimacy_change": 0.05}
    )
    
    judge = Judge()
    print_comparison(judge.compare(mock_zombie, mock_cortical))
