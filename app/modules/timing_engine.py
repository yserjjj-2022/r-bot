# -*- coding: utf-8 -*-
"""
R-Bot Timing Engine - система временных механик с адаптивными countdown сообщениями и Silent Mode

ОБНОВЛЕНИЯ:
06.10.2025 - ДОБАВЛЕНЫ адаптивные countdown сообщения (без технических узлов)
06.10.2025 - Умное форматирование времени (только ненулевые разряды) 
06.10.2025 - Контекстный выбор шаблонов сообщений
06.10.2025 - Удаление кнопок при timeout
06.10.2025 - ДОБАВЛЕН Silent Mode для сценарных timeout'ов
06.10.2025 - ВОССТАНОВЛЕНЫ заглушки для daily/remind/deadline (для будущих спринтов)
30.10.2025 - РЕФАКТОРИНГ к примитивам: добавлена поддержка DynamicPause для typing/process
30.10.2025 - АКТИВИРОВАН progressbar режим для typing команд
30.10.2025 - ПАРСЕР typing теперь поддерживает сообщения с пробелами

DSL команды:
- timeout:15s:no_answer - интерактивный timeout с countdown (если есть кнопки)
- timeout:5s:slow - тихий timeout для драматургии (если есть pause_text)  
- typing:5s:Анализ ваших ответов...:clean - прогресс-бар 5s с preset clean (сообщение с пробелами)
- daily@09:00MSK - ежедневные уведомления (заготовка)
- remind:5m,1h,1d - система напоминаний (заготовка)  
- deadline:2h - дедлайны с предупреждениями (заготовка)
"""

import threading
import time
import re
import logging
from datetime import timedelta, datetime, date
from typing import Dict, Any, Callable, Optional, List, Set

from app.modules.database.models import ActiveTimer, utc_now
from app.modules.database import SessionLocal
from app.modules.timing_primitives.dynamic_pause import DynamicPause

TIMING_ENABLED = True
logger = logging.getLogger(__name__)

# ... остальной файл без изменений до функции _parse_typing ...

    def _parse_typing(self, cmd_str: str) -> Dict[str, Any]:
        """Парсинг typing команд с preset'ами
        Форматы:
          - typing:5s                 → имя по умолчанию
          - typing:5s:Текст          → произвольный текст (можно с пробелами)
          - typing:5s:Текст:preset   → текст + явный preset
        """
        # 1) duration (обязательный)
        m = re.match(r'^typing:(\d+(?:\.\d+)?)s?(?::(.*))?$', cmd_str)
        if not m:
            return None
        duration = float(m.group(1))
        tail = m.group(2) or ''

        process_name = 'Обработка'
        preset = 'clean'

        if tail:
            # Разбиваем только ПЕРВОЕ двоеточие: до него — текст, после — preset (опционально)
            if ':' in tail:
                process_name, preset = tail.split(':', 1)
            else:
                process_name = tail
            process_name = process_name.strip()
            preset = (preset or 'clean').strip()

        preset_config = self.presets.get(preset, self.presets['clean'])
        return {
            'type': 'typing',
            'duration': duration,
            'process_name': process_name,
            'preset': preset,
            'exposure_time': preset_config['exposure_time'],
            'anti_flicker_delay': preset_config['anti_flicker_delay'],
            'action': preset_config['action'],
            'show_progress': True,
            'original': cmd_str
        }

# ... остальной файл без изменений ...