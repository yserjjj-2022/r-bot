from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field

class AgentRole(str, Enum):
    BROKER = "BROKER"
    AVATAR = "AVATAR"
    SYSTEM = "SYSTEM"

class AgentProfile(BaseModel):
    """
    Профиль агента (метаданные персонажа).
    Определяет, как агент мыслит и реагирует.
    """
    name: str = Field(..., description="Имя агента (отображаемое пользователю)")
    role: AgentRole = Field(..., description="Роль в архитектуре Хаба")
    
    # Психология
    system_prompt: str = Field(..., description="Основная инструкция (System Prompt) для LLM")
    tone_style: str = Field("neutral", description="Описание тональности (для шаблонизатора или LLM)")
    
    # Настройки срабатывания
    triggers: List[str] = Field(default_factory=list, description="Список триггеров (keywords/events), на которые агент реагирует")
    response_probability: float = Field(1.0, ge=0.0, le=1.0, description="Вероятность ответа (чтобы не спамил на каждый чих)")

    class Config:
        frozen = True # Чтобы нельзя было случайно изменить профиль в рантайме
