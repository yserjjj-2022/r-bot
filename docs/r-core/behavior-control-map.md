# R-Core Behavior Control Map

Цель: зафиксировать "карту управления поведением" R-Core для совместного обсуждения (психолог, матлингвист, разработка).
Карта описывает входы, обработку (Council + Neuro-Modulation), промпты и выходы, а также ветку экстренных состояний.

## Mermaid diagram

```mermaid
flowchart TD

%% ========== Inputs ==========
U[User message<br/>(text)] --> NLU[NLU/Parsing<br/>(intent, entities, sentiment)]
UP[User Profile<br/>(name, gender, preferred_mode)] --> CTX[Context Builder]
SM[Semantic Memory<br/>(facts)] --> CTX
EM[Episodic Memory<br/>(episodes)] --> CTX
CH[Chat History<br/>(last N)] --> CTX
NLU --> CTX

%% ========== Emergency gate ==========
CTX --> STATE[State Estimation<br/>(arousal/valence/risk)]
STATE -->|normal| COUNCIL[Council Scoring]

STATE -->|extreme| EMERGENCY[Emergency Controller<br/>(PFC shutdown / burnout / panic)]
EMERGENCY --> STYLE_EM[Emergency Style Modifiers]
EMERGENCY --> SAFE[Safety & De-escalation Policy]
SAFE --> RESP

%% ========== Council ==========
subgraph C[Council (5 agents)]
INT[Intuition] --> COUNCIL
SOC[Social] --> COUNCIL
PFC[Prefrontal] --> COUNCIL
STR[Striatum] --> COUNCIL
AMY[Amygdala] --> COUNCIL
end

COUNCIL --> HORM[Neuro‑Modulation<br/>(NE, DA, 5‑HT, CORT)]
HORM --> ARCH[Archetype Selector<br/>(CALM, RAGE, FEAR, ...)]
ARCH --> WIN[Winner Selection<br/>(max score + constraints)]

%% ========== Prompts ==========
SYS[System Prompt<br/>(values, role)] --> PROMPT[Prompt Composer]
AGP[Agent Prompt<br/>(winner instruction)] --> PROMPT
ARCH --> STYLE[Style Modifiers<br/>(tone, tempo, empathy)]
STYLE --> PROMPT
WIN --> PROMPT

%% ========== Optional module ==========
TM[Time Machine (optional)<br/>(counterfactual recall / rewind)] --> CTX

%% ========== Output ==========
PROMPT --> RESP[Final Response<br/>(user-facing text)]
PROMPT --> STATS[Internal Stats<br/>(scores, hormones, archetype, tokens, latency)]
```

## Блоки и ответственность

### Inputs
- User message: сырой текст + метаданные канала.
- User Profile: стабильные атрибуты пользователя (включая preferred_mode).
- Semantic/Episodic Memory: извлечённые факты и эпизоды, подходящие под текущий запрос.
- Chat History: последние N сообщений для локальной когерентности.

### Processing
- Context Builder: собирает единый контекст и "фичи" для Council.
- State Estimation: оценивает текущее состояние диалога/пользователя (норма vs экстрим).
- Council: 5 агентов дают независимые оценки/планы реакции.
- Neuro‑Modulation: гормоны корректируют веса/оценки (особенно в экстремальных режимах).
- Winner Selection: выбирает победителя с максимальным score с учётом ограничений политики.

### Prompts
- System Prompt: роль, ценности, запреты.
- Agent Prompt: инструкция выбранному агенту (что делать).
- Style Modifiers: тон/эмпатия/ритм из архетипа (CALM/RAGE/FEAR/...).

### Output
- Final Response: текст пользователю.
- Internal Stats: логируемые метрики (agent scores, гормоны, архетип, причины победы, latency, токены).

## Экстренные состояния
Экстренный контур нужен, если State Estimation фиксирует "опасную" зону (например, PFC shutdown, burnout, panic).
Он:
1) снижает сложность ответа (короче, яснее),
2) форсирует деэскалацию и поддержку,
3) может временно "перекрывать" Winner Selection.

## Time Machine (опционально)
Time Machine — отдельный модуль, если вы хотите явно обозначить:
- "откат" к предыдущим гипотезам/фактам,
- контрфактуальную проверку ("а если мы ошиблись?"),
- восстановление цепочки событий (timeline) из Episodic Memory.
Если сейчас это не в приоритете, блок можно оставить как optional.
