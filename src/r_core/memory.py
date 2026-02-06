import uuid
from typing import List, Optional, Dict
from datetime import datetime
import math
from pydantic import BaseModel

# Импортируем наши контракты
from .schemas import (
    SemanticTriple, 
    EpisodicAnchor, 
    VolitionalPattern,
    IncomingMessage
)

# --- Interfaces (Abstractions) ---

class VectorStoreParams(BaseModel):
    """Параметры для поиска в памяти"""
    limit: int = 5
    min_similarity: float = 0.7

class AbstractMemoryStore:
    """
    Интерфейс для хранилища памяти. 
    Позже мы реализуем этот класс для PostgreSQL/pgvector.
    """
    async def save_semantic(self, user_id: int, triple: SemanticTriple):
        raise NotImplementedError
    
    async def save_episodic(self, user_id: int, anchor: EpisodicAnchor):
        raise NotImplementedError
        
    async def save_pattern(self, user_id: int, pattern: VolitionalPattern):
        raise NotImplementedError

    async def search_episodic(self, user_id: int, query_vector: List[float], params: VectorStoreParams) -> List[EpisodicAnchor]:
        raise NotImplementedError
        
    async def search_semantic(self, user_id: int, query_text: str) -> List[SemanticTriple]:
        raise NotImplementedError
        
    async def get_volitional_patterns(self, user_id: int) -> List[VolitionalPattern]:
        raise NotImplementedError

# --- Mock Implementation (In-Memory) ---

class InMemoryStore(AbstractMemoryStore):
    """
    Временное хранилище в RAM для прототипирования.
    Имитирует работу БД.
    """
    def __init__(self):
        # Структура: user_id -> List[Item]
        self._semantic: Dict[int, List[SemanticTriple]] = {}
        self._episodic: Dict[int, List[EpisodicAnchor]] = {}
        self._volitional: Dict[int, List[VolitionalPattern]] = {}

    async def save_semantic(self, user_id: int, triple: SemanticTriple):
        if user_id not in self._semantic:
            self._semantic[user_id] = []
        # Простая проверка на дубликаты
        for existing in self._semantic[user_id]:
            if existing.subject == triple.subject and \
               existing.predicate == triple.predicate and \
               existing.object == triple.object:
                existing.confidence = max(existing.confidence, triple.confidence) # Обновляем уверенность
                return
        self._semantic[user_id].append(triple)
        print(f"[Memory] Semantic fact saved: {triple.subject} {triple.predicate} {triple.object}")

    async def save_episodic(self, user_id: int, anchor: EpisodicAnchor):
        if user_id not in self._episodic:
            self._episodic[user_id] = []
        self._episodic[user_id].append(anchor)
        print(f"[Memory] Episodic anchor saved: '{anchor.raw_text}' (Tags: {anchor.tags})")

    async def save_pattern(self, user_id: int, pattern: VolitionalPattern):
        if user_id not in self._volitional:
            self._volitional[user_id] = []
        self._volitional[user_id].append(pattern)
        print(f"[Memory] Pattern learned: {pattern.trigger} -> {pattern.action_taken}")

    async def search_episodic(self, user_id: int, query_vector: List[float], params: VectorStoreParams) -> List[EpisodicAnchor]:
        # В Mock-версии мы пока игнорируем векторы и возвращаем последние N записей
        # В продакшене тут будет cosine_similarity
        items = self._episodic.get(user_id, [])
        return items[-params.limit:] 

    async def search_semantic(self, user_id: int, query_text: str) -> List[SemanticTriple]:
        # Простой поиск по подстроке
        results = []
        items = self._semantic.get(user_id, [])
        for item in items:
            # Если запрос содержится в объекте или предикате
            if query_text.lower() in item.object.lower() or query_text.lower() in item.predicate.lower():
                results.append(item)
        return results

    async def get_volitional_patterns(self, user_id: int) -> List[VolitionalPattern]:
        return self._volitional.get(user_id, [])

# --- Service Layer ---

class MemorySystem:
    """
    Главная точка входа для работы с памятью в R-Core.
    """
    def __init__(self, store: Optional[AbstractMemoryStore] = None):
        self.store = store or InMemoryStore()

    async def memorize_event(self, message: IncomingMessage, extraction_result: dict):
        """
        Сохраняет результаты работы Perception Layer (извлеченные факты, цитаты, паттерны)
        """
        user_id = message.user_id

        # 1. Сохраняем семантику (Факты)
        for triple_data in extraction_result.get("triples", []):
            triple = SemanticTriple(**triple_data, source_message_id=message.message_id)
            await self.store.save_semantic(user_id, triple)

        # 2. Сохраняем эпизоды (Цитаты)
        for anchor_data in extraction_result.get("anchors", []):
            anchor = EpisodicAnchor(**anchor_data)
            # Тут в будущем: anchor.embedding_ref = await vector_service.embed(anchor.raw_text)
            await self.store.save_episodic(user_id, anchor)

        # 3. Сохраняем волевые паттерны
        if "volitional_pattern" in extraction_result and extraction_result["volitional_pattern"]:
            pattern = VolitionalPattern(**extraction_result["volitional_pattern"])
            await self.store.save_pattern(user_id, pattern)

    async def recall_context(self, user_id: int, current_text: str) -> dict:
        """
        Собирает контекст для LLM (Retrieval)
        """
        # 1. Ищем похожие эпизоды (по вектору - пока заглушка)
        # В реальности тут: query_vec = embed(current_text)
        episodic = await self.store.search_episodic(user_id, [], VectorStoreParams(limit=3))
        
        # 2. Ищем релевантные факты
        semantic = await self.store.search_semantic(user_id, current_text)
        
        # 3. Достаем паттерны поведения
        patterns = await self.store.get_volitional_patterns(user_id)

        return {
            "episodic_memory": [e.dict() for e in episodic],
            "semantic_facts": [s.dict() for s in semantic],
            "known_patterns": [p.dict() for p in patterns]
        }
