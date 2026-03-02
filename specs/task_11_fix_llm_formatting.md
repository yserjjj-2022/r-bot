# Task 11: Fix LLM Formatting & Diminutives Ignore Issue

## Context
During testing with the "Lyutik" character (and other personalities), the bot continues to generate roleplay action descriptions in italics/asterisks (e.g., *улыбается*, *смеется и подмигивает*) and uses excessive diminutives (e.g., "Сереженька") despite rules added to the LLM prompt.

**Root Cause:**
The `FORMATTING AND ADDRESSING RULES` block in `src/r_core/infrastructure/llm.py` (`generate_response`) is placed too early in the `system_prompt` construction. Because the `context_str` (conversation history) and `affective_context` are appended *after* these rules, the LLM suffers from "lost in the middle/beginning" syndrome. It sees previous messages in the history containing asterisks and diminutives, and prioritizes that context over the initial formatting instructions.

## Acceptance Criteria
1. The formatting rules must be moved to the **very end** of the system prompt, right before the JSON `--- PREDICTIVE PROCESSING ---` instructions.
2. The phrasing of the formatting rules must be made more aggressive to override the conversation history inertia.
3. The bot must strictly stop using action descriptions (asterisks/italics) and excessive diminutives.

## Implementation Steps

### 1. Update `src/r_core/infrastructure/llm.py`
Locate the `generate_response` method.

**Remove** the `formatting_rules` string definition from the top:
```python
# REMOVE THIS BLOCK FROM THE TOP:
# === 2. FORMATTING AND ADDRESSING RULES ===
# formatting_rules = (
#     "COMMUNICATION GUIDELINES:\\n"
#     "1. NO ACTION DESCRIPTIONS: NEVER use asterisks or text to describe actions...\\n"
#     "2. NO EXCESSIVE DIMINUTIVES: Avoid overly familiar or sweet name forms...\\n"
# )
```

**Modify** the `system_prompt` assembly. It should look exactly like this:

```python
        # === 3. FINAL SYSTEM PROMPT ===
        system_prompt = (
            f"{identity_block}\\n"
            f"{address_block}\\n"
            f"CURRENT FUNCTIONAL STATE (Active Agent): {system_persona}\\n"
            "INSTRUCTION: Reply to the user in the SAME LANGUAGE as they used (Russian/English/etc).\\n"
            "GRAMMAR: Use correct gender endings for yourself (Male/Female/Neutral) consistent with your IDENTITY.\\n\\n"
            "--- CONVERSATION MEMORY ---\\n"
            f"{context_str}\\n\\n"
        )

        if affective_context:
            system_prompt += (
                "--- AFFECTIVE CONTEXT (User's Emotional Relations) ---\\n"
                f"{affective_context}\\n\\n"
            )

        # === 4. INJECT AGGRESSIVE FORMATTING RULES AT THE END ===
        system_prompt += (
            "--- STRICT FORMATTING RULES (CRITICAL) ---\\n"
            "1. NO ROLEPLAY ACTIONS: You MUST NOT generate any actions in asterisks, parentheses, or italics (e.g., *smiles*, (laughs), смеется, подмигивает). Generate ONLY spoken text.\\n"
            "2. NO DIMINUTIVES: NEVER use sweet or diminutive name forms (like 'Сереженька', 'Сашенька'). Use the normal name or 'дружище'.\\n"
            "IF YOU VIOLATE THESE RULES, THE SYSTEM WILL PENALIZE THE OUTPUT.\\n\\n"
        )

        system_prompt += (
            "--- INTERNAL DIRECTIVES (Hidden from User) ---\\n"
            f"{style_instructions}\\n"
            f"MOTIVATION: {rationale}\\n\\n"
            "--- PREDICTIVE PROCESSING ---\\n"
            "You MUST output JSON with two fields:\\n"
            "1. 'reply': Your actual response to the user.\\n"
            "2. 'predicted_user_reaction': PREDICT the user's NEXT specific response to 'reply'.\\n"
            "   IMPORTANT: Do NOT describe the action (e.g. 'User will thank me').\\n"
            "   INSTEAD: Write the LITERAL FIRST-PERSON PHRASE you expect them to say (e.g. 'Спасибо, это помогло!' or 'Why is that?').\\n"
            "   This is used for vector similarity comparison."
        )
```

### 2. Verify
Run the Streamlit app. Clear the chat history to flush out the old "bad" messages. Try interacting with Lyutik — the asterisks and diminutives should be completely gone.