# src/r_core/hippocampus.py
"""
🧠 Hippocampus Consolidation Module

Назначение:
Гиппокамп - это НЕ хранилище, а ПРОЦЕССОР.
Он служит мостом между episodic_memory (сырые эпизоды) и semantic_memory (консолидированные факты).

Три основные задачи:
1. Deduplicate semantic facts (слияние дублей фактов)
2. Extract facts from episodes (консолидация: эпизод → семантика)
3. Update volitional patterns (выявление паттернов поведения, их обучение и поддержка)

Триггер: user_profiles.short_term_memory_load >= 20
"""

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Set, Tuple, Union, Sequence
from sqlalchemy import select, text, delete, and_, update, or_
from sqlalchemy.ext.asyncio import AsyncSession
from src.r_core.infrastructure.db import (
    AsyncSessionLocal,
    SemanticModel,
    EpisodicModel,
    VolitionalModel,
    UserProfileModel,
    ChatHistoryModel
)
from src.r_core.config import settings


# === Stage 1: TEC Decay Map (Nature Taxonomy) ===
# Base decay rate per turn for each intent category
# From attention-engagement-theory.md spec
BASE_DECAY_MAP = {
    "Phatic": 1.0,     # Social rituals: very stable
    "Casual": 0.4,     # Small talk: moderate decay
    "Narrative": 0.15, # Stories: faster decay
    "Deep": 0.05,      # Deep topics: slow decay (engaging)
    "Task": 0.0,       # Task-oriented: no automatic decay
}


@dataclass
class SemanticFact:
    """Semantic memory fact wrapper"""
    id: int
    subject: str
    predicate: str
    object: str
    confidence: float
    embedding: Optional[List[float]]
    created_at: datetime
    sentiment: Optional[Dict[str, Any]] = None


@dataclass
class Episode:
    """Episodic memory episode wrapper"""
    id: int
    raw_text: str
    embedding: List[float]
    emotion_score: float
    tags: List[str]
    created_at: datetime


class Hippocampus:
    """
    🧠 Memory Consolidation Engine
    
    Реализует "ленивую" консолидацию памяти.
    Запускается автоматически каждые N эпизодов (по умолчанию N=20).
    """
    
    def __init__(
        self,
        llm_client,  # LLM client для семантического анализа
        embedding_client,  # Embedding client для векторизации
        *,
        similarity_threshold: float = 0.85,  # порог для pgvector кластеризации
        max_cluster_size: int = 10,  # макс фактов в одном кластере
        episode_window_days: int = 30,  # окно для анализа эпизодов
        min_theme_frequency: int = 3,  # мин. повторов для создания факта
    ):
        self.llm = llm_client
        self.embedder = embedding_client
        self.similarity_threshold = similarity_threshold
        self.max_cluster_size = max_cluster_size
        self.episode_window_days = episode_window_days
        self.min_theme_frequency = min_theme_frequency

    def _ensure_list(self, embedding: Any) -> List[float]:
        """Helper to ensure embedding is a python list, not numpy array"""
        if hasattr(embedding, 'tolist'):
            return embedding.tolist()
        if isinstance(embedding, list):
            return embedding
        return []
    
    def _serialize_vector(self, embedding: Any) -> Optional[str]:
        """
        Robustly serialize vector to pgvector string format '[1.0,2.0,3.0]'.
        Returns None if embedding is missing or empty.
        """
        vec_list = self._ensure_list(embedding)
        if not vec_list:
            return None
        # pgvector expects '[1,2,3]' format. json.dumps produces exactly this for lists.
        return json.dumps(vec_list)

    async def consolidate(self, user_id: int) -> Dict[str, Any]:
        """
        🎓 Полный цикл консолидации памяти
        
        Returns:
            {
                "status": "ok" | "skip" | "error",
                "tasks_completed": ["deduplicate", "extract", "volitional"],
                "stats": {...}
            }
        """
        print(f"[Hippocampus] Starting consolidation for user {user_id}")
        
        stats = {
            "task_1_deduplicate": {},
            "task_2_extract": {},
            "task_3_volitional": {},
        }
        
        try:
            # Task 1: Дедупликация semantic_memory
            stats["task_1_deduplicate"] = await self._deduplicate_semantic_facts(user_id)
            
            # Task 2: Извлечение новых фактов из эпизодов
            stats["task_2_extract"] = await self._extract_facts_from_episodes(user_id)
            
            # Task 3: Обновление volitional_patterns (Semantic Intent Analysis)
            stats["task_3_volitional"] = await self._update_volitional_patterns(user_id)
            
            # Сброс счётчика
            await self._reset_consolidation_counter(user_id)
            
            print(f"[Hippocampus] ✅ Consolidation complete: {stats}")
            return {
                "status": "ok",
                "tasks_completed": ["deduplicate", "extract", "volitional"],
                "stats": stats
            }
            
        except Exception as e:
            print(f"[Hippocampus] ❌ Consolidation failed: {e}")
            return {
                "status": "error",
                "error": str(e),
                "stats": stats
            }
    
    # ========== TASK 1: Deduplicate Semantic Facts ==========
    
    async def _deduplicate_semantic_facts(self, user_id: int) -> Dict[str, Any]:
        """
        Task 1: Слияние дубликатов в semantic_memory
        
        Алгоритм:
        1. pgvector находит кластеры похожих фактов (recall)
        2. LLM проверяет семантическое совпадение (precision)
        3. Создаёт канонический факт, удаляет дубли
        """
        async with AsyncSessionLocal() as session:
            # 1. Загрузить факты с embedding
            facts = await self._load_semantic_facts_with_embeddings(session, user_id)
            
            if len(facts) < 3:
                return {"status": "skip", "reason": "too_few_facts", "count": len(facts)}
            
            # 2. Найти кластеры через pgvector
            clusters = await self._find_similar_fact_clusters(session, user_id, facts)
            
            if not clusters:
                return {"status": "skip", "reason": "no_duplicates", "facts_checked": len(facts)}
            
            # 3. Для каждого кластера: LLM merge
            merged_count = 0
            for cluster_ids in clusters:
                cluster_facts = [f for f in facts if f.id in cluster_ids]
                if len(cluster_facts) < 2:
                    continue
                
                # LLM сливает факты
                canonical = await self._llm_merge_facts(cluster_facts)
                if not canonical:
                    continue
                
                # Сохранить канонический факт, удалить старые
                await self._upsert_canonical_fact(session, user_id, canonical, cluster_ids)
                merged_count += 1
            
            await session.commit()
            
            return {
                "status": "ok",
                "facts_checked": len(facts),
                "clusters_found": len(clusters),
                "clusters_merged": merged_count
            }
    
    async def _load_semantic_facts_with_embeddings(
        self, session: AsyncSession, user_id: int
    ) -> List[SemanticFact]:
        """Загрузить факты с embedding (только те, где embedding IS NOT NULL)"""
        result = await session.execute(
            select(SemanticModel)
            .where(
                and_(
                    SemanticModel.user_id == user_id,
                    SemanticModel.embedding.isnot(None)
                )
            )
            .order_by(SemanticModel.created_at.desc())
            .limit(200)  # ограничение для производительности
        )
        rows = result.scalars().all()
        
        return [
            SemanticFact(
                id=row.id,
                subject=row.subject,
                predicate=row.predicate,
                object=row.object,
                confidence=row.confidence,
                embedding=row.embedding,
                created_at=row.created_at,
                sentiment=row.sentiment
            )
            for row in rows
        ]
    
    async def _find_similar_fact_clusters(
        self, session: AsyncSession, user_id: int, facts: List[SemanticFact]
    ) -> List[Set[int]]:
        """
        Найти кластеры похожих фактов через pgvector cosine similarity.
        
        Returns: List of Sets, каждый set = {fact_id1, fact_id2, ...}
        """
        clusters: List[Set[int]] = []
        processed: Set[int] = set()
        
        for fact in facts:
            if fact.id in processed or fact.embedding is None:
                continue
            
            # Use new robust serializer
            emb_str = self._serialize_vector(fact.embedding)
            if not emb_str:
                continue
            
            # Найти соседей через pgvector
            query = text("""
                SELECT id, 1 - (embedding <=> :target_embedding) AS similarity
                FROM semantic_memory
                WHERE user_id = :user_id
                  AND id != :fact_id
                  AND embedding IS NOT NULL
                  AND 1 - (embedding <=> :target_embedding) >= :threshold
                ORDER BY similarity DESC
                LIMIT :max_size
            """)
            
            result = await session.execute(query, {
                "user_id": user_id,
                "fact_id": fact.id,
                "target_embedding": emb_str,
                "threshold": self.similarity_threshold,
                "max_size": self.max_cluster_size
            })
            
            neighbors = result.fetchall()
            
            if neighbors:
                cluster = {fact.id} | {row.id for row in neighbors}
                clusters.append(cluster)
                processed.update(cluster)
        
        return clusters
    
    async def _llm_merge_facts(self, facts: List[SemanticFact]) -> Optional[Dict[str, Any]]:
        """
        LLM сливает несколько фактов в один канонический.
        """
        # Формируем промпт
        facts_text = "\n".join([
            f"{i+1}. {f.subject} {f.predicate} {f.object} (confidence: {f.confidence:.2f})"
            for i, f in enumerate(facts)
        ])
        
        # ✨ Updated Prompt: Added Sentiment Extraction
        prompt = f"""
Ты - система консолидации семантической памяти.
Задача: слить несколько похожих фактов в один канонический.

Факты:
{facts_text}

Инструкция:
- Сохрани общий смысл, убери дубликаты.
- confidence = средневзвешенное (с учётом старых confidence).
- sentiment: Оцени эмоцию пользователя к объекту (Valence: -1..1, Arousal: 0..1). Если эмоция неясна, верни null.
- Если факты НЕ являются дубликатами (разный смысл), верни null.

Формат ответа (JSON):
{{
    "is_duplicate": true/false,
    "canonical": {{
        "subject": "...",
        "predicate": "...",
        "object": "...",
        "confidence": 0.85,
        "sentiment": {{ "valence": 0.8, "arousal": 0.5, "dominance": 0.0 }}
    }}
}}
"""
        
        try:
            # Вызываем LLM (предполагаем, что llm.complete возвращает строку)
            response = await self.llm.complete(prompt)
            data = json.loads(response)
            
            if not data.get("is_duplicate", False):
                return None
            
            canonical = data.get("canonical")
            if not canonical or not all(k in canonical for k in ["subject", "predicate", "object"]):
                return None
            
            return canonical
            
        except Exception as e:
            print(f"[Hippocampus] LLM merge failed: {e}")
            return None
    
    async def _upsert_canonical_fact(
        self,
        session: AsyncSession,
        user_id: int,
        canonical: Dict[str, Any],
        old_fact_ids: Set[int]
    ):
        """Сохранить канонический факт, удалить старые"""
        # Создаём embedding для нового факта
        fact_text = f"{canonical['subject']} {canonical['predicate']} {canonical['object']}"
        embedding = await self.embedder.embed(fact_text)
        
        # Создаём новый факт
        new_fact = SemanticModel(
            user_id=user_id,
            subject=canonical["subject"],
            predicate=canonical["predicate"],
            object=canonical["object"],
            confidence=canonical.get("confidence", 0.8),
            embedding=embedding,
            sentiment=canonical.get("sentiment"),
            source_message_id="hippocampus_consolidation"
        )
        session.add(new_fact)
        
        # Удаляем старые
        await session.execute(
            delete(SemanticModel).where(SemanticModel.id.in_(old_fact_ids))
        )
    
    # ========== TASK 2: Extract Facts from Episodes ==========
    
    async def _extract_facts_from_episodes(self, user_id: int) -> Dict[str, Any]:
        """
        Task 2: Извлечение новых фактов из episodic_memory.
        
        Пример: 5 эпизодов упоминают "Python" → факт: "User INTERESTED_IN Python"
        """
        async with AsyncSessionLocal() as session:
            # Загрузить последние N эпизодов
            cutoff_date = datetime.utcnow() - timedelta(days=self.episode_window_days)
            result = await session.execute(
                select(EpisodicModel)
                .where(
                    and_(
                        EpisodicModel.user_id == user_id,
                        EpisodicModel.created_at >= cutoff_date
                    )
                )
                .order_by(EpisodicModel.created_at.desc())
                .limit(100)
            )
            episodes = result.scalars().all()
            
            if len(episodes) < self.min_theme_frequency:
                return {"status": "skip", "reason": "too_few_episodes", "count": len(episodes)}
            
            # LLM анализирует темы
            themes = await self._llm_extract_themes(episodes)
            
            if not themes:
                return {"status": "skip", "reason": "no_themes_found", "episodes_checked": len(episodes)}
            
            # Сохраняем новые факты
            duplicates_skipped = 0
            facts_added = 0
            
            for theme in themes:
                # ✨ Fix: Check duplicates before adding
                existing = await session.execute(
                    select(SemanticModel).where(
                        and_(
                            SemanticModel.user_id == user_id,
                            SemanticModel.subject.ilike(theme["subject"]),
                            SemanticModel.predicate.ilike(theme["predicate"]),
                            SemanticModel.object.ilike(theme["object"])
                        )
                    ).limit(1)
                )
                if existing.scalar_one_or_none():
                    duplicates_skipped += 1
                    continue

                fact_text = f"{theme['subject']} {theme['predicate']} {theme['object']}"
                embedding = await self.embedder.embed(fact_text)
                
                new_fact = SemanticModel(
                    user_id=user_id,
                    subject=theme["subject"],
                    predicate=theme["predicate"],
                    object=theme["object"],
                    confidence=theme.get("confidence", 0.7),
                    embedding=embedding,
                    source_message_id="hippocampus_episode_extraction",
                    sentiment=theme.get("sentiment") # ✨ Save Sentiment
                )
                session.add(new_fact)
                facts_added += 1
            
            await session.commit()
            
            return {
                "status": "ok",
                "episodes_analyzed": len(episodes),
                "themes_found": len(themes),
                "facts_added": facts_added,
                "duplicates_skipped": duplicates_skipped
            }
    
    async def _llm_extract_themes(self, episodes: Sequence[EpisodicModel]) -> List[Dict[str, Any]]:
        """
        LLM анализирует эпизоды и извлекает повторяющиеся темы/интересы пользователя.
        """
        episodes_text = "\n".join([
            f"{i+1}. {ep.raw_text[:200]}"
            for i, ep in enumerate(episodes[:50])  # ограничение для контекста
        ])
        
        # ✨ Updated Prompt: Added Sentiment Extraction
        prompt = f"""
Ты - система анализа эпизодической памяти.
Задача: найти повторяющиеся темы/интересы пользователя.

Эпизоды:
{episodes_text}

Инструкция:
- Найди темы, которые встречаются >= {self.min_theme_frequency} раз.
- Создай факт в формате Subject-Predicate-Object.
- confidence = frequency / total_episodes.
- sentiment: Оцени эмоцию пользователя к этой теме (Valence: -1..1, Arousal: 0..1).

Пример:
{{
    "themes": [
        {{
            "subject": "User", 
            "predicate": "INTERESTED_IN", 
            "object": "Python", 
            "confidence": 0.75,
            "sentiment": {{ "valence": 0.7, "arousal": 0.4, "dominance": 0.2 }}
        }}
    ]
}}

Верни JSON:
"""
        
        try:
            response = await self.llm.complete(prompt)
            data = json.loads(response)
            return data.get("themes", [])
        except Exception as e:
            print(f"[Hippocampus] Theme extraction failed: {e}")
            return []
    
    # ========== TASK 3: Update Volitional Patterns (Semantic Intent Analysis) ==========
    
    async def _update_volitional_patterns(self, user_id: int) -> Dict[str, Any]:
        """
        Task 3: Semantic Intent Analysis - Stage 1: Taxonomy & TEC Decay.
        
        Выделяет структуру волевого акта из последних сообщений:
        - Trigger (контекст)
        - Impulse (сопротивление/желание)
        - Target (объект цели)
        - Intent Category (Nature Taxonomy: Phatic, Casual, Narrative, Deep, Task)
        
        TEC Decay Logic:
        - effective_decay = base_decay * complexity_modifier
        - fuel = max(0, fuel - effective_decay)
        - Recovery: fuel += recovery_rate if pattern is reinforced
        """
        async with AsyncSessionLocal() as session:
            # 1. Загружаем последние 25 сообщений (User + Assistant)
            # 25 - достаточно для контекста, не слишком много шума
            result = await session.execute(
                select(ChatHistoryModel)
                .where(ChatHistoryModel.user_id == user_id)
                .order_by(ChatHistoryModel.created_at.desc())
                .limit(25)
            )
            messages = result.scalars().all()
            # Разворачиваем в хронологическом порядке для LLM
            messages = list(reversed(messages))
            
            if len(messages) < 5:
                return {"status": "skip", "reason": "too_few_messages", "count": len(messages)}
            
            # 2. LLM извлекает волевые паттерны (updated for Stage 1)
            patterns_data = await self._llm_extract_volitional_intent(messages)
            
            if not patterns_data:
                return {"status": "ok", "reason": "no_volition_detected"}
            
            patterns_updated = 0
            patterns_created = 0
            
            # 3. Merging logic with TEC Decay
            for p_data in patterns_data:
                target = p_data.get("target")
                if not target:
                    continue
                
                # Поиск похожего паттерна по Target (case-insensitive)
                existing_pattern = await session.execute(
                    select(VolitionalModel).where(
                        and_(
                            VolitionalModel.user_id == user_id,
                            VolitionalModel.target.ilike(target),
                            VolitionalModel.is_active == True
                        )
                    ).limit(1)
                )
                existing = existing_pattern.scalar_one_or_none()
                
                # === Stage 1: Get intent category and TEC fields ===
                intent_category = p_data.get("intent_category", "Casual")
                topic_engagement = p_data.get("topic_engagement", 1.0)
                complexity_modifier = p_data.get("complexity_modifier", 1.0)
                
                # === Calculate effective decay ===
                base_decay = BASE_DECAY_MAP.get(intent_category, BASE_DECAY_MAP["Casual"])
                effective_decay = base_decay * complexity_modifier
                
                if existing:
                    # ✨ REINFORCE / MERGE with TEC
                    # === Stage 1: Calculate situational_multiplier ===
                    # response_density = min(len(user_text.split()) / 50.0, 1.0)
                    # Assume current_PE = 1 - topic_engagement (prediction error)
                    current_PE = 1.0 - existing.topic_engagement
                    response_density = min(len(messages[-1].content.split()) / 50.0, 1.0) if messages else 0.5
                    situational_multiplier = (0.5 + (1 - current_PE) * 0.5) * (2.0 - response_density)
                    
                    # Calculate effective decay
                    effective_decay = base_decay * situational_multiplier
                    
                    # Apply decay to topic_engagement
                    existing.topic_engagement = max(0.0, existing.topic_engagement - effective_decay)
                    
                    # Fuel update: apply decay first, then reinforce
                    existing.fuel = max(0.0, existing.fuel - effective_decay)
                    
                    # Reinforce with inertia: 0.7 * old + 0.3 * new
                    new_fuel = p_data.get("fuel", 0.5)
                    existing.fuel = 0.7 * existing.fuel + 0.3 * new_fuel
                    
                    # Apply recovery rate after reinforcement
                    recovery_rate = p_data.get("recovery_rate", 0.05)
                    existing.fuel = min(1.0, existing.fuel + recovery_rate)
                    
                    # Update TEC fields
                    existing.intent_category = intent_category
                    existing.complexity_modifier = complexity_modifier
                    existing.base_decay_rate = base_decay
                    existing.emotional_load = p_data.get("emotional_load", 0.0)
                    existing.recovery_rate = recovery_rate
                    
                    # Intensity: max(old, new)
                    existing.intensity = max(existing.intensity, p_data.get("intensity", 0.5))
                    
                    # === Stage 1: Updated learned_delta logic ===
                    # Only reinforce if topic_engagement > 0.5 (not exhausted)
                    reinforcement_rate = existing.reinforcement_rate if hasattr(existing, 'reinforcement_rate') else 0.05
                    if current_PE < 0.2 and existing.topic_engagement > 0.5:
                        existing.learned_delta = min(1.0, existing.learned_delta + reinforcement_rate)
                    
                    existing.last_activated_at = datetime.utcnow()
                    existing.turns_active += 1
                    
                    patterns_updated += 1
                else:
                    # ✨ CREATE NEW with TEC fields
                    new_pattern = VolitionalModel(
                        user_id=user_id,
                        trigger=p_data.get("trigger", "unknown"),
                        impulse=p_data.get("impulse", "unknown"),
                        target=target,
                        goal="self_improvement", # default grouping
                        resolution_strategy=p_data.get("resolution_strategy", ""),
                        intensity=p_data.get("intensity", 0.5),
                        fuel=p_data.get("fuel", 0.8),
                        learned_delta=0.0,
                        last_activated_at=datetime.utcnow(),
                        turns_active=1,
                        is_active=True,
                        # === Stage 1: TEC/Taxonomy fields ===
                        intent_category=intent_category,
                        topic_engagement=1.0,  # Fresh start - full engagement
                        base_decay_rate=base_decay,
                        complexity_modifier=complexity_modifier,
                        emotional_load=p_data.get("emotional_load", 0.0),
                        recovery_rate=p_data.get("recovery_rate", 0.05),
                    )
                    session.add(new_pattern)
                    patterns_created += 1
            
            await session.commit()
            
            return {
                "status": "ok",
                "messages_analyzed": len(messages),
                "patterns_extracted": len(patterns_data),
                "updated": patterns_updated,
                "created": patterns_created,
                "tec_decay_applied": True,
                "base_decay_map": BASE_DECAY_MAP
            }

    async def _llm_extract_volitional_intent(self, messages: List[ChatHistoryModel]) -> List[Dict[str, Any]]:
        """
        Извлекает JSON структуру волевого акта из диалога.
        """
        dialogue_text = "\n".join([
            f"{msg.role}: {msg.content}" 
            for msg in messages
        ])
        
        prompt = f"""
Ты - аналитик волевой сферы (Volitional Analyst).
Твоя задача: найти в диалоге следы волевого конфликта или стремления (Volitional Act).

Диалог:
{dialogue_text}

Структура Волевого Праттерна:
1. Trigger: Контекст или событие (например, "разговор о работе", "поздняя ночь").
2. Impulse: Внутреннее сопротивление или желание "животного я" (например, "лень", "страх", "злость").
3. Target: Объект приложения усилий (например, "Spanish", "Python", "Morning Run").
4. Resolution Strategy: Как пользователь пытается преодолеть импульс? (например, "обещание", "геймификация", "просьба о помощи").
5. Intensity: Сила конфликта (0.0 - 1.0).
6. Fuel: Текущий ресурс/желание (0.0 - нет сил, 1.0 - горит желанием).

Инструкция:
- Анализируй в основном реплики USER.
- Если волевого акта нет (просто болтовня), верни пустой список [].
- Не выдумывай. Извлекай только явные паттерны.

Верни JSON формат:
[
  {{
    "trigger": "...",
    "impulse": "...",
    "target": "...",
    "resolution_strategy": "...",
    "intensity": 0.7,
    "fuel": 0.5
  }}
]
"""
        try:
            response = await self.llm.complete(prompt)
            # Пытаемся распарсить JSON. Иногда LLM добавляет markdown ```json
            cleaned = response.replace("```json", "").replace("```", "").strip()
            data = json.loads(cleaned)
            
            if isinstance(data, list):
                return data
            elif isinstance(data, dict):
                return [data]
            return []
            
        except Exception as e:
            print(f"[Hippocampus] Volitional extraction failed: {e}")
            return []

    # ========== Utility ==========
    
    async def _reset_consolidation_counter(self, user_id: int):
        """Сбросить short_term_memory_load = 0 и обновить last_consolidation_at"""
        async with AsyncSessionLocal() as session:
            await session.execute(
                text("""
                    UPDATE user_profiles
                    SET short_term_memory_load = 0,
                        last_consolidation_at = NOW()
                    WHERE user_id = :user_id
                """)
            ,
                {"user_id": user_id}
            )
            await session.commit()
            
    # ========== ✨ NEW: Predictive Processing Methods (Phase 2.2) ==========

    async def save_prediction(self, 
                            user_id: int, 
                            session_id: str, 
                            bot_message: str, 
                            predicted_reaction: str,
                            predicted_embedding: Optional[List[float]] = None):
        """
        Save the bot's prediction about the user's NEXT move.
        """
        # FIX: Ensure python list for json serialization
        emb_str = self._serialize_vector(predicted_embedding)
        
        print(f"[Hippocampus] DEBUG: Saving Prediction. Session={session_id}, Prediction='{predicted_reaction}'")
        
        try:
            async with AsyncSessionLocal() as session:
                # FIX: Added RETURNING id
                result = await session.execute(
                    text("""
                        INSERT INTO prediction_history 
                        (user_id, session_id, bot_message, predicted_reaction, predicted_embedding)
                        VALUES (:user_id, :session_id, :bot_message, :predicted_reaction, :predicted_embedding)
                        RETURNING id
                    """),
                    {
                        "user_id": user_id,
                        "session_id": session_id,
                        "bot_message": bot_message,
                        "predicted_reaction": predicted_reaction,
                        "predicted_embedding": emb_str
                    }
                )
                new_id = result.scalar()
                await session.commit()
                print(f"[Hippocampus] DEBUG: DB Commit Successful. Created Prediction ID={new_id}")
        except Exception as e:
             print(f"[Hippocampus] ❌ FATAL DB ERROR in save_prediction: {e}")
             raise e

    async def get_last_prediction(self, session_id: str) -> Optional[Dict]:
        """
        Get the most recent UNVERIFIED prediction for this session.
        
        FIX: Matches prediction to the last bot message from chat_history.
        This prevents matching user responses to old/wrong bot messages.
        """
        print(f"[Hippocampus] DEBUG: Fetching last prediction for Session={session_id}")
        
        try:
            async with AsyncSessionLocal() as session:
                # Step 1: Get last bot message from chat_history
                last_bot_result = await session.execute(
                    text("""
                        SELECT content FROM chat_history
                        WHERE session_id = :session_id
                          AND role = 'assistant'
                        ORDER BY created_at DESC
                        LIMIT 1
                    """),
                    {"session_id": session_id}
                )
                last_bot_row = last_bot_result.fetchone()
                
                if not last_bot_row:
                    print("[Hippocampus] DEBUG: No assistant messages found in chat_history. Skipping prediction lookup.")
                    return None
                
                last_bot_message = last_bot_row[0]  # content column
                print(f"[Hippocampus] DEBUG: Last bot message: '{last_bot_message[:60]}...'")
                
                # Step 2: Find prediction tied to this bot message
                result = await session.execute(
                    text("""
                        SELECT * FROM prediction_history 
                        WHERE session_id = :session_id 
                          AND bot_message = :bot_message
                          AND (actual_message IS NULL OR actual_message = '')
                        ORDER BY created_at DESC 
                        LIMIT 1
                    """),
                    {"session_id": session_id, "bot_message": last_bot_message}
                )
                
                row = result.fetchone()
                if not row:
                    print("[Hippocampus] DEBUG: No unverified predictions found for this bot message.")
                    return None
                    
                # Convert row to dict
                try:
                    data = row._mapping
                    data = dict(data)
                except AttributeError:
                    keys = result.keys()
                    data = dict(zip(keys, row))
                
                predicted = data.get('predicted_reaction') or ''
                print(f"[Hippocampus] DEBUG: ✅ Matched Prediction. ID={data.get('id')}, Predicted='{predicted[:50]}...'")
                return data
                
        except Exception as e:
            print(f"[Hippocampus] ❌ FATAL DB ERROR in get_last_prediction: {e}")
            return None

    async def verify_prediction(self, 
                              prediction_id: int, 
                              actual_message: str, 
                              prediction_error: float, 
                              actual_embedding: Optional[List[float]] = None):
        """
        Update the prediction record with the actual outcome and calculated error.
        """
        # FIX: Ensure python list for json serialization
        emb_str = self._serialize_vector(actual_embedding)
        
        print(f"[Hippocampus] DEBUG: Verifying Prediction {prediction_id}. Error={prediction_error}")
        
        try:
            async with AsyncSessionLocal() as session:
                await session.execute(
                    text("""
                        UPDATE prediction_history
                        SET actual_message = :actual_message,
                            actual_embedding = :actual_embedding,
                            prediction_error = :prediction_error,
                            verified_at = NOW()
                        WHERE id = :prediction_id
                    """),
                    {
                        "actual_message": actual_message,
                        "actual_embedding": emb_str,
                        "prediction_error": prediction_error,
                        "prediction_id": prediction_id
                    }
                )
                await session.commit()
                print(f"[Hippocampus] DEBUG: Prediction {prediction_id} Verified & Committed.")
        except Exception as e:
             print(f"[Hippocampus] ❌ FATAL DB ERROR in verify_prediction: {e}")

    # =========================================================================
    # Stage 3: The Bifurcation Engine - Vector Methods
    # =========================================================================
    
    async def get_semantic_neighbors(self, user_id: int, current_embedding: List[float], limit: int = 3) -> List[Dict[str, Any]]:
        """
        Vector 1: Semantic Neighbor
        
        Finds related semantic memories using vector similarity (Cosine Distance).
        Returns items where distance is between 0.35 and 0.65 (related, but not identical).
        
        Args:
            user_id: User ID
            current_embedding: Current message embedding
            limit: Maximum number of results
            
        Returns:
            List of semantic neighbor memories as dictionaries
        """
        async with AsyncSessionLocal() as session:
            try:
                emb_str = "[" + ",".join(map(str, current_embedding)) + "]"
                
                # Use vector_cosine_ops to find similar memories
                # Distance 0.35-0.65 means related but not identical
                result = await session.execute(
                    text("""
                        SELECT id, topic, content, vector_cosine_ops(embedding, :emb::vector) as distance
                        FROM semantic_memory
                        WHERE user_id = :user_id
                          AND vector_cosine_ops(embedding, :emb::vector) BETWEEN 0.35 AND 0.65
                        ORDER BY distance ASC
                        LIMIT :limit
                    """),
                    {"user_id": user_id, "emb": emb_str, "limit": limit}
                )
                rows = result.fetchall()
                
                neighbors = []
                for row in rows:
                    neighbors.append({
                        "id": row[0],
                        "topic": row[1],
                        "content": row[2],
                        "distance": row[3],
                        "vector_type": "semantic_neighbor"
                    })
                
                print(f"[Hippocampus] get_semantic_neighbors: Found {len(neighbors)} neighbors for user {user_id}")
                return neighbors
                
            except Exception as e:
                print(f"[Hippocampus] ❌ Error in get_semantic_neighbors: {e}")
                return []
    
    async def get_zeigarnik_returns(self, user_id: int, limit: int = 3) -> List[Dict[str, Any]]:
        """
        Vector 3: Zeigarnik Return
        
        Finds recent episodic memories with high prediction_error or unresolved tags.
        These are "unfinished business" topics that the user might want to return to.
        
        Args:
            user_id: User ID
            limit: Maximum number of results
            
        Returns:
            List of unresolved memories as dictionaries
        """
        async with AsyncSessionLocal() as session:
            try:
                # Query chat_history for unresolved topics
                # High emotion_score or specific markers indicate unresolved
                result = await session.execute(
                    text("""
                        SELECT id, content, emotion_score, created_at,
                               COALESCE(prediction_error, 0.5) as pe
                        FROM chat_history
                        WHERE user_id = :user_id
                          AND (emotion_score > 0.7 OR emotion_score < -0.7 
                               OR COALESCE(prediction_error, 0.5) > 0.6)
                        ORDER BY created_at DESC
                        LIMIT :limit
                    """),
                    {"user_id": user_id, "limit": limit}
                )
                rows = result.fetchall()
                
                zeigarnik_returns = []
                for row in rows:
                    zeigarnik_returns.append({
                        "id": row[0],
                        "content": row[1],
                        "emotion_score": row[2],
                        "created_at": row[3],
                        "prediction_error": row[4],
                        "vector_type": "zeigarnik_return"
                    })
                
                print(f"[Hippocampus] get_zeigarnik_returns: Found {len(zeigarnik_returns)} unresolved topics for user {user_id}")
                return zeigarnik_returns
                
            except Exception as e:
                print(f"[Hippocampus] ❌ Error in get_zeigarnik_returns: {e}")
                return []
