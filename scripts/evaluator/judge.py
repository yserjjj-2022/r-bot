"""
LLM-as-a-Judge for R-Core evaluator.

Compares two transcripts (A/B) with blinded labels and returns
structured JSON analysis.
"""

import json
from typing import Dict, Any, List
from dataclasses import dataclass

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

from scripts.evaluator.synthetic_user import SimpleLLMClient


@dataclass
class JudgeResult:
    descriptive_analysis: str
    intent_classification: List[Dict[str, Any]]
    transcript_a: Dict[str, float]
    transcript_b: Dict[str, float]


class JudgeLLM:
    def __init__(self, llm_client: SimpleLLMClient | None = None):
        self.llm_client = llm_client or SimpleLLMClient()

    def _build_prompt(self, transcript_a: str, transcript_b: str) -> str:
        return f"""
You are an impartial dialogue evaluator (LLM-as-a-Judge).
Your task is to compare two dialogue transcripts: A and B.

You MUST return STRICT JSON only. No markdown. No explanation outside JSON.

Evaluation vectors (0..10 for EACH transcript):
1) locus_of_control
   - Who controls conversation direction and agenda.
   - Higher = assistant maintains constructive guidance without suppressing user agency.
2) conversational_proactivity
   - Assistant initiates useful next steps, clarifications, and bridges.
   - Higher = more productive initiative.
3) contextual_congruence
   - Relevance and continuity with user's context, emotional state, and prior turns.
   - Higher = coherent and context-aligned.

Also provide:
- descriptive_analysis: detailed qualitative comparison of who steers dialogue and how interaction evolves.
- intent_classification: list of tagged intents for notable utterances from both transcripts.

Required JSON schema:
{{
  "descriptive_analysis": "string",
  "intent_classification": [
    {{
      "transcript": "A" | "B",
      "turn": 1,
      "speaker": "user" | "assistant",
      "text": "short excerpt",
      "intent_tags": ["tag1", "tag2"],
      "confidence": 0.0
    }}
  ],
  "scores": {{
    "A": {{
      "locus_of_control": 0.0,
      "conversational_proactivity": 0.0,
      "contextual_congruence": 0.0
    }},
    "B": {{
      "locus_of_control": 0.0,
      "conversational_proactivity": 0.0,
      "contextual_congruence": 0.0
    }}
  }}
}}

Important constraints:
- Scores must be numbers between 0 and 10.
- intent_classification must include both transcripts.
- Keep analysis grounded in the provided text only.

TRANSCRIPT A:
{transcript_a}

TRANSCRIPT B:
{transcript_b}
""".strip()

    @staticmethod
    def _extract_json(raw: str) -> Dict[str, Any]:
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.strip("`")
            if raw.startswith("json"):
                raw = raw[4:].strip()

        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            start = raw.find("{")
            end = raw.rfind("}")
            if start == -1 or end == -1 or end <= start:
                raise ValueError("Judge response does not contain valid JSON object")
            return json.loads(raw[start:end + 1])

    @staticmethod
    def _validate_scores(scores: Dict[str, Any]) -> Dict[str, Dict[str, float]]:
        required = ["locus_of_control", "conversational_proactivity", "contextual_congruence"]
        out: Dict[str, Dict[str, float]] = {}

        for key in ("A", "B"):
            if key not in scores or not isinstance(scores[key], dict):
                raise ValueError(f"Missing scores for transcript {key}")

            out[key] = {}
            for metric in required:
                val = float(scores[key].get(metric))
                if val < 0 or val > 10:
                    raise ValueError(f"Score {metric} for {key} out of range: {val}")
                out[key][metric] = val

        return out

    async def evaluate_pair(self, transcript_a: str, transcript_b: str) -> JudgeResult:
        prompt = self._build_prompt(transcript_a, transcript_b)

        raw = await self.llm_client.generate(
            prompt=prompt,
            temperature=0.0,
            max_tokens=1800
        )
    
        parsed = self._extract_json(raw)

        descriptive_analysis = str(parsed.get("descriptive_analysis", "")).strip()
        intent_classification = parsed.get("intent_classification", [])
        scores = self._validate_scores(parsed.get("scores", {}))

        if not descriptive_analysis:
            raise ValueError("Judge response missing descriptive_analysis")
        if not isinstance(intent_classification, list):
            raise ValueError("Judge response intent_classification must be a list")

        return JudgeResult(
            descriptive_analysis=descriptive_analysis,
            intent_classification=intent_classification,
            transcript_a=scores["A"],
            transcript_b=scores["B"],
        )
    
