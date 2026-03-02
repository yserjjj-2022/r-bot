# Task 13: Prompt History Sanitization (Anti-Echo Mechanism)

## Context
Even with strict negative formatting rules in the LLM prompt (Task 11), the bot may still occasionally hallucinate roleplay actions (e.g., `*smiles*`) or use forbidden diminutives (e.g., `Сереженька`). 

**Root Cause:**
LLMs are highly susceptible to "few-shot echoing". If the `chat_history` injected into the prompt contains previous bot messages with asterisks or diminutives, the LLM will subconsciously mirror that style, overriding the system prompt instructions. We cannot simply delete this history from the database, as it destroys the integrity of the episodic memory and session continuity.

**Solution:**
We need an interceptor that "scrubs" or "sanitizes" the bot's past messages *only* when formatting the context string for the LLM prompt. The raw messages in the database remain untouched.

## Acceptance Criteria
1. Implement a `sanitize_history_message(text: str) -> str` utility function.
2. The function must remove any text enclosed in asterisks (e.g., `*smiles*`, `*смеется и подмигивает*`).
3. The function must remove any text enclosed in parentheses if it looks like an action (e.g., `(улыбается)`).
4. The function must replace a known list of toxic diminutives (e.g., `Сереженька`, `Сашенька`) with neutral alternatives (e.g., `дружище` or remove them entirely).
5. Apply this function in `pipeline.py` (or `memory.py`) right before the `chat_history` is concatenated into the `context_str` for the LLM prompt.
6. The database (`chat_history` table) must NOT be modified.

## Implementation Steps

### 1. Create the Sanitizer Utility
In `src/r_core/utils.py` (or similar), add:

```python
import re

def sanitize_bot_history(text: str) -> str:
    \"\"\"
    Removes roleplay formatting and forbidden diminutives from bot messages 
    before injecting them into the LLM prompt context.
    \"\"\"
    if not text:
        return text
        
    # 1. Remove anything between asterisks (e.g., *улыбается*)
    text = re.sub(r'\\*.*?\\*', '', text)
    
    # 2. Remove common action verbs written in italics or loose formatting
    # Often LLMs might output just "смеется " without asterisks if previously conditioned
    actions_to_remove = [
        \"смеется\", \"улыбается\", \"подмигивает\", \"вздыхает\", 
        \"кивает\", \"смеется и подмигивает\", \"довольно улыбается\"
    ]
    for action in actions_to_remove:
        # Match standalone actions (case insensitive)
        pattern = re.compile(rf'\\b{action}\\b', re.IGNORECASE)
        text = pattern.sub('', text)
        
    # 3. Replace/Remove diminutives
    diminutives = [\"Сереженька\", \"Сережа\", \"Сашенька\", \"Сергеюшка\"]
    for dim in diminutives:
        pattern = re.compile(rf'\\b{dim}\\b', re.IGNORECASE)
        text = pattern.sub('дружище', text) # Or just '' to remove
        
    # Clean up double spaces left by replacements
    text = re.sub(r'\\s+', ' ', text).strip()
    
    return text
```

### 2. Apply in `pipeline.py`
Locate the `_format_context_for_llm` method in `src/r_core/pipeline.py`.

Update the history generation block:

```python
from .utils import sanitize_bot_history # Add import at top

# Inside _format_context_for_llm:
        if context.get(\"chat_history\"):
            chat_history = context[\"chat_history\"]
            if limit_history is not None:
                chat_history = chat_history[-limit_history:]
            if chat_history:
                lines.append(\"RECENT DIALOGUE:\")
                for msg in chat_history:
                    role = \"User\" if msg[\"role\"] == \"user\" else \"Assistant\"
                    content = msg['content']
                    
                    # ✨ SANITIZE ASSISTANT MESSAGES
                    if role == \"Assistant\":
                        content = sanitize_bot_history(content)
                        
                    lines.append(f\"{role}: {content}\")
                lines.append(\"\") 
```

### 3. Verify
Run the app. Even if the immediate previous message in the UI shows "улыбается Сереженька", the next generated response should not echo it, because the LLM will see a clean history.