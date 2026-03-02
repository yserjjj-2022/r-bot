# Task 12: Context Sanitization & Preferred Name Handling

## Context
In Task 11, we moved the formatting rules to the end of the LLM prompt. However, if the user doesn't clear their chat history, the LLM will still see past messages where the bot used action descriptions (e.g., *смеется*) and excessive diminutives (e.g., "Сереженька"). This "bad history" can still poison the generation. We want to keep the valuable semantic memory and history intact in the DB, but "sanitize" it on the fly *before* it goes into the LLM prompt.

Additionally, we need a robust way to enforce the user's preferred name or general address style, rather than relying on the LLM guessing.

## Acceptance Criteria
1. When constructing the conversation history string (`context_str`), past assistant messages must be scrubbed of action descriptions (words inside asterisks, or common patterns like `смеется`, `улыбается` at the start of sentences).
2. Known diminutive names in the history (e.g., "Сереженька") must be replaced on the fly with a neutral name (e.g., "Сергей") or removed.
3. The actual chat history in the database must **NOT** be altered. The sanitization happens only during prompt assembly.
4. The user's `user_profile` should explicitly enforce addressing without diminutives (either neutral name "Сергей" or generic "дружище/ты").
5. Implement metrics logging for sanitization (e.g., `sanitized_history_lines_count`) to track how often the history had to be cleaned.

## Implementation Steps

### 1. Create a Sanitizer Utility (`src/r_core/utils.py`)
Add a new function `sanitize_bot_message_for_context(text: str) -> str`.
- Use regex to remove text enclosed in asterisks: `re.sub(r'\*.*?\*', '', text)`
- Use regex to remove text enclosed in parentheses if they look like actions (optional, but good for safety).
- Remove common Russian roleplay action prefixes (e.g., `смеется`, `улыбается`, `подмигивает` if they appear alone at the start or are clearly not part of the spoken sentence).
- Replace excessive diminutives. For now, a simple replacement list is fine: `text.replace("Сереженька", "Сергей").replace("Сашенька", "Саша")`.

### 2. Apply Sanitization in `pipeline.py`
In `RCoreKernel._format_context_for_llm`, modify the `RECENT DIALOGUE` assembly:

```python
        if context.get("chat_history"):
            chat_history = context["chat_history"]
            if limit_history is not None:
                chat_history = chat_history[-limit_history:]
            if chat_history:
                lines.append("RECENT DIALOGUE:")
                for msg in chat_history:
                    if msg['role'] == "assistant":
                        # Apply sanitization to past bot messages
                        from .utils import sanitize_bot_message_for_context
                        clean_content = sanitize_bot_message_for_context(msg['content'])
                        lines.append(f"Assistant: {clean_content}")
                    else:
                        lines.append(f"User: {msg['content']}")
                lines.append("") 
```

*Note: You may want to return a count of how many lines were actually changed to log it later.*

### 3. Update Name Enforcement Rules in `llm.py`
In `LLMService.generate_response`, update the `formatting_rules` block (which was moved to the end in Task 11) to explicitly enforce the preferred name strategy based on the profile.

Currently, the user profile has `name` (e.g., "Сергей").
Add an instruction:
```python
            "2. NO DIMINUTIVES: NEVER use sweet or diminutive name forms (like 'Сереженька', 'Сашенька'). Use the user's exact name from the profile (e.g., 'Сергей') or neutral terms like 'дружище'.\\n"
```

### 4. Metrics Logging (Optional but recommended)
If possible, track if `sanitize_bot_message_for_context` made changes, and pass that count back to `pipeline.py` to include in `internal_stats` under a key like `sanitized_history_lines`.

## Verification
1. Do NOT clear the chat history.
2. Send a new message.
3. Look at the console logs (if you add a debug print for the generated `context_str`) to verify that the old messages are injected *without* asterisks and "Сереженька".
4. Ensure the new response from the bot adheres to the clean format.