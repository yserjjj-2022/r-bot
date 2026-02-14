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
from typing import List, Dict, Any, Optional, Set, Tuple, Union
from sqlalchemy import select, text, delete, and_, update
from sqlalchemy.ext.asyncio import AsyncSession
from src.r_core.infrastructure.db import (
    AsyncSessionLocal,
    SemanticModel,
    EpisodicModel,
    VolitionalModel,
    UserProfileModel
)
from src.r_core.config import settings


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
            
            # Task 3: Обновление volitional_patterns
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
        
        Returns:
            {
                "subject": "...",
                "predicate": "...",
                "object": "...",
                "confidence": 0.0-1.0,
                "sentiment": {...} or None
            }
        """
        # Формируем промпт
        facts_text = "\n".join([
            f"{i+1}. {f.subject} {f.predicate} {f.object} (confidence: {f.confidence:.2f})"
            for i, f in enumerate(facts)
        ])
        
        prompt = f"""
Ты - система консолидации семантической памяти.
Задача: слить несколько похожих фактов в один канонический.

Факты:
{facts_text}

Инструкция:
- Сохрани общий смысл, убери дубликаты.
- confidence = средневзвешенное (с учётом старых confidence).
- Если факты НЕ являются дубликатами (разный смысл), верни null.

Формат ответа (JSON):
{{
    "is_duplicate": true/false,
    "canonical": {{
        "subject": "...",
        "predicate": "...",
        "object": "...",
        "confidence": 0.85
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
            for theme in themes:
                fact_text = f"{theme['subject']} {theme['predicate']} {theme['object']}"
                embedding = await self.embedder.embed(fact_text)
                
                new_fact = SemanticModel(
                    user_id=user_id,
                    subject=theme["subject"],
                    predicate=theme["predicate"],
                    object=theme["object"],
                    confidence=theme.get("confidence", 0.7),
                    embedding=embedding,
                    source_message_id="hippocampus_episode_extraction"
                )
                session.add(new_fact)
            
            await session.commit()
            
            return {
                "status": "ok",
                "episodes_analyzed": len(episodes),
                "themes_extracted": len(themes)
            }
    
    async def _llm_extract_themes(self, episodes: List[EpisodicModel]) -> List[Dict[str, Any]]:
        """
        LLM анализирует эпизоды и извлекает повторяющиеся темы/интересы.
        """
        episodes_text = "\n".join([
            f"{i+1}. {ep.raw_text[:200]}"
            for i, ep in enumerate(episodes[:50])  # ограничение для контекста
        ])
        
        prompt = f"""
Ты - система анализа эпизодической памяти.
Задача: найти повторяющиеся темы/интересы пользователя.

Эпизоды:
{episodes_text}

Инструкция:
- Найди темы, которые встречаются >= {self.min_theme_frequency} раз.
- Создай факт в формате Subject-Predicate-Object.
- confidence = frequency / total_episodes.

Пример:
{{
    "themes": [
        {{\"subject\": \"User\", \"predicate\": \"INTERESTED_IN\", \"object\": \"Python\", \"confidence\": 0.75}},
        {{\"subject\": \"User\", \"predicate\": \"DISLIKES\", \"object\": \"холодная погода\", \"confidence\": 0.6}}
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
    
    # ========== TASK 3: Update Volitional Patterns ==========
    
    async def _update_volitional_patterns(self, user_id: int) -> Dict[str, Any]:
        """
        Task 3: Обновление volitional_memory (паттерны поведения).
        
        Анализируем:
        - Время активности (night_owl / morning_person)
        - Энергетический профиль (high / low energy)
        
        ✨ NEW (Update): Reinforcement Learning of Volition
        Вместо простого добавления, мы теперь:
        1. Ищем существующий паттерн.
        2. Если найден: Увеличиваем learned_delta (обучение) и обновляем last_activated_at.
        3. Если нет: Создаем с базовым intensity.
        """
        async with AsyncSessionLocal() as session:
            # Загрузить эпизоды за последние N дней
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
            )
            episodes = result.scalars().all()
            
            if len(episodes) < 5:
                return {"status": "skip", "reason": "too_few_episodes", "count": len(episodes)}
            
            patterns_updated = 0
            
            # --- Analysis 1: Night Owl ---
            timestamps = [ep.created_at for ep in episodes]
            is_night_owl = self._detect_night_owl(timestamps)
            
            if is_night_owl:
                await self._reinforce_or_create_pattern(
                    session, user_id,
                    trigger="time > 22:00",
                    impulse="initiate_dialogue",
                    defaults={
                        "goal": "social_connection",
                        "resolution_strategy": "wait_for_user",
                        "action_taken": "detected_night_owl_pattern",
                        "intensity": 0.4  # Базовая сила хронотипа
                    }
                )
                patterns_updated += 1
            
            # --- Analysis 2: High Energy ---
            avg_emotion = sum(ep.emotion_score for ep in episodes) / len(episodes)
            energy_level = min(1.0, max(0.0, (avg_emotion + 1.0) / 2.0))  # нормализация -1..1 → 0..1
            
            if energy_level > 0.7:
                await self._reinforce_or_create_pattern(
                    session, user_id,
                    trigger="user_message_received",
                    impulse="high_energy",
                    defaults={
                        "goal": "maintain_engagement",
                        "resolution_strategy": "mirror_energy",
                        "action_taken": f"detected_high_energy (avg={energy_level:.2f})",
                        "intensity": 0.7  # Высокая базовая сила
                    }
                )
                patterns_updated += 1
            
            await session.commit()
            
            return {
                "status": "ok",
                "episodes_analyzed": len(episodes),
                "patterns_updated": patterns_updated
            }
            
    async def _reinforce_or_create_pattern(
        self, 
        session: AsyncSession, 
        user_id: int, 
        trigger: str, 
        impulse: str, 
        defaults: Dict[str, Any]
    ):
        """
        Helper: Ищет паттерн. Если есть — усиливает (Reinforcement). Если нет — создает.
        """
        # 1. Try to find existing pattern
        result = await session.execute(
            select(VolitionalModel).where(
                and_(
                    VolitionalModel.user_id == user_id,
                    VolitionalModel.trigger == trigger,
                    VolitionalModel.impulse == impulse
                )
            )
        )
        pattern = result.scalar_one_or_none()
        
        if pattern:
            # ✨ REINFORCEMENT: Усиливаем паттерн
            # learned_delta растет, но не бесконечно (clamp -1.0 to +1.0)
            new_delta = pattern.learned_delta + pattern.reinforcement_rate
            pattern.learned_delta = max(-1.0, min(1.0, new_delta))
            
            # Обновляем время последней активации (важно для decay)
            pattern.last_activated_at = datetime.utcnow()
            
            # Обновляем метаданные (например, новый уровень энергии)
            if "action_taken" in defaults:
                pattern.action_taken = defaults["action_taken"]
                
        else:
            # ✨ CREATE: Создаем новый паттерн
            new_pattern = VolitionalModel(
                user_id=user_id,
                trigger=trigger,
                impulse=impulse,
                goal=defaults.get("goal"),
                resolution_strategy=defaults.get("resolution_strategy"),
                action_taken=defaults.get("action_taken"),
                intensity=defaults.get("intensity", 0.5),
                learned_delta=0.0,
                last_activated_at=datetime.utcnow()
            )
            session.add(new_pattern)

    def _detect_night_owl(self, timestamps: List[datetime]) -> bool:
        """Проверяет, является ли пользователь ночной совой (>50% активности 22:00-06:00)"""
        night_count = sum(1 for ts in timestamps if ts.hour >= 22 or ts.hour <= 6)
        return night_count / len(timestamps) > 0.5
    
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
                """),
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
        Uses raw SQL to avoid needing a new model definition right now.
        """
        # FIX: Ensure python list for json serialization
        emb_str = self._serialize_vector(predicted_embedding)
        
        async with AsyncSessionLocal() as session:
            await session.execute(
                text("""
                    INSERT INTO prediction_history 
                    (user_id, session_id, bot_message, predicted_reaction, predicted_embedding)
                    VALUES (:user_id, :session_id, :bot_message, :predicted_reaction, :predicted_embedding::vector)
                """),
                {
                    "user_id": user_id,
                    "session_id": session_id,
                    "bot_message": bot_message,
                    "predicted_reaction": predicted_reaction,
                    "predicted_embedding": emb_str
                }
            )
            await session.commit()

    async def get_last_prediction(self, session_id: str) -> Optional[Dict]:
        """
        Get the most recent UNVERIFIED prediction for this session.
        """
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                text("""
                    SELECT * FROM prediction_history 
                    WHERE session_id = :session_id 
                    ORDER BY created_at DESC 
                    LIMIT 1
                """),
                {"session_id": session_id}
            )
            
            # SQLAlchemy returns Row objects, convert to dict
            row = result.fetchone()
            if not row:
                return None
                
            # Accessing row columns by index or name depends on driver, 
            # assuming name access or mapping.
            # Convert row to dict safely
            try:
                data = row._mapping
            except AttributeError:
                # Fallback for older alchemy
                keys = result.keys()
                data = dict(zip(keys, row))
            
            # If actual_message is present, it's already verified
            if data["actual_message"] is not None:
                return None
                
            return dict(data)

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
        
        async with AsyncSessionLocal() as session:
            await session.execute(
                text("""
                    UPDATE prediction_history
                    SET actual_message = :actual_message,
                        actual_embedding = :actual_embedding::vector,
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
