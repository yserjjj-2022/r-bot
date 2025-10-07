# -*- coding: utf-8 -*-

"""

R-Bot Timing Engine - ЭТАП 2 ИСПРАВЛЕН: Календарная Daily + правильная логика времени

КРИТИЧЕСКИЕ ИСПРАВЛЕНИЯ:
07.10.2025 - ИСПРАВЛЕНА calculate_next_daily_time(): планирование СЕГОДНЯ если время не прошло
07.10.2025 - ПРАВИЛЬНЫЙ ПУТЬ ИМПОРТА: app.modules.telegram_handler (без .scenarios!)
07.10.2025 - УЛУЧШЕННОЕ ЛОГИРОВАНИЕ: детальные сообщения для отладки времени

ЭТАП 2 ВОЗМОЖНОСТИ:
07.10.2025 - КАЛЕНДАРНАЯ DAILY система (до даты, не по счетчику)
07.10.2025 - WORKDAYS календарь (пропуск выходных + проверка сегодня)  
07.10.2025 - ON_COMPLETE механизм (автозапуск итоговых вопросов)
07.10.2025 - GUARD защита (блокировка узлов до cutoff даты)
07.10.2025 - СТАТИСТИКА участия (автоматическое ведение)
07.10.2025 - БЕЗОПАСНЫЕ FALLBACK (множественные пути импорта)

УНАСЛЕДОВАНО ИЗ ЭТАПА 1 (ПОЛНОСТЬЮ БЕЗ ПОТЕРЬ):
06.10.2025 - ДОБАВЛЕНЫ адаптивные countdown сообщения (без технических узлов)
06.10.2025 - Умное форматирование времени (только ненулевые разряды)
06.10.2025 - Контекстный выбор шаблонов сообщений
06.10.2025 - Удаление кнопок при timeout (исправлено "Ваш ответ: Отлично")
06.10.2025 - ДОБАВЛЕН Silent Mode для сценарных timeout'ов
06.10.2025 - Все preset'ы для контроля экспозиции и anti-flicker
06.10.2025 - Все БД заглушки (готовы к активации в Этапе 3)

DSL КОМАНДЫ ЭТАПА 2:
- daily@21:00:MSK                           - одноразовое (завтра)
- daily@17:00:MSK:until:2025-10-07         - до 7 октября (с планированием сегодня!)
- daily@17:00:MSK:until:2025-10-17:wd      - до 17 октября, рабочие дни
- daily@17:00:MSK:until:2025-10-17:wd>final   - с автопереходом к итогам
- timing:guard:until_date_reached          - защита узлов до cutoff

DSL КОМАНДЫ ИЗ ЭТАПА 1 (ВСЕ СОХРАНЕНЫ):
- timeout:15s:no_answer - интерактивный timeout с countdown (если есть кнопки)
- timeout:5s:slow - тихий timeout для драматургии (если есть pause_text)
- typing:5s:Анализ поведения:clean - прогресс-бар 5s с preset clean
- process:3s:Обработка данных:fast - статический процесс с preset fast
- remind:5m,1h,1d - система напоминаний (заготовка для будущих спринтов)
- deadline:2h - дедлайны с предупреждениями (заготовка для будущих спринтов)

"""

import threading
import time
import re
import logging
from datetime import datetime, timedelta, date
from typing import Dict, Any, Callable, Optional, List, Set
import pytz

# Безопасные импорты БД (заглушки для стабильности в Этапе 2)
try:
    from app.modules.database.models import ActiveTimer, utc_now
    from app.modules.database import SessionLocal
except ImportError:
    print("[TIMING-ENGINE-S2] Database imports not available, using stubs")
    ActiveTimer = None
    def utc_now():
        return datetime.utcnow()
    SessionLocal = None

TIMING_ENABLED = True
logger = logging.getLogger(__name__)

class TimingEngine:
    """
    ЭТАП 2 ИСПРАВЛЕН: Timing Engine с правильной календарной Daily системой, 
    Guard защитой и всеми исправлениями из Этапа 1 (ПОЛНАЯ ВЕРСИЯ БЕЗ ПОТЕРЬ)
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, 'initialized'):
            return

        self.enabled = TIMING_ENABLED
        self.active_timers: Dict[str, threading.Timer] = {}
        self.parsers = self._init_parsers()
        self.executors = self._init_executors()
        self.presets = self._init_presets()

        # Для timeout задач (из Этапа 1 - полностью сохранено)
        self.cancelled_tasks: Set[int] = set()
        self.active_timeouts: Dict[int, threading.Thread] = {}
        self.debug_timers: Dict[int, Dict] = {}

        # Адаптивные шаблоны countdown сообщений (из Этапа 1 - полностью сохранено)
        self.countdown_templates = self._init_countdown_templates()

        # НОВОЕ ЭТАПА 2: Daily календарная система с исправлениями
        self.active_daily_configs: Dict[str, Dict] = {}  # calendar daily configurations
        self.daily_participation_stats: Dict[str, Dict] = {}  # участие по дням
        self.daily_cutoff_dates: Dict[str, date] = {}  # cutoff даты для защиты
        self.workday_calendar = self._init_workdays()  # рабочие дни

        self.initialized = True
        logger.info(f"TimingEngine STAGE2 FIXED initialized with correct time logic. Enabled: {self.enabled}")
        print(f"[TIMING-ENGINE-S2] === ЭТАП 2 ИСПРАВЛЕН: КАЛЕНДАРНАЯ DAILY + ПРАВИЛЬНОЕ ВРЕМЯ ===")
        print(f"[TIMING-ENGINE-S2] Enabled: {self.enabled}")
        print(f"[TIMING-ENGINE-S2] Available presets: {list(self.presets.keys())}")
        print(f"[TIMING-ENGINE-S2] Available commands: {list(self.parsers.keys())}")
        print(f"[TIMING-ENGINE-S2] Adaptive message types: {list(self.countdown_templates.keys())}")
        print(f"[TIMING-ENGINE-S2] Silent Mode: ✅ (из Этапа 1)")
        print(f"[TIMING-ENGINE-S2] Calendar Daily: ✅ (ИСПРАВЛЕНО - планирует сегодня!)") 
        print(f"[TIMING-ENGINE-S2] Workdays Support: ✅ (включая проверку сегодня)")
        print(f"[TIMING-ENGINE-S2] Guard Protection: ✅")
        print(f"[TIMING-ENGINE-S2] Auto Statistics: ✅")
        print(f"[TIMING-ENGINE-S2] Correct Imports: ✅ app.modules.telegram_handler")

        if self.enabled:
            try:
                self.restore_timers_from_db()
                self.cleanup_expired_timers()
            except Exception as e:
                logger.error(f"Failed to restore/cleanup timers on init: {e}")

    # ============================================================================
    # НОВОЕ ЭТАПА 2: КАЛЕНДАРНАЯ DAILY СИСТЕМА С ИСПРАВЛЕНИЯМИ
    # ============================================================================

    def _init_workdays(self) -> Set[int]:
        """НОВОЕ ЭТАПА 2: Инициализация рабочих дней (понедельник=0, воскресенье=6)"""
        return {0, 1, 2, 3, 4}  # пн-пт

    def calculate_next_daily_time(self, hour: int, minute: int, timezone_str: str, 
                                  workdays_only: bool = False) -> Optional[datetime]:
        """
        ИСПРАВЛЕННАЯ ВЕРСИЯ ЭТАПА 2: Расчет следующего времени daily с учетом времени СЕГОДНЯ

        КРИТИЧЕСКОЕ ИСПРАВЛЕНИЕ:
        - Если время daily СЕГОДНЯ еще НЕ прошло → планируем СЕГОДНЯ
        - Если время daily СЕГОДНЯ УЖЕ прошло → планируем ЗАВТРА  
        - С учетом workdays календаря (включая проверку сегодняшнего дня)
        """
        try:
            tz_map = {
                'MSK': 'Europe/Moscow', 'UTC': 'UTC', 'EST': 'US/Eastern',
                'PST': 'US/Pacific', 'CET': 'Europe/Berlin', 'GMT': 'GMT'
            }

            timezone = pytz.timezone(tz_map.get(timezone_str, 'Europe/Moscow'))
            now = datetime.now(timezone)

            # ИСПРАВЛЕНИЕ: Проверяем время СЕГОДНЯ вместо автоматического +1 день
            today_target_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

            print(f"[DAILY-S2] Now: {now}")
            print(f"[DAILY-S2] Target today: {today_target_time}")
            print(f"[DAILY-S2] Time comparison: now < target = {now < today_target_time}")

            # НОВАЯ ЛОГИКА: Если время daily СЕГОДНЯ еще НЕ прошло
            if now < today_target_time:
                print(f"[DAILY-S2] Time has NOT passed today yet!")

                if workdays_only:
                    if today_target_time.weekday() in self.workday_calendar:
                        print(f"[DAILY-S2] ✅ Scheduling for TODAY: {today_target_time} (workday + time available)")
                        return today_target_time
                    else:
                        print(f"[DAILY-S2] Today is not workday ({today_target_time.strftime('%A')}), moving to next workday")
                        # Не рабочий день - ищем следующий рабочий
                        next_workday = today_target_time + timedelta(days=1)
                        while next_workday.weekday() not in self.workday_calendar:
                            next_workday += timedelta(days=1)
                        print(f"[DAILY-S2] Next workday time: {next_workday}")
                        return next_workday
                else:
                    print(f"[DAILY-S2] ✅ Scheduling for TODAY: {today_target_time} (no workdays restriction)")
                    return today_target_time

            # Время СЕГОДНЯ уже прошло - планируем на ЗАВТРА
            print(f"[DAILY-S2] Time already passed today, scheduling for tomorrow or next workday")
            tomorrow = today_target_time + timedelta(days=1)

            # Если нужны только рабочие дни, найти следующий рабочий день
            if workdays_only:
                while tomorrow.weekday() not in self.workday_calendar:
                    tomorrow += timedelta(days=1)
                print(f"[DAILY-S2] Next workday: {tomorrow}")

            print(f"[DAILY-S2] Next daily time: {tomorrow} (workdays_only={workdays_only})")
            return tomorrow

        except Exception as e:
            print(f"[DAILY-S2] Error calculating next daily time: {e}")
            return None
    def _parse_daily(self, cmd_str: str) -> Dict[str, Any]:
        """
        ЭТАП 2: Парсинг календарных daily команд (ОБНОВЛЕНО из заготовки Этапа 1!)

        ПОДДЕРЖИВАЕМЫЕ ФОРМАТЫ:
        daily@21:00:MSK                              → одноразово завтра
        daily@17:00:MSK:until:2025-10-07            → до 7 октября (с планированием сегодня!)
        daily@17:00:MSK:until:2025-10-17:wd         → до 17 октября, рабочие дни
        daily@17:00:MSK:until:2025-10-17:wd>final   → + автопереход к итогам

        ИЗМЕНЕНИЯ ЭТАПА 2:
        - Календарная логика (до конкретной даты, не по счетчику дней)
        - Workdays поддержка (пропуск выходных)
        - On_complete механизм (автозапуск итоговых вопросов)
        - Правильная обработка cutoff дат
        """
        print(f"[DAILY-S2] Parsing daily command: {cmd_str}")

        # Regex для полного парсинга календарной daily (ЭТАП 2)
        pattern = r'^daily@(\d{1,2}):(\d{2})(?::([A-Z]{3}))?(?::until:(\d{4}-\d{2}-\d{2}))?(?::(wd|workdays))?(?:>([^\s]+))?$'
        match = re.match(pattern, cmd_str)

        if match:
            hour = int(match.group(1))
            minute = int(match.group(2))
            timezone_str = match.group(3) or 'MSK'  # дефолт MSK для российских исследований
            until_date_str = match.group(4)  # YYYY-MM-DD или None
            workdays_flag = match.group(5)  # 'wd'/'workdays' или None
            on_complete_node = match.group(6)  # узел для автоперехода или None

            # Парсим дату окончания с безопасной обработкой
            until_date = None
            if until_date_str:
                try:
                    until_date = datetime.strptime(until_date_str, '%Y-%m-%d').date()
                    print(f"[DAILY-S2] Parsed until_date: {until_date}")
                except ValueError:
                    print(f"[DAILY-S2] Invalid until date format: {until_date_str}")
                    return None
            else:
                # Дефолт: завтра (одноразовое daily как в Этапе 1)
                until_date = (datetime.now().date() + timedelta(days=1))
                print(f"[DAILY-S2] Default until_date (tomorrow): {until_date}")

            result = {
                'type': 'daily',
                'hour': hour,
                'minute': minute,
                'timezone': timezone_str,
                'until_date': until_date,
                'workdays_only': bool(workdays_flag),
                'on_complete_node': on_complete_node,
                'original': cmd_str
            }

            print(f"[DAILY-S2] Successfully parsed: {result}")
            return result

        # ОБРАТНАЯ СОВМЕСТИМОСТЬ: Старый формат из заготовки Этапа 1
        old_match = re.match(r'^daily@(\d{2}):(\d{2})([A-Z]{3})?$', cmd_str)
        if old_match:
            print(f"[DAILY-S2] Using legacy format from Stage 1")
            return {
                'type': 'daily',
                'hour': int(old_match.group(1)),
                'minute': int(old_match.group(2)),
                'timezone': old_match.group(3) or 'UTC',
                'until_date': (datetime.now().date() + timedelta(days=1)),  # завтра (как в Этапе 1)
                'workdays_only': False,
                'on_complete_node': None,
                'original': cmd_str
            }

        print(f"[DAILY-S2] Failed to parse daily command: {cmd_str}")
        return None

    def _parse_guard(self, cmd_str: str) -> Dict[str, Any]:
        """
        НОВОЕ ЭТАПА 2: Парсинг guard команд для защиты узлов

        ФОРМАТ: timing:guard:until_date_reached
        ЛОГИКА: Блокирует доступ к узлу до достижения cutoff даты из daily системы
        ПРИМЕНЕНИЕ: Защита итоговых вопросов до завершения исследовательского периода
        """
        if cmd_str.startswith('timing:guard:'):
            condition = cmd_str[13:]  # убираем префикс 'timing:guard:'
            print(f"[GUARD-S2] Parsed guard condition: {condition}")
            return {
                'type': 'guard',
                'condition': condition,
                'original': cmd_str
            }
        print(f"[GUARD-S2] Not a guard command: {cmd_str}")
        return None

    def _execute_daily(self, command: Dict[str, Any], callback: Callable, **context) -> None:
        """
        ЭТАП 2: Исполнитель календарной daily системы (ОБНОВЛЕНО из заготовки Этапа 1!)

        НОВАЯ ЛОГИКА ЭТАПА 2:
        - Календарное планирование (до конкретной даты)
        - Автоматическая статистика участия
        - On_complete механизм для итоговых вопросов
        - Workdays поддержка с проверкой сегодняшнего дня
        - Правильное планирование времени (сегодня/завтра)
        """
        hour = command['hour']
        minute = command['minute']
        timezone_str = command['timezone']
        until_date = command['until_date']
        workdays_only = command.get('workdays_only', False)
        on_complete_node = command.get('on_complete_node')

        session_id = context.get('session_id')

        print(f"[DAILY-S2] === EXECUTING DAILY SYSTEM ===")
        print(f"[DAILY-S2] Daily time: {hour:02d}:{minute:02d} {timezone_str}")
        print(f"[DAILY-S2] Until date: {until_date}")
        print(f"[DAILY-S2] Workdays only: {workdays_only}")
        print(f"[DAILY-S2] On complete node: {on_complete_node}")
        print(f"[DAILY-S2] Session ID: {session_id}")

        # ВАЖНАЯ ПРОВЕРКА: Не истекла ли cutoff дата ДО планирования
        current_date = datetime.now().date()
        print(f"[DAILY-S2] Current date: {current_date}")
        print(f"[DAILY-S2] Cutoff comparison: {current_date} > {until_date} = {current_date > until_date}")

        if current_date > until_date:
            print(f"[DAILY-S2] ❌ Daily period expired: {current_date} > {until_date}")
            # Если есть on_complete и время пришло → запускаем итоговые вопросы
            if on_complete_node:
                print(f"[DAILY-S2] 🎯 Triggering on_complete immediately: {on_complete_node}")
                self._trigger_on_complete(on_complete_node, **context)
            return

        # НОВОЕ: Проверяем, можем ли мы еще запланировать daily НА СЕГОДНЯ
        current_time = datetime.now(pytz.timezone('Europe/Moscow' if timezone_str == 'MSK' else 'UTC'))
        today_target = current_time.replace(hour=hour, minute=minute, second=0, microsecond=0)

        print(f"[DAILY-S2] Current time: {current_time}")
        print(f"[DAILY-S2] Today target: {today_target}")
        print(f"[DAILY-S2] Can schedule today: {current_time < today_target}")

        # Создаем daily конфигурацию
        daily_key = f"daily_{session_id}_{hour}_{minute}_{timezone_str}"
        daily_config = {
            'session_id': session_id,
            'hour': hour,
            'minute': minute,
            'timezone': timezone_str,
            'until_date': until_date,
            'workdays_only': workdays_only,
            'on_complete_node': on_complete_node,
            'start_date': current_date,
            'callback': callback
        }

        self.active_daily_configs[daily_key] = daily_config
        self.daily_cutoff_dates[daily_key] = until_date

        # Инициализируем статистику участия
        stats_key = f"stats_{session_id}_{hour}_{minute}"
        if stats_key not in self.daily_participation_stats:
            self.daily_participation_stats[stats_key] = {
                'total_days': 0,
                'participated_days': 0,
                'start_date': current_date,
                'until_date': until_date,
                'workdays_only': workdays_only
            }
            print(f"[DAILY-S2] ✅ Initialized participation stats: {stats_key}")

        # ВАЖНО: Выполняем callback немедленно при инициализации (как настройка daily)
        print(f"[DAILY-S2] 🎯 Executing immediate callback for daily setup")
        try:
            callback()
        except Exception as e:
            print(f"[DAILY-S2] Error in immediate callback: {e}")

        # Планируем следующий daily (с исправленной логикой времени)
        print(f"[DAILY-S2] 📅 Scheduling next daily execution...")
        self.schedule_next_daily_calendar(daily_key, daily_config, **context)

    def schedule_next_daily_calendar(self, daily_key: str, daily_config: Dict, **context):
        """
        НОВОЕ ЭТАПА 2: Календарное планирование daily (до cutoff даты) с правильной логикой времени

        ИСПРАВЛЕНИЯ:
        - Правильный расчет времени (сегодня/завтра)
        - Проверка workdays для текущего дня
        - Корректная обработка cutoff даты
        - Автозапуск on_complete при завершении
        """
        hour = daily_config['hour']
        minute = daily_config['minute']
        timezone_str = daily_config['timezone']
        until_date = daily_config['until_date']
        workdays_only = daily_config['workdays_only']
        on_complete_node = daily_config['on_complete_node']
        callback = daily_config['callback']

        print(f"[DAILY-S2] === SCHEDULING NEXT DAILY: {daily_key} ===")

        # ИСПРАВЛЕННЫЙ расчет времени (может быть сегодня!)
        next_time = self.calculate_next_daily_time(hour, minute, timezone_str, workdays_only)
        if not next_time:
            print(f"[DAILY-S2] ❌ Failed to calculate next time for {daily_key}")
            return

        # Проверяем календарную отсечку
        next_date = next_time.date()
        print(f"[DAILY-S2] Next execution date: {next_date}")
        print(f"[DAILY-S2] Cutoff date: {until_date}")
        print(f"[DAILY-S2] Cutoff check: {next_date} > {until_date} = {next_date > until_date}")

        if next_date > until_date:
            print(f"[DAILY-S2] 🏁 Cutoff reached: {next_date} > {until_date}")
            print(f"[DAILY-S2] Daily cycle completed for {daily_key}")

            # Запускаем on_complete если есть
            if on_complete_node:
                print(f"[DAILY-S2] 🎯 Scheduling on_complete with delay: {on_complete_node}")
                # Небольшая задержка для "по горячему" эффекта (UX)
                threading.Timer(2.0, lambda: self._trigger_on_complete(on_complete_node, **context)).start()

            # Удаляем из активных конфигураций (цикл завершен)
            self.active_daily_configs.pop(daily_key, None)
            print(f"[DAILY-S2] ✅ Removed completed daily config: {daily_key}")
            return

        # Вычисляем задержку до следующего срабатывания с timezone корректировкой
        now_utc = datetime.now(pytz.UTC)
        next_time_utc = next_time.astimezone(pytz.UTC)
        delay_seconds = (next_time_utc - now_utc).total_seconds()

        print(f"[DAILY-S2] 🕐 Scheduling next daily: {next_time} (in {delay_seconds:.1f} seconds)")

        # ЗАЩИТА: Минимальная задержка 1 секунда
        if delay_seconds < 1:
            delay_seconds = 1
            print(f"[DAILY-S2] ⚠️ Adjusted delay to minimum: {delay_seconds} seconds")

        def daily_timer_callback():
            """Callback для ежедневного срабатывания daily"""
            try:
                print(f"[DAILY-S2] 🔥 Daily timer fired: {daily_key}")
                print(f"[DAILY-S2] Execution time: {datetime.now()}")

                # Обновляем статистику участия
                self._update_daily_stats(daily_key, participated=True)

                # ДВОЙНАЯ ПРОВЕРКА cutoff даты (на всякий случай)
                execution_date = datetime.now().date()
                print(f"[DAILY-S2] Execution date check: {execution_date} <= {until_date} = {execution_date <= until_date}")

                if execution_date <= until_date:
                    print(f"[DAILY-S2] ✅ Executing daily callback (within cutoff period)")
                    # Выполняем callback для ежедневных вопросов
                    try:
                        callback()
                    except Exception as cb_error:
                        print(f"[DAILY-S2] ❌ Callback execution error: {cb_error}")

                    # Планируем следующий daily (если конфигурация еще активна)
                    if daily_key in self.active_daily_configs:
                        print(f"[DAILY-S2] 📅 Planning next daily iteration...")
                        self.schedule_next_daily_calendar(daily_key, daily_config, **context)
                    else:
                        print(f"[DAILY-S2] ⚠️ Daily config removed, not scheduling next iteration")
                else:
                    print(f"[DAILY-S2] ❌ Daily expired during execution: {execution_date} > {until_date}")
                    if on_complete_node:
                        print(f"[DAILY-S2] 🎯 Triggering on_complete due to expiration: {on_complete_node}")
                        self._trigger_on_complete(on_complete_node, **context)

            except Exception as e:
                print(f"[DAILY-S2] ❌ Daily timer callback error: {e}")
                logger.error(f"Daily timer callback error for {daily_key}: {e}")

        # Создаем и запускаем Timer с рассчитанной задержкой
        print(f"[DAILY-S2] 🚀 Creating timer with {delay_seconds:.1f}s delay")
        timer = threading.Timer(delay_seconds, daily_timer_callback)
        timer.start()
        self.active_timers[daily_key] = timer
        print(f"[DAILY-S2] ✅ Timer started and registered: {daily_key}")

    def _trigger_on_complete(self, on_complete_node: str, **context):
        """
        ИСПРАВЛЕННАЯ ВЕРСИЯ ЭТАПА 2: Безопасный запуск on_complete узлов 
        с правильными импортами и множественными fallback

        ИСПРАВЛЕНИЯ:
        - ПРАВИЛЬНЫЙ ПУТЬ: app.modules.telegram_handler (без .scenarios!)
        - Расширенные fallback с детальным логированием
        - Персонализированные сообщения с статистикой
        - Graceful деградация при любых проблемах
        """
        print(f"[DAILY-S2] === TRIGGERING ON_COMPLETE NODE ===")
        print(f"[DAILY-S2] Target node: {on_complete_node}")

        bot = context.get('bot')
        chat_id = context.get('chat_id')

        if not bot or not chat_id:
            print(f"[DAILY-S2] ❌ Cannot trigger on_complete: missing bot={bool(bot)} chat_id={bool(chat_id)}")
            return

        # Получаем статистику для персонализации сообщения
        session_id = context.get('session_id')
        stats = self._get_daily_stats_summary(session_id)

        # Красивое уведомление о переходе с персонализацией
        participation_text = f"{stats['participated_days']} из {stats['total_days']} дней" if stats['total_days'] > 0 else "весь период"
        transition_msg = f"🎉 Исследовательский период завершен!\n\n📊 Ваше участие: {participation_text}\n\n🔄 Переходим к итоговым вопросам..."

        try:
            print(f"[DAILY-S2] 📨 Sending transition message...")
            bot.send_message(chat_id, transition_msg)

            # Небольшая пауза для восприятия пользователем
            print(f"[DAILY-S2] ⏳ Waiting 2s for user comprehension...")
            time.sleep(2)

            # ИСПРАВЛЕННЫЕ ИМПОРТЫ: Множественные попытки с правильными путями
            success = False

            # Попытка 1: ПРАВИЛЬНЫЙ путь (найден в existing R-Bot коде!)
            if not success:
                try:
                    print(f"[DAILY-S2] 🔄 Attempting standard import path...")
                    from app.modules.telegram_handler import send_node_message
                    send_node_message(chat_id, on_complete_node, context)
                    print(f"[DAILY-S2] ✅ SUCCESS via correct path: {on_complete_node}")
                    success = True
                except ImportError as e:
                    print(f"[DAILY-S2] ❌ Standard path import failed: {e}")
                except Exception as e:
                    print(f"[DAILY-S2] ❌ Standard path execution error: {e}")

            # Попытка 2: Альтернативный путь (без app prefix)
            if not success:
                try:
                    print(f"[DAILY-S2] 🔄 Attempting alternative import path...")
                    from telegram_handler import send_node_message
                    send_node_message(chat_id, on_complete_node, context)
                    print(f"[DAILY-S2] ✅ SUCCESS via alternative path: {on_complete_node}")
                    success = True
                except ImportError as e:
                    print(f"[DAILY-S2] ❌ Alternative path import failed: {e}")
                except Exception as e:
                    print(f"[DAILY-S2] ❌ Alternative path execution error: {e}")

            # Попытка 3: Прямой путь (modules.telegram_handler)
            if not success:
                try:
                    print(f"[DAILY-S2] 🔄 Attempting direct modules path...")
                    from modules.telegram_handler import send_node_message
                    send_node_message(chat_id, on_complete_node, context)
                    print(f"[DAILY-S2] ✅ SUCCESS via direct path: {on_complete_node}")
                    success = True
                except ImportError as e:
                    print(f"[DAILY-S2] ❌ Direct path import failed: {e}")
                except Exception as e:
                    print(f"[DAILY-S2] ❌ Direct path execution error: {e}")

            # Попытка 4: Bot method (если существует)
            if not success:
                try:
                    print(f"[DAILY-S2] 🔄 Attempting bot method...")
                    if hasattr(bot, 'send_node_message'):
                        bot.send_node_message(chat_id, on_complete_node, context)
                        print(f"[DAILY-S2] ✅ SUCCESS via bot method: {on_complete_node}")
                        success = True
                    else:
                        print(f"[DAILY-S2] ❌ Bot does not have send_node_message method")
                except Exception as e:
                    print(f"[DAILY-S2] ❌ Bot method execution error: {e}")

            # GRACEFUL FALLBACK: Понятные инструкции пользователю
            if not success:
                print(f"[DAILY-S2] ⚠️ All import attempts failed, using graceful fallback")
                fallback_msg = f"🔄 Для перехода к итоговым вопросам:\n\n📋 Выберите удобный способ:\n\n1️⃣ Отправьте команду /start\n2️⃣ Найдите узел '{on_complete_node}' в сценарии\n3️⃣ Обратитесь к администратору\n\n💡 Это техническая проблема, данные сохранены"
                try:
                    bot.send_message(chat_id, fallback_msg)
                    print(f"[DAILY-S2] ✅ Fallback message sent successfully")
                except Exception as fallback_error:
                    print(f"[DAILY-S2] ❌ Even fallback message failed: {fallback_error}")

        except Exception as e:
            print(f"[DAILY-S2] ❌ Critical error in _trigger_on_complete: {e}")
            logger.error(f"Critical error in _trigger_on_complete: {e}")

            # ПОСЛЕДНИЙ fallback - базовое сообщение об ошибке
            try:
                error_msg = "⚠️ Произошла техническая ошибка при переходе к итоговым вопросам.\n\n🔄 Для продолжения:\n• Отправьте /start\n• Обратитесь к администратору\n\nВаши данные сохранены ✅"
                bot.send_message(chat_id, error_msg) 
                print(f"[DAILY-S2] ✅ Final fallback message sent")
            except Exception as final_error:
                print(f"[DAILY-S2] ❌ Even final fallback failed: {final_error}")

    def _execute_guard(self, command: Dict[str, Any], callback: Callable, **context) -> None:
        """
        НОВОЕ ЭТАПА 2: Исполнитель Guard защиты узлов

        ЛОГИКА:
        - Проверяет условие (until_date_reached)
        - Если условие выполнено → разрешает доступ (выполняет callback)
        - Если условие НЕ выполнено → ТИХО блокирует доступ (НЕ выполняет callback)
        - НЕ отправляет сообщения пользователю (silent guard)

        ПРИМЕНЕНИЕ: Защита итоговых вопросов до завершения daily периода
        """
        condition = command.get('condition')
        session_id = context.get('session_id')

        print(f"[GUARD-S2] === CHECKING GUARD CONDITION ===")
        print(f"[GUARD-S2] Condition: {condition}")
        print(f"[GUARD-S2] Session ID: {session_id}")

        if condition == 'until_date_reached':
            cutoff_reached = self._is_daily_cutoff_reached(session_id)
            print(f"[GUARD-S2] Cutoff date reached: {cutoff_reached}")

            if cutoff_reached:
                print(f"[GUARD-S2] ✅ Guard PASSED - cutoff date reached, allowing access")
                try:
                    callback()  # Доступ разрешен - выполняем узел
                except Exception as e:
                    print(f"[GUARD-S2] ❌ Callback execution error: {e}")
            else:
                print(f"[GUARD-S2] 🔒 Guard BLOCKED - cutoff date not reached (silent block)")
                # ТИХАЯ блокировка - НЕ отправляем сообщение пользователю
                # Просто не выполняем callback - пользователь не увидит узел
                pass
        else:
            print(f"[GUARD-S2] ⚠️ Unknown guard condition: {condition}")
            print(f"[GUARD-S2] 🔄 Allowing access for unknown condition (safe fallback)")
            callback()  # Пропускаем при неизвестном условии (безопасный fallback)

    def _is_daily_cutoff_reached(self, session_id: int) -> bool:
        """
        НОВОЕ ЭТАПА 2: Проверка достижения cutoff даты для конкретной session

        ЛОГИКА:
        - Ищет cutoff дату среди активных daily конфигураций для данной сессии
        - Сравнивает текущую дату с cutoff датой
        - Возвращает True если cutoff достигнут или превышен
        - Дефолт True если cutoff дата не найдена (разрешительная политика)
        """
        current_date = datetime.now().date()

        print(f"[GUARD-S2] Checking cutoff for session {session_id}")
        print(f"[GUARD-S2] Current date: {current_date}")

        # Ищем cutoff дату для этой сессии среди активных daily конфигураций
        for daily_key, cutoff_date in self.daily_cutoff_dates.items():
            if f"_{session_id}_" in daily_key:
                result = current_date > cutoff_date
                print(f"[GUARD-S2] Found cutoff for session {session_id}: {cutoff_date}")
                print(f"[GUARD-S2] Cutoff comparison: {current_date} > {cutoff_date} = {result}")
                return result

        # Если cutoff дата не найдена - разрешительная политика
        print(f"[GUARD-S2] No cutoff date found for session {session_id} - allowing access (permissive)")
        return True

    def _update_daily_stats(self, daily_key: str, participated: bool):
        """
        НОВОЕ ЭТАПА 2: Обновление статистики участия в daily исследовании

        ЛОГИКА:
        - Извлекает session_id из daily_key
        - Обновляет счетчики участия
        - Ведет статистику для персонализации итоговых сообщений
        """
        try:
            # Извлекаем session_id из daily_key формата "daily_SESSION_HOUR_MINUTE_TIMEZONE"
            parts = daily_key.split('_')
            if len(parts) >= 4:
                session_id = int(parts[1])
                hour = int(parts[2])
                minute = int(parts[3])

                stats_key = f"stats_{session_id}_{hour}_{minute}"
                print(f"[DAILY-S2] Updating stats: {stats_key}")

                if stats_key in self.daily_participation_stats:
                    stats = self.daily_participation_stats[stats_key]
                    stats['total_days'] += 1
                    if participated:
                        stats['participated_days'] += 1

                    participation_rate = (stats['participated_days'] / stats['total_days']) * 100
                    print(f"[DAILY-S2] ✅ Stats updated: {stats['participated_days']}/{stats['total_days']} ({participation_rate:.1f}%)")

                    # Дополнительная аналитика для исследований
                    current_date = datetime.now().date()
                    days_since_start = (current_date - stats['start_date']).days
                    days_until_end = (stats['until_date'] - current_date).days

                    print(f"[DAILY-S2] 📊 Research progress: Day {days_since_start + 1}, {days_until_end} days remaining")
                else:
                    print(f"[DAILY-S2] ⚠️ Stats key not found: {stats_key}")
        except Exception as e:
            print(f"[DAILY-S2] ❌ Error updating daily stats: {e}")

    def _get_daily_stats_summary(self, session_id: int) -> Dict[str, Any]:
        """
        НОВОЕ ЭТАПА 2: Получение сводки статистики участия для персонализации

        ВОЗВРАТ: Словарь с данными участия для использования в сообщениях
        """
        print(f"[DAILY-S2] Getting stats summary for session {session_id}")

        for stats_key, stats in self.daily_participation_stats.items():
            if f"stats_{session_id}_" in stats_key:
                participation_rate = (stats['participated_days'] / stats['total_days'] * 100) if stats['total_days'] > 0 else 0
                summary = {
                    'total_days': stats['total_days'],
                    'participated_days': stats['participated_days'],
                    'participation_rate': round(participation_rate, 1),
                    'start_date': stats['start_date'],
                    'until_date': stats['until_date'],
                    'workdays_only': stats.get('workdays_only', False)
                }
                print(f"[DAILY-S2] ✅ Found stats: {summary}")
                return summary

        # Дефолтные значения если статистика не найдена
        default_summary = {
            'total_days': 0,
            'participated_days': 0,
            'participation_rate': 0,
            'start_date': datetime.now().date(),
            'until_date': datetime.now().date()
        }
        print(f"[DAILY-S2] ⚠️ Using default stats: {default_summary}")
        return default_summary
    # ============================================================================
    # ВСЕ ИЗ ЭТАПА 1 - ПОЛНОСТЬЮ БЕЗ ИЗМЕНЕНИЙ И СОКРАЩЕНИЙ
    # ============================================================================

    def _init_countdown_templates(self) -> Dict[str, Dict[str, str]]:
        """
        Инициализация адаптивных шаблонов countdown сообщений (ЭТАП 1)

        НОВАЯ ВОЗМОЖНОСТЬ ЭТАПА 1:
        - Контекстные сообщения в зависимости от типа взаимодействия
        - Персонализированные формулировки для разных сценариев
        - Поддержка эмоциональной окраски сообщений

        ТИПЫ СООБЩЕНИЙ:
        - urgent: для критически важных действий (≤5с)
        - choice: для выбора вариантов (≤15с)
        - decision: для принятия решений (≤60с)
        - answer: для ответов на вопросы
        - gentle: для размышлений и мягких взаимодействий
        - generic: универсальный fallback
        """
        return {
            'urgent': {
                'countdown': "🚨 Внимание! Осталось: {time}",
                'final': "🚨 Время истекло!"
            },
            'choice': {
                'countdown': "⏳ Выбор нужно сделать через: {time}",
                'final': "⏰ Время выбора истекло"
            },
            'decision': {
                'countdown': "⏳ На принятие решения осталось: {time}",
                'final': "⏰ Время принятия решения истекло"
            },
            'answer': {
                'countdown': "⏳ Время на ответ: {time}",
                'final': "⏰ Время на ответ истекло"
            },
            'gentle': {
                'countdown': "💭 Время поделиться мыслями: {time}",
                'final': "💭 Время для размышлений истекло"
            },
            'generic': {
                'countdown': "⏰ Осталось времени: {time}",
                'final': "⏰ Время истекло"
            }
        }

    def format_countdown_time(self, seconds: int) -> str:
        """
        Форматирует время для countdown в человекочитаемый вид (ЭТАП 1)

        УМНЫЕ ВОЗМОЖНОСТИ:
        - Показывает только ненулевые разряды времени
        - Правильные русские окончания (час/часа/часов)
        - Автоматическое сокращение для коротких периодов
        - Graceful обработка нулевых и отрицательных значений

        ПРИМЕРЫ:
        - 3661 → "1 час 1 минуту 1 секунду"  
        - 125 → "2 минуты 5 секунд"
        - 45 → "45 секунд"
        - 0 → "время истекло"
        """
        if seconds <= 0:
            return "время истекло"

        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        parts = []

        # Форматирование часов с правильными окончаниями
        if hours > 0:
            if hours == 1:
                form = "час"
            elif 2 <= hours <= 4:
                form = "часа" 
            else:
                form = "часов"
            parts.append(f"{hours} {form}")

        # Форматирование минут с правильными окончаниями
        if minutes > 0:
            if minutes == 1:
                form = "минуту"
            elif 2 <= minutes <= 4:
                form = "минуты"
            else:
                form = "минут"
            parts.append(f"{minutes} {form}")

        # Форматирование секунд с правильными окончаниями
        if secs > 0 or not parts:  # Показываем секунды если это единственная единица
            if secs == 1:
                form = "секунду"
            elif 2 <= secs <= 4:
                form = "секунды"
            else:
                form = "секунд"
            parts.append(f"{secs} {form}")

        return " ".join(parts)

    def get_countdown_message_type(self, duration: int, node_id: str = "", node_text: str = "") -> str:
        """
        Адаптивный выбор типа countdown сообщения по контексту (ЭТАП 1)

        АЛГОРИТМ ВЫБОРА:
        1. Базовый тип по длительности timeout
        2. Переопределение по node_id (если содержит ключевые слова)  
        3. Переопределение по содержанию текста узла
        4. Fallback к базовому типу

        КОНТЕКСТНАЯ АДАПТАЦИЯ:
        - Технические узлы → более нейтральные сообщения
        - Эмоциональные узлы → более мягкие формулировки  
        - Тестовые узлы → акцент на ответы
        - Timing узлы → акцент на скорость реакции
        """
        # Правило 1: Базовый тип по длительности timeout
        if duration <= 5:
            base_type = "urgent"      # Критически важные действия
        elif duration <= 15:
            base_type = "choice"      # Быстрые выборы
        elif duration <= 60:
            base_type = "decision"    # Обдуманные решения
        else:
            base_type = "gentle"      # Размышления

        # Правило 2: Переопределение по node_id (анализ названия узла)
        if node_id:
            node_lower = node_id.lower()
            # Узлы тестирования и вопросов
            if any(keyword in node_lower for keyword in ['test', 'quiz', 'question', 'answer']):
                return "answer"
            # Узлы реакции и скорости
            elif any(keyword in node_lower for keyword in ['timing', 'speed', 'reaction', 'fast']):
                return "choice"
            # Узлы завершения и итогов
            elif any(keyword in node_lower for keyword in ['complete', 'final', 'end']):
                return "gentle"

        # Правило 3: Переопределение по содержанию текста узла
        if node_text:
            text_lower = node_text.lower()
            # Эмоциональные вопросы
            if any(word in text_lower for word in ['настроение', 'чувство', 'ощущение', 'эмоция']):
                return "gentle"
            # Срочные действия  
            elif any(word in text_lower for word in ['быстро', 'срочно', 'скорее', 'немедленно']):
                return "urgent"
            # Тесты и вопросы
            elif any(word in text_lower for word in ['тест', 'вопрос', 'ответ', 'выбор']):
                return "answer"

        return base_type

    def should_show_countdown(self, context: dict) -> bool:
        """
        НОВОЕ ЭТАПА 1: Определяет режим timeout (Silent/Interactive)

        ЛОГИКА SILENT MODE:
        - pause_text заполнен → ТИХИЙ timeout (сценарная пауза)
        - Есть кнопки И НЕТ pause_text → ИНТЕРАКТИВНЫЙ timeout (countdown)  
        - НЕТ кнопок И НЕТ pause_text → ТИХИЙ timeout

        ПРИМЕНЕНИЕ:
        - Интерактивные timeout показывают countdown с кнопками
        - Сценарные timeout тихо ждут для драматического эффекта
        """
        pause_text = context.get('pause_text', '').strip()
        has_pause_text = bool(pause_text)
        buttons = context.get('buttons', [])
        has_buttons = len(buttons) > 0

        print(f"[TIMING-ENGINE-S2] === SILENT MODE CHECK ===")
        print(f"[TIMING-ENGINE-S2] pause_text length: {len(pause_text)}")
        print(f"[TIMING-ENGINE-S2] pause_text preview: '{pause_text[:30]}{'...' if len(pause_text) > 30 else ''}'")
        print(f"[TIMING-ENGINE-S2] has_buttons: {has_buttons} (count: {len(buttons)})")
        print(f"[TIMING-ENGINE-S2] has_pause_text: {has_pause_text}")

        # ПРАВИЛО: Показывать countdown только для интерактивных timeout'ов
        show_countdown = has_buttons and not has_pause_text
        mode = "INTERACTIVE" if show_countdown else "SILENT"
        print(f"[TIMING-ENGINE-S2] Determined mode: {mode}")

        return show_countdown

    def _init_presets(self) -> Dict[str, Dict[str, Any]]:
        """
        Инициализация preset'ов для контроля экспозиции и anti-flicker (ЭТАП 1)

        PRESET СИСТЕМА:
        - Контроль времени показа результата (exposure_time)
        - Anti-flicker задержка между операциями
        - Действие с сообщением после показа (delete/keep)
        - Описания для документации и отладки

        ПРИМЕНЕНИЕ:
        - typing и process команды используют preset'ы для UX
        - Предотвращение мерцания интерфейса
        - Контроль визуального потока в диалоге
        """
        return {
            'clean': {
                'exposure_time': 1.5,      # Показать результат 1.5 секунды
                'anti_flicker_delay': 1.0, # Пауза перед удалением 1 секунда
                'action': 'delete',        # Удалить сообщение
                'description': 'Стандарт: показать результат 1.5с, пауза 1с, удалить'
            },
            'keep': {
                'exposure_time': 0,        # Не ждать
                'anti_flicker_delay': 0.5, # Минимальная пауза
                'action': 'keep',          # Оставить в ленте
                'description': 'Оставить в ленте навсегда с минимальной паузой'
            },
            'fast': {
                'exposure_time': 0.8,      # Быстро показать
                'anti_flicker_delay': 0.5, # Быстро убрать
                'action': 'delete',
                'description': 'Быстро: показать 0.8с, пауза 0.5с, удалить'
            },
            'slow': {
                'exposure_time': 3.0,      # Долго показать
                'anti_flicker_delay': 2.0, # Долго ждать
                'action': 'delete',
                'description': 'Медленно: показать 3с, пауза 2с, удалить (для драматургии)'
            },
            'instant': {
                'exposure_time': 0,        # Мгновенно
                'anti_flicker_delay': 0,   # Без пауз
                'action': 'delete',        # Сразу удалить
                'description': 'Мгновенно: сразу удалить без показа (техническое)'
            }
        }

    @classmethod
    def get_instance(cls):
        """Получить singleton экземпляр TimingEngine"""
        return cls()
    # ============================================================================
    # INIT МЕТОДЫ (ОБНОВЛЕНЫ ДЛЯ ЭТАПА 2)
    # ============================================================================

    def _init_parsers(self) -> Dict[str, Any]:
        """
        Инициализация парсеров DSL команд (Этап 1 + обновления Этапа 2)

        ПАРСЕРЫ ЭТАПА 1 (полностью сохранены):
        - basic_pause: простые паузы (5s, 10.5s)
        - typing: прогресс-бары с preset'ами
        - process: статические процессы (замена state: true)
        - timeout: универсальные timeout'ы с countdown

        НОВЫЕ ПАРСЕРЫ ЭТАПА 2:
        - daily: календарная daily система (ОБНОВЛЕНО из заготовки!)
        - guard: защита узлов до cutoff даты

        ЗАГОТОВКИ ДЛЯ БУДУЩИХ СПРИНТОВ (из Этапа 1):
        - remind: система напоминаний (remind:5m,1h,1d)
        - deadline: дедлайны с предупреждениями (deadline:2h)
        """
        return {
            'basic_pause': self._parse_basic_pause,    # ЭТАП 1
            'typing': self._parse_typing,              # ЭТАП 1
            'process': self._parse_process,            # ЭТАП 1
            'timeout': self._parse_timeout,            # ЭТАП 1
            'daily': self._parse_daily,                # ЭТАП 2 (обновлено!)
            'guard': self._parse_guard,                # ЭТАП 2 (новое!)
            'remind': self._parse_remind,              # Заготовка для Этапа 3+
            'deadline': self._parse_deadline           # Заготовка для Этапа 3+
        }

    def _init_executors(self) -> Dict[str, Any]:
        """
        Инициализация исполнителей команд (Этап 1 + обновления Этапа 2)

        ИСПОЛНИТЕЛИ ЭТАПА 1 (полностью сохранены):
        - pause: простые паузы с callback
        - typing: прогресс-бары с визуализацией
        - process: статические процессы
        - timeout: интерактивные/silent timeout'ы

        НОВЫЕ ИСПОЛНИТЕЛИ ЭТАПА 2:
        - daily: календарная daily система (ОБНОВЛЕНО из заготовки!)
        - guard: guard защита узлов

        ЗАГОТОВКИ ДЛЯ БУДУЩИХ СПРИНТОВ (из Этапа 1):
        - remind: исполнитель напоминаний
        - deadline: исполнитель дедлайнов
        """
        return {
            'pause': self._execute_pause,              # ЭТАП 1
            'typing': self._execute_typing,            # ЭТАП 1
            'process': self._execute_process,          # ЭТАП 1
            'timeout': self._execute_timeout,          # ЭТАП 1
            'daily': self._execute_daily,              # ЭТАП 2 (обновлено!)
            'guard': self._execute_guard,              # ЭТАП 2 (новое!)
            'remind': self._execute_remind,            # Заготовка для Этапа 3+
            'deadline': self._execute_deadline         # Заготовка для Этапа 3+
        }

    # ============================================================================
    # DSL ПАРСЕРЫ - ВСЕ ИЗ ЭТАПА 1 БЕЗ ИЗМЕНЕНИЙ И СОКРАЩЕНИЙ
    # ============================================================================

    def _parse_basic_pause(self, cmd_str: str) -> Dict[str, Any]:
        """
        Парсинг простых пауз (ЭТАП 1)

        ФОРМАТЫ:
        - 5 → пауза 5 секунд
        - 10s → пауза 10 секунд  
        - 3.5s → пауза 3.5 секунды

        ОБРАТНАЯ СОВМЕСТИМОСТЬ: Поддержка старого формата простых чисел
        """
        match = re.match(r'^\d+(\.\d+)?(s)?$', cmd_str)
        if match:
            duration = float(cmd_str.replace('s', ''))
            print(f"[TIMING-ENGINE-S2] Parsed basic pause: {duration}s")
            return {
                'type': 'pause', 
                'duration': duration, 
                'process_name': 'Пауза', 
                'original': cmd_str
            }
        return None

    def _parse_typing(self, cmd_str: str) -> Dict[str, Any]:
        """
        Парсинг typing команд с preset'ами (ЭТАП 1)

        ФОРМАТЫ:
        - typing:5s → прогресс-бар 5с с preset 'clean'
        - typing:3s:Анализ данных → прогресс-бар с кастомным текстом
        - typing:5s:Обработка:fast → прогресс-бар с preset 'fast'

        PRESET ИНТЕГРАЦИЯ:
        - Автоматически применяет настройки exposure и anti-flicker
        - Поддержка кастомных названий процессов
        - Fallback к preset 'clean' при отсутствии
        """
        pattern = r'^typing:(\d+(?:\.\d+)?)s?(?::([^:]+))?(?::([^:]+))?$'
        match = re.match(pattern, cmd_str)

        if match:
            duration = float(match.group(1))
            process_name = match.group(2) if match.group(2) else "Обработка"
            preset = match.group(3) if match.group(3) else 'clean'

            # Получаем конфигурацию preset'а
            preset_config = self.presets.get(preset, self.presets['clean'])

            print(f"[TIMING-ENGINE-S2] Parsed typing: {duration}s '{process_name}' preset:{preset}")

            return {
                'type': 'typing',
                'duration': duration,
                'process_name': process_name,
                'preset': preset,
                'exposure_time': preset_config['exposure_time'],
                'anti_flicker_delay': preset_config['anti_flicker_delay'],
                'action': preset_config['action'],
                'show_progress': True,  # typing всегда показывает прогресс
                'original': cmd_str
            }
        return None

    def _parse_process(self, cmd_str: str) -> Dict[str, Any]:
        """
        Парсинг process команд - замена для state: true (ЭТАП 1)

        ФОРМАТЫ:
        - process:3s:Сохранение данных → статический процесс 3с
        - process:5s:Анализ:keep → процесс с preset 'keep' (остается в ленте)

        ОТЛИЧИЕ ОТ TYPING:
        - process: статическое сообщение без анимации прогресса
        - typing: анимированный прогресс-бар с процентами

        ПРИМЕНЕНИЕ: Замена старых state: true для UX улучшения
        """
        pattern = r'^process:(\d+(?:\.\d+)?)s?:([^:]+)(?::([^:]+))?$'
        match = re.match(pattern, cmd_str)

        if match:
            duration = float(match.group(1))
            process_name = match.group(2)
            preset = match.group(3) if match.group(3) else 'clean'

            # Получаем конфигурацию preset'а
            preset_config = self.presets.get(preset, self.presets['clean'])

            print(f"[TIMING-ENGINE-S2] Parsed process: {duration}s '{process_name}' preset:{preset}")

            return {
                'type': 'process',
                'duration': duration,
                'process_name': process_name,
                'preset': preset,
                'exposure_time': preset_config['exposure_time'],
                'anti_flicker_delay': preset_config['anti_flicker_delay'],
                'action': preset_config['action'],
                'show_progress': False,  # process НЕ показывает анимацию
                'original': cmd_str
            }
        return None

    def _parse_timeout(self, cmd_str: str) -> Dict[str, Any]:
        """
        Парсинг универсальных timeout команд (ЭТАП 1)

        ФОРМАТЫ:
        - timeout:30s → используется nextnodeid + preset 'clean'
        - timeout:15s:no_answer → явный переход на узел 'no_answer'  
        - timeout:5s:slow → используется nextnodeid + preset 'slow' (silent mode)

        ЛОГИКА ОПРЕДЕЛЕНИЯ РЕЖИМА:
        - Если аргумент = известный preset → используем nextnodeid + preset
        - Если аргумент = неизвестный → считаем узлом назначения
        - Без аргумента → nextnodeid + preset 'clean'

        ИНТЕГРАЦИЯ С SILENT MODE:
        - preset 'slow' часто используется для сценарных пауз
        - Режим определяется в should_show_countdown() по context
        """
        known_presets = set(self.presets.keys())

        # Формат: timeout:15s:xxx (с аргументом)
        pattern_with_arg = r'^timeout:(\d+(?:\.\d+)?)s:([^:]+)$'
        match_with_arg = re.match(pattern_with_arg, cmd_str)

        if match_with_arg:
            duration = float(match_with_arg.group(1))
            arg = match_with_arg.group(2).strip()

            print(f"[TIMING-ENGINE-S2] Parsing timeout with arg: {duration}s '{arg}'")

            if arg in known_presets:
                # Аргумент - это preset, используем next_node_id
                print(f"[TIMING-ENGINE-S2] Recognized preset: {arg}")
                return {
                    'type': 'timeout',
                    'duration': duration,
                    'target_node': None,
                    'use_next_node_id': True,
                    'preset': arg,
                    'show_countdown': True,  # будет переопределено в should_show_countdown()
                    'original': cmd_str
                }
            else:
                # Аргумент - это узел назначения
                print(f"[TIMING-ENGINE-S2] Target node specified: {arg}")
                return {
                    'type': 'timeout',
                    'duration': duration,
                    'target_node': arg,
                    'use_next_node_id': False,
                    'preset': 'clean',
                    'show_countdown': True,  # будет переопределено в should_show_countdown()
                    'original': cmd_str
                }

        # Формат: timeout:30s (без аргумента)
        pattern_simple = r'^timeout:(\d+(?:\.\d+)?)s$'
        match_simple = re.match(pattern_simple, cmd_str)

        if match_simple:
            duration = float(match_simple.group(1))
            print(f"[TIMING-ENGINE-S2] Parsed simple timeout: {duration}s")
            return {
                'type': 'timeout',
                'duration': duration,
                'target_node': None,
                'use_next_node_id': True,
                'preset': 'clean',
                'show_countdown': True,  # будет переопределено в should_show_countdown()
                'original': cmd_str
            }

        print(f"[TIMING-ENGINE-S2] Failed to parse timeout: {cmd_str}")
        return None

    # ЗАГОТОВКИ парсеров для будущих спринтов (из Этапа 1 - полностью сохранены)
    def _parse_remind(self, cmd_str: str) -> Dict[str, Any]:
        """
        ЗАГОТОВКА ЭТАПА 1: Парсинг remind команд для системы напоминаний

        ПЛАНИРУЕМЫЕ ФОРМАТЫ (для будущих спринтов):
        - remind:5m → напоминание через 5 минут
        - remind:1h,1d → напоминания через час и день
        - remind:5m,1h,1d → каскад напоминаний

        ПРИМЕНЕНИЕ В ИССЛЕДОВАНИЯХ:
        - Напоминания о заполнении дневников
        - Напоминания о завершении задач
        - Каскадные уведомления для повышения engagement

        СТАТУС: Заготовка - будет реализована в Этапе 3+
        """
        match = re.match(r'^remind:(.+)$', cmd_str)
        if match:
            intervals = []
            # Парсинг интервалов: 5m,1h,1d
            for interval in match.group(1).split(','):
                interval_str = interval.strip()
                time_match = re.match(r'^(\d+)(h|m|s)$', interval_str)
                if time_match:
                    value = int(time_match.group(1))
                    unit = time_match.group(2)
                    # Конвертация в секунды
                    seconds = value if unit == 's' else value*60 if unit == 'm' else value*3600
                    intervals.append(seconds)

            print(f"[TIMING-ENGINE-S2] Parsed remind intervals: {intervals} (STUB)")
            return {
                'type': 'remind', 
                'intervals': intervals, 
                'original': cmd_str
            }
        return None

    def _parse_deadline(self, cmd_str: str) -> Dict[str, Any]:
        """
        ЗАГОТОВКА ЭТАПА 1: Парсинг deadline команд для системы дедлайнов

        ПЛАНИРУЕМЫЕ ФОРМАТЫ (для будущих спринтов):
        - deadline:2h → дедлайн через 2 часа с предупреждениями
        - deadline:1d → дедлайн через день
        - deadline:3d:urgent → дедлайн с типом urgency

        ПРИМЕНЕНИЕ В ИССЛЕДОВАНИЯХ:
        - Дедлайны для заполнения анкет
        - Временные ограничения на участие в этапах
        - Автоматическое закрытие неактивных исследований

        СТАТУС: Заготовка - будет реализована в Этапе 3+
        """
        match = re.match(r'^deadline:(\d+)(h|d|m)$', cmd_str)
        if match:
            value = int(match.group(1))
            unit = match.group(2)
            # Конвертация в секунды
            seconds = value*3600 if unit == 'h' else value*86400 if unit == 'd' else value*60

            print(f"[TIMING-ENGINE-S2] Parsed deadline: {seconds}s ({value}{unit}) (STUB)")
            return {
                'type': 'deadline', 
                'duration': seconds, 
                'original': cmd_str
            }
        return None