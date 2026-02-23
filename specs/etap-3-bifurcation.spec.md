# Этап 3: The Bifurcation Engine (Спецификация для локального ИИ-агента)

**CONTEXT FOR AI AGENT:**
You are a Senior Python Developer working on the `r-bot` project (a cognitive AI architecture). Your task is to implement "Stage 3: The Bifurcation Engine" based on Section 5 of the `attention-engagement-theory.md` document.

**STRICT RULE:** Do NOT modify database schemas directly via SQLAlchemy migrations (Alembic) or raw SQL strings. Your focus is strictly on Python code (`pipeline.py` and `hippocampus.py`).

---

## Task 1: Semantic Neighbor (Vector 1) & Zeigarnik Return (Vector 3) in `Hippocampus`
Locate `src/r_core/hippocampus.py`. We need methods to fetch candidate topics for the Bifurcation Engine.

1. **Add `get_semantic_neighbors()`:**
   Create an async method to find related but distinct topics based on the current context embedding.
   ```python
   async def get_semantic_neighbors(self, user_id: int, current_embedding: List[float], limit: int = 3) -> List[Dict]:
       """
       Finds related semantic memories using vector similarity (Cosine Distance).
       Returns items where distance is between 0.35 and 0.65 (related, but not identical).
       """
       # Implement a query to semantic_memory using vector_cosine_ops
       # Exclude memories where cosine_distance < 0.35 (too similar to current topic)
       # Return top `limit` results as dictionaries.
   ```

2. **Add `get_zeigarnik_returns()`:**
   Create an async method to find unresolved past topics.
   ```python
   async def get_zeigarnik_returns(self, user_id: int, limit: int = 3) -> List[Dict]:
       """
       Finds recent episodic memories with high prediction_error or unresolved tags.
       """
       # Query episodic_memory (or chat_history) for the user.
       # Look for items with high emotion_score or specific unresolved markers.
       # Return top `limit` results.
   ```

---

## Task 2: Emotional Anchor (Vector 2) in `MemorySystem`
Locate `src/r_core/memory.py` or where you manage affective ToM / semantic memory.

1. **Add `get_emotional_anchors()`:**
   Create an async method to fetch high-valence/high-arousal memories.
   ```python
   async def get_emotional_anchors(self, user_id: int, limit: int = 3) -> List[Dict]:
       """
       Finds semantic memories with high affective intensity (sentiment > 0.7 or < -0.7).
       """
       # Query semantic_memory where sentiment JSON contains high arousal/valence.
       # Return top `limit` results.
   ```

---

## Task 3: The Bifurcation Arbitration in `Pipeline`
Locate `src/r_core/pipeline.py`. Integrate the 3 vectors when LC mode is "tonic".

1. **Calculate Bifurcation Vectors:**
   Inside `process_message`, right after determining `lc_mode = "tonic"`, trigger the Bifurcation Engine.
   ```python
   bifurcation_candidates = []
   if lc_mode == "tonic":
       print("[Bifurcation Engine] Tonic LC detected. Generating topic switch hypotheses...")
       
       # 1. Fetch vectors concurrently
       semantic_candidates, zeigarnik_candidates, emotional_candidates = await asyncio.gather(
           self.hippocampus.get_semantic_neighbors(message.user_id, current_embedding),
           self.hippocampus.get_zeigarnik_returns(message.user_id),
           self.memory.get_emotional_anchors(message.user_id)
       )
       
       # 2. Score candidates
       # Semantic: weight 0.5 (based on similarity)
       # Emotional: weight 0.3 (based on intensity)
       # Zeigarnik: weight 0.2 (based on recency)
       
       # Combine all valid candidates into a sorted list: `bifurcation_candidates`
       # Select the top candidate as the `predicted_bifurcation_topic`
   ```

2. **Inject Bifurcation Directive into LLM Prompt:**
   If a `predicted_bifurcation_topic` exists, add a directive to the Prefrontal agent's rationale or the `final_style_instructions` for the LLM:
   ```python
   bifurcation_instruction = ""
   if predicted_bifurcation_topic:
       bifurcation_instruction = (
           f"\\nPROACTIVE MIRRORING (Topic Switch Recommended):\\n"
           f"- The user's engagement with the current topic is depleted.\\n"
           f"- Gently pivot the conversation towards: {predicted_bifurcation_topic}\\n"
       )
       final_style_instructions += bifurcation_instruction
   ```

3. **Metrics Logging:**
   Log the bifurcation event in `internal_stats`:
   - `"bifurcation_triggered"`: `True` (if tonic)
   - `"bifurcation_target"`: The chosen topic string.

**END OF CONTEXT.**