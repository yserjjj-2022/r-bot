# Causal Volitional Model Architecture

## 1. Overview
This document defines the architecture for the "Causal Volitional Model" — a system that reconstructs behavioral logic from text, identifying causal links between Context (COM-B) and the 8-Step Volitional Cycle.

The goal is to move from simple sequence labeling to a SEM-like (Structural Equation Modeling) graph structure that can be aggregated to find behavioral patterns.

## 2. Data Model

### 2.1. The Episode (Unit of Analysis)
An episode represents a single behavioral instance extracted from text.

```json
{
  "episode_id": "uuid",
  "user_id": "uuid",
  "source_text": "Original text chunk...",
  "relevance_score": 0.85, // Similarity to research domain
  "vector_embedding": [0.12, -0.45, ...], // Embedding of the Context for clustering
  "graph": {
    "spine": [], // The 8 steps
    "context_factors": [] // The modifiers
  }
}
```

### 2.2. The Spine (Process Nodes)
These are the standard 8 steps of the Synthetic Model v2.0.

```json
{
  "id": "node_id",
  "step_index": 3, // 1-8
  "step_type": "DOUBLE_ACTIVATION", // Enum: CONTEXT, TRIGGER, ..., REFLECTION
  "sub_type": "IMPULSE", // Specific branch (Impulse vs Goal)
  "description": "Natural language description of the node",
  "embedding": [...] // Vector representation of the node content
}
```

### 2.3. The Context Factors (Modifiers)
These are the observable variables that influence the process.

```json
{
  "id": "factor_id",
  "target_node_id": "node_id", // Which step it influences
  "com_b_category": "OPPORTUNITY_SOCIAL", // Capability, Opportunity, Motivation
  "description": "Peer pressure from colleagues",
  "influence_direction": "BARRIER", // FACILITATOR (+) or BARRIER (-)
  "influence_strength": 0.8 // 0.0 to 1.0 (estimated impact)
}
```

## 3. Processing Pipeline

### Stage 1: Extraction (LLM)
*   **Input**: Raw text chunk + Research Domain definition.
*   **Prompt Logic**:
    1.  Identify the 8 steps of the Volitional Cycle.
    2.  Identify "Context Factors" (facts about state, environment, skills).
    3.  Link Factors to Steps: "Did this factor help or hinder this step?"
*   **Output**: JSON Graph structure.

### Stage 2: Vectorization & Relevance (Embeddings)
*   **Action**: Generate embeddings for:
    1.  `Context_Summary`: A text combining all Context Factors.
    2.  `Action_Summary`: The final outcome.
*   **Relevance Check**: Calculate Cosine Similarity(`Context_Summary`, `Research_Domain_Vector`).
    *   If < Threshold: Tag as "Low Relevance" (noise).
    *   If > Threshold: Tag as "Core Data".

### Stage 3: Aggregation (Pattern Mining)
*   **Input**: List of Episodes for User X.
*   **Clustering**: Group episodes by their `Context_Summary` vector (e.g., "High Stress" cluster vs "Relaxed" cluster).
*   **Causal Synthesis**: Within each cluster, calculate:
    *   *Bottleneck Frequency*: Which step fails most often?
    *   *Factor Impact*: Which COM-B category has the highest sum of `influence_strength` on the Outcome?

## 4. Storage Strategy (Vector DB + Relational)
We need a hybrid approach:
*   **Relational (Postgres/SQL)**: Stores the rigid graph structure (Nodes, Edges, Steps) for UI rendering and deterministic logic.
*   **Vector (Pinecone/Chroma/PGVector)**: Stores embeddings of Contexts and Nodes.
    *   Allows semantic search: "Find all episodes where *Social Pressure* caused *Inhibition Failure*."
    *   Allows clustering: "Group users with similar motivational triggers."

## 5. Implementation Plan
1.  **Define Pydantic Models**: Strict typing for the JSON structure.
2.  **Develop Extraction Prompt**: Few-shot prompting with the new SEM-like schema.
3.  **Vector Store Integration**: Add embedding generation for context nodes.
4.  **Aggregation Logic**: Python script to compute "Average Causal Path" for a cluster.
