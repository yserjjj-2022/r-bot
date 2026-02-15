import uuid
from typing import List, Optional, Dict, Any
from datetime import datetime
import math
from pydantic import BaseModel
from sqlalchemy import select, desc, or_

from .schemas import (
    SemanticTriple, 
    EpisodicAnchor, 
    VolitionalPattern,
    IncomingMessage
)

from src.r_core.infrastructure.db import (
    AsyncSessionLocal, 
    SemanticModel, 
    EpisodicModel, 
    VolitionalModel,
    ChatHistoryModel,
    UserProfileModel
)
from src.r_core.infrastructure.llm import LLMService

class VectorStoreParams(BaseModel):
    limit: int = 5
    min_similarity: float = 0.7

class AbstractMemoryStore:
    async def save_semantic(self, user_id: int, triple: SemanticTriple):
        raise NotImplementedError
    
    async def save_episodic(self, user_id: int, anchor: EpisodicAnchor, embedding: Optional[List[float]] = None):
        raise NotImplementedError
        
    async def save_pattern(self, user_id: int, pattern: VolitionalPattern):
        raise NotImplementedError

    async def search_episodic(self, user_id: int, query_vector: List[float], params: VectorStoreParams) -> List[EpisodicAnchor]:
        raise NotImplementedError
        
    async def search_semantic(self, user_id: int, query_text: str) -> List[SemanticTriple]:
        raise NotImplementedError
        
    async def get_volitional_patterns(self, user_id: int) -> List[VolitionalPattern]:
        raise NotImplementedError

    async def save_chat_message(self, user_id: int, session_id: str, role: str, content: str):
        raise NotImplementedError
    
    async def get_recent_history(self, user_id: int, session_id: str, limit: int = 10) -> List[Dict]:
        raise NotImplementedError

    async def get_user_profile(self, user_id: int) -> Optional[Dict]:
        raise NotImplementedError

    async def update_user_profile(self, user_id: int, data: Dict):
        raise NotImplementedError

    async def get_sentiment_for_entity(self, user_id: int, entity: str) -> Optional[Dict]:
        """Получить эмоциональное отношение пользователя к сущности"""
        raise NotImplementedError

# --- Postgres Implementation ---

class PostgresMemoryStore(AbstractMemoryStore):
    async def save_semantic(self, user_id: int, triple: SemanticTriple):
        async with AsyncSessionLocal() as session:
            stmt = select(SemanticModel).where(
                SemanticModel.user_id == user_id,
                SemanticModel.subject == triple.subject,
                SemanticModel.predicate == triple.predicate,
                SemanticModel.object == triple.object
            )
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()
            
            if existing:
                existing.confidence = max(existing.confidence, triple.confidence)
                # ✨ Update sentiment if provided
                if triple.sentiment:
                    existing.sentiment = triple.sentiment
                # ✨ Update embedding if provided (and was null)
                if triple.embedding and not existing.embedding:
                     existing.embedding = triple.embedding
            else:
                new_triple = SemanticModel(
                    user_id=user_id,
                    subject=triple.subject,
                    predicate=triple.predicate,
                    object=triple.object,
                    confidence=triple.confidence,
                    source_message_id=triple.source_message_id,
                    sentiment=triple.sentiment,  # ✨ NEW: Save sentiment
                    embedding=triple.embedding   # ✨ NEW: Save embedding
                )
                session.add(new_triple)
            await session.commit()
            
    async def save_episodic(self, user_id: int, anchor: EpisodicAnchor, embedding: Optional[List[float]] = None):
        if not embedding:
            print("[Memory] Warning: Saving episodic memory without embedding.")
            embedding = [0.0] * 1536
            
        async with AsyncSessionLocal() as session:
            entry = EpisodicModel(
                user_id=user_id,
                raw_text=anchor.raw_text,
                embedding=embedding,
                emotion_score=anchor.emotion_score,
                tags=anchor.tags,
                ttl_days=anchor.ttl_days
            )
            session.add(entry)
            await session.commit()

    async def save_pattern(self, user_id: int, pattern: VolitionalPattern):
        async with AsyncSessionLocal() as session:
            entry = VolitionalModel(
                user_id=user_id,
                trigger=pattern.trigger,
                impulse=pattern.impulse,
                goal=pattern.goal,
                conflict_detected=pattern.conflict_detected,
                resolution_strategy=pattern.resolution_strategy,
                action_taken=pattern.action_taken
            )
            session.add(entry)
            await session.commit()

    async def search_episodic(self, user_id: int, query_vector: List[float], params: VectorStoreParams) -> List[EpisodicAnchor]:
        async with AsyncSessionLocal() as session:
            stmt = select(EpisodicModel).where(EpisodicModel.user_id == user_id)
            stmt = stmt.order_by(EpisodicModel.embedding.cosine_distance(query_vector))
            stmt = stmt.limit(params.limit)
            result = await session.execute(stmt)
            rows = result.scalars().all()
            return [
                EpisodicAnchor(
                    raw_text=r.raw_text,
                    emotion_score=r.emotion_score,
                    tags=r.tags,
                    ttl_days=r.ttl_days,
                    embedding_ref="pg_vector_stored" 
                ) for r in rows
            ]

    async def search_semantic(self, user_id: int, query_text: str) -> List[SemanticTriple]:
        async with AsyncSessionLocal() as session:
            stmt = select(SemanticModel).where(
                SemanticModel.user_id == user_id,
                (SemanticModel.object.ilike(f"%{query_text}%")) | 
                (SemanticModel.predicate.ilike(f"%{query_text}%"))
            )
            result = await session.execute(stmt)
            rows = result.scalars().all()
            return [
                SemanticTriple(
                    subject=r.subject,
                    predicate=r.predicate,
                    object=r.object,
                    confidence=r.confidence,
                    source_message_id=r.source_message_id,
                    sentiment=r.sentiment,  # ✨ NEW: Include sentiment
                    # Embedding is usually heavy to return for simple search, skipping for now
                ) for r in rows
            ]

    async def get_sentiment_for_entity(self, user_id: int, entity: str) -> Optional[Dict]:
        """
        ✨ NEW: Получить эмоциональное отношение пользователя к сущности.
        Возвращает sentiment-словарь или None, если нет данных.
        """
        async with AsyncSessionLocal() as session:
            # Ищем записи, где object содержит entity И есть sentiment
            stmt = select(SemanticModel).where(
                SemanticModel.user_id == user_id,
                SemanticModel.object.ilike(f"%{entity}%"),
                SemanticModel.sentiment.isnot(None)
            ).order_by(
                # Сортируем по силе эмоции (abs(valence))
                desc(SemanticModel.created_at)  # Берём самую свежую запись
            ).limit(1)
            
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()
            
            if row and row.sentiment:
                return {
                    "entity": row.object,
                    "predicate": row.predicate,
                    "sentiment": row.sentiment,
                    "intensity": abs(row.sentiment.get("valence", 0.0))
                }
            return None

    async def get_volitional_patterns(self, user_id: int) -> List[VolitionalPattern]:
        async with AsyncSessionLocal() as session:
            stmt = select(VolitionalModel).where(VolitionalModel.user_id == user_id)
            result = await session.execute(stmt)
            rows = result.scalars().all()
            return [
                VolitionalPattern(
                    trigger=r.trigger,
                    impulse=r.impulse,
                    goal=r.goal,
                    conflict_detected=r.conflict_detected,
                    resolution_strategy=r.resolution_strategy,
                    action_taken=r.action_taken
                ) for r in rows
            ]

    async def save_chat_message(self, user_id: int, session_id: str, role: str, content: str):
        async with AsyncSessionLocal() as session:
            msg = ChatHistoryModel(
                user_id=user_id,
                session_id=session_id,
                role=role,
                content=content
            )
            session.add(msg)
            await session.commit()

    async def get_recent_history(self, user_id: int, session_id: str, limit: int = 6) -> List[Dict]:
        async with AsyncSessionLocal() as session:
            stmt = select(ChatHistoryModel).where(
                ChatHistoryModel.user_id == user_id,
                ChatHistoryModel.session_id == session_id
            ).order_by(desc(ChatHistoryModel.created_at)).limit(limit)
            
            result = await session.execute(stmt)
            rows = result.scalars().all()
            
            history = [{"role": r.role, "content": r.content} for r in reversed(rows)]
            return history

    async def get_user_profile(self, user_id: int) -> Optional[Dict]:
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(UserProfileModel).where(UserProfileModel.user_id == user_id))
            profile = result.scalar_one_or_none()
            if not profile:
                return None
            return {
                "name": profile.name,
                "gender": profile.gender,
                "preferred_mode": profile.preferred_mode,
                "attributes": profile.attributes
            }

    async def update_user_profile(self, user_id: int, data: Dict):
        """
        Implementation of Smart Trait Competition (Winner-Takes-Slot).
        Uses simple fuzzy matching (string based for MVP) to prevent duplicates,
        and manages a limit of 7 slots.
        """
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(UserProfileModel).where(UserProfileModel.user_id == user_id))
            profile = result.scalar_one_or_none()
            
            if not profile:
                profile = UserProfileModel(user_id=user_id)
                session.add(profile)
            
            # Simple fields
            if "name" in data: profile.name = data["name"]
            if "gender" in data: profile.gender = data["gender"]
            if "preferred_mode" in data: profile.preferred_mode = data["preferred_mode"]
            
            # --- Smart Trait Competition Logic ---
            if "attributes" in data: 
                # Load existing traits
                # Expected format in DB: {"personality_traits": [{"name": "Romantic", "weight": 0.8}, ...]}
                current_attrs = dict(profile.attributes) if profile.attributes else {}
                traits = current_attrs.get("personality_traits", [])
                
                # New candidate traits from update
                new_traits_data = data["attributes"].get("personality_traits", [])
                
                # MVP: If just a dict update (legacy), fallback to merge
                # But if structured list, run competition
                if isinstance(new_traits_data, list):
                    MAX_SLOTS = 7
                    
                    for candidate in new_traits_data:
                        # 1. Check duplicates (Simple String Matching for MVP, Vector TODO)
                        match_found = False
                        for existing in traits:
                            # Fuzzy match: "Romantic" == "romantic"
                            if existing.get("name", "").lower() == candidate.get("name", "").lower():
                                # Reinforce existing
                                existing["weight"] = min(1.0, existing.get("weight", 0.5) + 0.1)
                                existing["last_reinforced"] = datetime.utcnow().isoformat()
                                match_found = True
                                break
                        
                        if not match_found:
                            # 2. Add new trait
                            candidate["weight"] = candidate.get("weight", 0.5) # Default weight
                            candidate["last_reinforced"] = datetime.utcnow().isoformat()
                            traits.append(candidate)
                    
                    # 3. Competition / Eviction
                    if len(traits) > MAX_SLOTS:
                        # Sort by weight (descending) -> Keep top N
                        traits.sort(key=lambda x: x.get("weight", 0.0), reverse=True)
                        traits = traits[:MAX_SLOTS]
                
                else:
                    # Legacy update behavior for non-trait attributes
                    current_attrs.update(data["attributes"])
                
                # Save back
                if isinstance(new_traits_data, list):
                    current_attrs["personality_traits"] = traits
                    
                profile.attributes = current_attrs
                
            await session.commit()

# --- Service Layer ---

class MemorySystem:
    def __init__(self, store: Optional[AbstractMemoryStore] = None):
        self.store = store or PostgresMemoryStore() 
        self.llm_service = LLMService()

    async def memorize_event(self, message: IncomingMessage, extraction_result: dict, precomputed_embedding: Optional[List[float]] = None):
        # 1. Save Raw User Message to History (STM)
        await self.store.save_chat_message(
            message.user_id, message.session_id, "user", message.text
        )

        # 2. Semantic & Episodic (LTM)
        user_id = message.user_id
        for triple_data in extraction_result.get("triples", []):
            triple = SemanticTriple(**triple_data, source_message_id=message.message_id)
            # ✨ NEW: If triple came without embedding (from fast path), generate it now?
            # Actually, `memorize_event` is mostly used by standard path. 
            # Fast path calls `save_semantic` directly via pipeline.
            # But let's handle it here just in case.
            if not triple.embedding and precomputed_embedding:
                 # Only if the triple text matches the message exactly, which is rare for semantic triples.
                 # Usually semantic triples are abstract.
                 # So we probably should generate specific embedding for the triple text.
                 try:
                     fact_text = f"{triple.subject} {triple.predicate} {triple.object}"
                     triple.embedding = await self.llm_service.get_embedding(fact_text)
                 except Exception:
                     pass
            
            await self.store.save_semantic(user_id, triple)

        for anchor_data in extraction_result.get("anchors", []):
            anchor = EpisodicAnchor(**anchor_data)
            try:
                if precomputed_embedding and anchor.raw_text == message.text:
                    embedding = precomputed_embedding
                else:
                    embedding = await self.llm_service.get_embedding(anchor.raw_text)
                
                await self.store.save_episodic(user_id, anchor, embedding=embedding)
            except Exception as e:
                print(f"[MemorySystem] Embedding failed: {e}")

        if "volitional_pattern" in extraction_result and extraction_result["volitional_pattern"]:
            pattern = VolitionalPattern(**extraction_result["volitional_pattern"])
            await self.store.save_pattern(user_id, pattern)

    async def memorize_bot_response(self, user_id: int, session_id: str, text: str):
        await self.store.save_chat_message(user_id, session_id, "assistant", text)

    async def recall_context(self, user_id: int, current_text: str, session_id: str = "default", precomputed_embedding: Optional[List[float]] = None) -> dict:
        # 1. Episodes (RAG)
        try:
            if precomputed_embedding:
                query_vec = precomputed_embedding
            else:
                query_vec = await self.llm_service.get_embedding(current_text)
                
            episodic = await self.store.search_episodic(user_id, query_vec, VectorStoreParams(limit=3))
        except Exception as e:
            print(f"[MemorySystem] Recall Embedding failed: {e}")
            episodic = []
        
        # 2. Facts
        semantic = await self.store.search_semantic(user_id, current_text)
        
        # 3. Patterns
        patterns = await self.store.get_volitional_patterns(user_id)
        
        # 4. Short Term History
        history = await self.store.get_recent_history(user_id, session_id, limit=6)

        # 5. User Profile
        profile = await self.store.get_user_profile(user_id)

        # ✨ 6. NEW: Affective Context — сканирование на эмоционально заряженные объекты
        affective_warnings = await self._extract_affective_context(user_id, current_text)
        
        # ✨ 7. NEW: Relevant Profile Traits — фильтрация черт личности по теме
        relevant_traits = self._filter_relevant_profile(profile, current_text)

        return {
            "episodic_memory": [e.dict() for e in episodic],
            "semantic_facts": [s.dict() for s in semantic],
            "known_patterns": [p.dict() for p in patterns],
            "chat_history": history,
            "user_profile": profile,
            "affective_context": affective_warnings,  # ✨ NEW
            "relevant_traits": relevant_traits        # ✨ NEW
        }

    async def _extract_affective_context(self, user_id: int, text: str) -> List[Dict]:
        """
        ✨ NEW: Извлекает сущности из текста и проверяет их на эмоциональную окраску.
        Возвращает список warnings для инъекции в промпт.
        """
        # Простая эвристика: извлекаем существительные в верхнем регистре или ключевые слова
        # В production можно использовать NER или LLM-извлечение
        words = text.split()
        entities = [w.strip(".,!?") for w in words if len(w) > 3]  # Упрощённый вариант
        
        warnings = []
        for entity in entities:
            sentiment_data = await self.store.get_sentiment_for_entity(user_id, entity)
            if sentiment_data and sentiment_data["intensity"] > 0.6:
                valence = sentiment_data["sentiment"].get("valence", 0.0)
                warnings.append({
                    "entity": sentiment_data["entity"],
                    "predicate": sentiment_data["predicate"],
                    "user_feeling": "NEGATIVE" if valence < 0 else "POSITIVE",
                    "intensity": sentiment_data["intensity"]
                })
        
        return warnings

    def _filter_relevant_profile(self, profile: Optional[Dict], current_text: str) -> List[str]:
        """
        ✨ NEW: Filters user profile traits to find only those relevant to the current conversation context.
        Uses simple keyword matching for MVP (Topic Tracker Light).
        
        Example:
        - Text: "How do I fix this Python bug?"
        - Profile Traits: ["Python Expert", "Loves Cats", "Night Owl"]
        - Result: ["Python Expert"] (Relevance > 0)
        """
        if not profile or not profile.get("attributes"):
            return []
            
        traits = profile["attributes"].get("personality_traits", [])
        if not traits:
            return []
            
        relevant = []
        text_lower = current_text.lower()
        
        for trait in traits:
            name = trait.get("name", "")
            # Simple keyword match: Check if any word from trait name appears in text
            # E.g. Trait "Python Expert" matches text "python bug"
            trait_words = name.lower().split()
            if any(word in text_lower for word in trait_words if len(word) > 3):
                relevant.append(f"{name} (weight={trait.get('weight', 0.5)})")
                
        # If no specific matches, return top 2 dominant traits just in case
        if not relevant and traits:
            # Sort by weight
            sorted_traits = sorted(traits, key=lambda x: x.get("weight", 0.0), reverse=True)
            top_traits = sorted_traits[:2]
            return [f"{t.get('name')} (Dominant)" for t in top_traits]
            
        return relevant

    async def update_user_profile(self, user_id: int, updates: Dict):
        """Service method to update profile"""
        await self.store.update_user_profile(user_id, updates)
