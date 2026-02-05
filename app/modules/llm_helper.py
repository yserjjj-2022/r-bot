import asyncio
import logging
from app.modules.gigachat_handler import get_ai_response

logger = logging.getLogger("LLMHelper")

async def safe_generate_response(agent_name: str, system_prompt: str, user_text: str) -> str:
    """
    Асинхронная обертка над синхронным gigachat_handler.
    Выполняет запрос в отдельном потоке, чтобы не блокировать Event Loop хаба.
    """
    try:
        # Запускаем синхронную функцию в ThreadPoolExecutor
        logger.debug(f"[{agent_name}] Generating response via LLM...")
        
        response = await asyncio.to_thread(
            get_ai_response, 
            user_message=user_text, 
            system_prompt=system_prompt
        )
        
        # Если пришла ошибка (начинается с ⚠️), логируем её, но возвращаем как есть
        if response.startswith("⚠️"):
            logger.warning(f"[{agent_name}] LLM Error: {response}")
            
        return response

    except Exception as e:
        logger.error(f"[{agent_name}] Critical Async LLM Error: {e}", exc_info=True)
        return "⚠️ (System Error) Мозговой модуль временно недоступен."
