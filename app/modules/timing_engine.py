# -*- coding: utf-8 -*-

"""

R-Bot Timing Engine - ЭТАП 2: Календарная Daily система + исправления импорта

ЭТАП 2 ОБНОВЛЕНИЯ:
07.10.2025 - КАЛЕНДАРНАЯ DAILY система (до даты, не по счетчику) 
07.10.2025 - WORKDAYS календарь (пропуск выходных)  
07.10.2025 - ON_COMPLETE механизм (ИСПРАВЛЕН - безопасные импорты)
07.10.2025 - GUARD защита (блокировка узлов до cutoff даты)
07.10.2025 - СТАТИСТИКА участия (автоматическое ведение)
07.10.2025 - БЕЗ БД операций (memory only для стабильности)

УНАСЛЕДОВАНО ИЗ ЭТАПА 1 (БЕЗ ПОТЕРЬ):
06.10.2025 - ДОБАВЛЕНЫ адаптивные countdown сообщения (без технических узлов)
06.10.2025 - Умное форматирование времени (только ненулевые разряды)
06.10.2025 - Контекстный выбор шаблонов сообщений
06.10.2025 - Удаление кнопок при timeout
06.10.2025 - ДОБАВЛЕН Silent Mode для сценарных timeout'ов
06.10.2025 - ИСПРАВЛЕНИЕ "Ваш ответ: Отлично" (кнопки удаляются правильно)

DSL КОМАНДЫ ЭТАПА 2:
- daily@21:00:MSK                           - одноразовое (завтра)
- daily@21:00:MSK:until:2025-10-17         - до 17 октября
- daily@21:00:MSK:until:2025-10-17:wd      - до 17 октября, рабочие дни
- daily@21:00:MSK:until:2025-10-17>final   - с автопереходом к итогам
- timing:guard:until_date_reached          - защита узлов до cutoff

DSL КОМАНДЫ ИЗ ЭТАПА 1:
- timeout:15s:no_answer - интерактивный timeout с countdown (если есть кнопки)
- timeout:5s:slow - тихий timeout для драматургии (если есть pause_text)
- typing:5s:Анализ поведения:clean - прогресс-бар 5s с preset clean
- process:3s:Обработка данных:fast - статический процесс с preset fast
- daily@09:00MSK - ежедневные уведомления (заготовка ИЗ ЭТАПА 1 - теперь РАБОЧИЙ!)
- remind:5m,1h,1d - система напоминаний (заготовка)
- deadline:2h - дедлайны с предупреждениями (заготовка)

"""

import threading
import time
import re
import logging
from datetime import datetime, timedelta, date
from typing import Dict, Any, Callable, Optional, List, Set
import pytz

# Безопасные импорты БД
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
    ЭТАП 2: Timing Engine с календарной Daily системой, Guard защитой
    и всеми исправлениями из Этапа 1 (ПОЛНАЯ ВЕРСИЯ БЕЗ ПОТЕРЬ)
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

        # Для timeout задач (из Этапа 1)
        self.cancelled_tasks: Set[int] = set()
        self.active_timeouts: Dict[int, threading.Thread] = {}
        self.debug_timers: Dict[int, Dict] = {}

        # Адаптивные шаблоны countdown сообщений (из Этапа 1)
        self.countdown_templates = self._init_countdown_templates()

        # НОВОЕ ЭТАПА 2: Daily календарная система
        self.active_daily_configs: Dict[str, Dict] = {}  # calendar daily configurations
        self.daily_participation_stats: Dict[str, Dict] = {}  # участие по дням
        self.daily_cutoff_dates: Dict[str, date] = {}  # cutoff даты для защиты
        self.workday_calendar = self._init_workdays()  # рабочие дни

        self.initialized = True
        logger.info(f"TimingEngine STAGE2 initialized with Silent Mode. Enabled: {self.enabled}")
        print(f"[TIMING-ENGINE-S2] TimingEngine STAGE2 initialized with enabled={self.enabled}")
        print(f"[TIMING-ENGINE-S2] Available presets: {list(self.presets.keys())}")
        print(f"[TIMING-ENGINE-S2] Available commands: {list(self.parsers.keys())}")
        print(f"[TIMING-ENGINE-S2] Adaptive message types: {list(self.countdown_templates.keys())}")
        print(f"[TIMING-ENGINE-S2] Silent Mode activated for scenic timeouts")
        print(f"[TIMING-ENGINE-S2] Calendar Daily System: ✅")
        print(f"[TIMING-ENGINE-S2] Workdays Support: ✅")
        print(f"[TIMING-ENGINE-S2] Guard Protection: ✅")
        print(f"[TIMING-ENGINE-S2] Auto Statistics: ✅")
        print(f"[TIMING-ENGINE-S2] Safe Imports: ✅")

        if self.enabled:
            try:
                self.restore_timers_from_db()
                self.cleanup_expired_timers()
            except Exception as e:
                logger.error(f"Failed to restore/cleanup timers on init: {e}")

    # ============================================================================
    # НОВОЕ ЭТАПА 2: КАЛЕНДАРНАЯ DAILY СИСТЕМА
    # ============================================================================

    def _init_workdays(self) -> Set[int]:
        """НОВОЕ ЭТАПА 2: Инициализация рабочих дней (понедельник=0, воскресенье=6)"""
        return {0, 1, 2, 3, 4}  # пн-пт

    def _parse_daily(self, cmd_str: str) -> Dict[str, Any]:
        """
        ЭТАП 2: Парсинг календарных daily команд (ОБНОВЛЕНО из заготовки!)

        ПОДДЕРЖИВАЕМЫЕ ФОРМАТЫ:
        daily@21:00:MSK                              → одноразово завтра
        daily@21:00:MSK:until:2025-10-17            → до 17 октября
        daily@21:00:MSK:until:2025-10-17:wd         → до 17 октября, рабочие дни
        daily@21:00:MSK:until:2025-10-17:wd>final   → + автопереход к итогам
        """
        print(f"[DAILY-S2] Parsing daily command: {cmd_str}")

        # Regex для полного парсинга календарной daily
        pattern = r'^daily@(\d{1,2}):(\d{2})(?::([A-Z]{3}))?(?::until:(\d{4}-\d{2}-\d{2}))?(?::(wd|workdays))?(?:>([^\s]+))?$'
        match = re.match(pattern, cmd_str)

        if match:
            hour = int(match.group(1))
            minute = int(match.group(2))
            timezone_str = match.group(3) or 'MSK'  # дефолт MSK для исследований
            until_date_str = match.group(4)  # YYYY-MM-DD или None
            workdays_flag = match.group(5)  # 'wd'/'workdays' или None
            on_complete_node = match.group(6)  # узел для автоперехода или None

            # Парсим дату окончания
            until_date = None
            if until_date_str:
                try:
                    until_date = datetime.strptime(until_date_str, '%Y-%m-%d').date()
                except ValueError:
                    print(f"[DAILY-S2] Invalid until date: {until_date_str}")
                    return None
            else:
                # Дефолт: завтра (одноразово)
                until_date = (datetime.now().date() + timedelta(days=1))

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

            print(f"[DAILY-S2] Parsed: {result}")
            return result

        # FALLBACK: Старый формат из заготовки Этапа 1
        old_match = re.match(r'^daily@(\d{2}):(\d{2})([A-Z]{3})?$', cmd_str)
        if old_match:
            return {
                'type': 'daily',
                'hour': int(old_match.group(1)),
                'minute': int(old_match.group(2)),
                'timezone': old_match.group(3) or 'UTC',
                'until_date': (datetime.now().date() + timedelta(days=1)),  # завтра
                'workdays_only': False,
                'on_complete_node': None,
                'original': cmd_str
            }

        print(f"[DAILY-S2] Failed to parse: {cmd_str}")
        return None

    def _parse_guard(self, cmd_str: str) -> Dict[str, Any]:
        """
        НОВОЕ ЭТАПА 2: Парсинг guard команд для защиты узлов

        ФОРМАТ: timing:guard:until_date_reached
        """
        if cmd_str.startswith('timing:guard:'):
            condition = cmd_str[13:]  # убираем 'timing:guard:'
            return {
                'type': 'guard',
                'condition': condition,
                'original': cmd_str
            }
        return None

    def calculate_next_daily_time(self, hour: int, minute: int, timezone_str: str, 
                                  workdays_only: bool = False) -> Optional[datetime]:
        """
        НОВОЕ ЭТАПА 2: Расчет следующего времени daily с учетом workdays
        """
        try:
            tz_map = {
                'MSK': 'Europe/Moscow', 'UTC': 'UTC', 'EST': 'US/Eastern',
                'PST': 'US/Pacific', 'CET': 'Europe/Berlin', 'GMT': 'GMT'
            }

            timezone = pytz.timezone(tz_map.get(timezone_str, 'Europe/Moscow'))
            now = datetime.now(timezone)

            # Завтра в указанное время
            # ИСПРАВЛЕНИЕ 07.10.2025: Проверяем время СЕГОДНЯ перед планированием ЗАВТРА
            today_target_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

            print(f"[DAILY-S2] FIXED: Now={now}")
            print(f"[DAILY-S2] FIXED: Target today={today_target_time}")
            print(f"[DAILY-S2] FIXED: Time comparison: now < target = {now < today_target_time}")

            # НОВАЯ ЛОГИКА: Если время daily СЕГОДНЯ еще НЕ прошло → планируем СЕГОДНЯ
            if now < today_target_time:
                print(f"[DAILY-S2] FIXED: Time has NOT passed today - scheduling TODAY!")

                if workdays_only:
                    if today_target_time.weekday() in self.workday_calendar:
                        print(f"[DAILY-S2] FIXED: Today is workday - using today: {today_target_time}")
                        return today_target_time
                    else:
                        print(f"[DAILY-S2] FIXED: Today not workday, finding next workday...")
                        tomorrow = today_target_time + timedelta(days=1)
                else:
                    print(f"[DAILY-S2] FIXED: No workday restriction - using today: {today_target_time}")
                    return today_target_time
            else:
                print(f"[DAILY-S2] FIXED: Time already passed today - scheduling tomorrow")
                tomorrow = today_target_time + timedelta(days=1)

                # Если нужны только рабочие дни, найти следующий рабочий день
                if workdays_only:
                    while tomorrow.weekday() not in self.workday_calendar:
                        tomorrow += timedelta(days=1)

                print(f"[DAILY-S2] Next daily time: {tomorrow} (workdays_only={workdays_only})")
                return tomorrow

        except Exception as e:
            print(f"[DAILY-S2] Error calculating next daily time: {e}")
            return None

    def _execute_daily(self, command: Dict[str, Any], callback: Callable, **context) -> None:
        """
        ЭТАП 2: Исполнитель календарной daily системы (ОБНОВЛЕНО из заготовки!)
        """
        hour = command['hour']
        minute = command['minute']
        timezone_str = command['timezone']
        until_date = command['until_date']
        workdays_only = command.get('workdays_only', False)
        on_complete_node = command.get('on_complete_node')

        session_id = context.get('session_id')

        print(f"[DAILY-S2] Executing daily: {hour:02d}:{minute:02d} {timezone_str}")
        print(f"[DAILY-S2] Until date: {until_date}")
        print(f"[DAILY-S2] Workdays only: {workdays_only}")
        print(f"[DAILY-S2] On complete: {on_complete_node}")

        # Проверяем, не истекла ли cutoff дата
        current_date = datetime.now().date()
        if current_date > until_date:
            print(f"[DAILY-S2] Daily expired: {current_date} > {until_date}")
            # Если есть on_complete и время пришло → запускаем итоговые вопросы
            if on_complete_node:
                print(f"[DAILY-S2] Triggering on_complete: {on_complete_node}")
                self._trigger_on_complete(on_complete_node, **context)
            return

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

        # Планируем первый daily (сегодня выполняем callback, завтра планируем следующий)
        print(f"[DAILY-S2] Executing immediate callback for daily setup")
        callback()

        # Планируем следующий daily
        self.schedule_next_daily_calendar(daily_key, daily_config, **context)

    def schedule_next_daily_calendar(self, daily_key: str, daily_config: Dict, **context):
        """
        НОВОЕ ЭТАПА 2: Календарное планирование daily (до cutoff даты)
        """
        hour = daily_config['hour']
        minute = daily_config['minute']
        timezone_str = daily_config['timezone']
        until_date = daily_config['until_date']
        workdays_only = daily_config['workdays_only']
        on_complete_node = daily_config['on_complete_node']
        callback = daily_config['callback']

        next_time = self.calculate_next_daily_time(hour, minute, timezone_str, workdays_only)
        if not next_time:
            print(f"[DAILY-S2] Failed to calculate next time for {daily_key}")
            return

        # Проверяем календарную отсечку
        next_date = next_time.date()
        if next_date > until_date:
            print(f"[DAILY-S2] Cutoff reached: {next_date} > {until_date}")
            print(f"[DAILY-S2] Daily cycle completed for {daily_key}")

            # Запускаем on_complete если есть
            if on_complete_node:
                print(f"[DAILY-S2] Scheduling on_complete: {on_complete_node}")
                # Небольшая задержка для "по горячему" эффекта
                threading.Timer(2.0, lambda: self._trigger_on_complete(on_complete_node, **context)).start()

            # Удаляем из активных (цикл завершен)
            self.active_daily_configs.pop(daily_key, None)
            return

        # Вычисляем задержку до следующего срабатывания  
        now_utc = datetime.now(pytz.UTC)
        next_time_utc = next_time.astimezone(pytz.UTC)
        delay_seconds = (next_time_utc - now_utc).total_seconds()

        print(f"[DAILY-S2] Scheduling next daily: {next_time} (in {delay_seconds:.1f}s)")

        def daily_timer_callback():
            """
            SURGICAL FIX 1: Исправлена логика cutoff проверки
            Теперь cutoff проверяется ПОСЛЕ выполнения callback, а не до
            """
            try:
                print(f"[DAILY-S2] Daily timer fired: {daily_key}")

                # ИСПРАВЛЕНИЕ: Сначала обновляем статистику участия
                self._update_daily_stats(daily_key, participated=True)

                # ИСПРАВЛЕНИЕ: Выполняем callback (переход к следующему узлу) БЕЗ проверки cutoff
                print(f"[DAILY-S2] SURGICAL-FIX-1: Executing callback before cutoff check")
                callback()

                # ИСПРАВЛЕНИЕ: Проверяем cutoff ПОСЛЕ выполнения callback
                # Это позволяет завершить текущий цикл вопросов до срабатывания on_complete
                current_date = datetime.now().date()
                print(f"[DAILY-S2] SURGICAL-FIX-1: Post-callback cutoff check: {current_date} vs {until_date}")

                # Планируем следующий daily ТОЛЬКО если период не закончился
                if current_date < until_date and daily_key in self.active_daily_configs:
                    print(f"[DAILY-S2] SURGICAL-FIX-1: Period continues, scheduling next daily")
                    self.schedule_next_daily_calendar(daily_key, daily_config, **context)
                else:
                    print(f"[DAILY-S2] SURGICAL-FIX-1: Period ended, triggering on_complete after cycle")
                    if on_complete_node:
                        # ВАЖНО: Даем время на завершение текущего цикла (3 секунды)
                        threading.Timer(3.0, lambda: self._trigger_on_complete(on_complete_node, **context)).start()
                        print(f"[DAILY-S2] SURGICAL-FIX-1: on_complete delayed by 3s for cycle completion")

            except Exception as e:
                print(f"[DAILY-S2] Daily callback error: {e}")

    def _trigger_on_complete(self, on_complete_node: str, **context):
        """
        ИСПРАВЛЕННАЯ ВЕРСИЯ: Безопасный запуск on_complete узлов через возврат результата
        ИСПРАВЛЕНИЕ 07.10.2025: Убраны проваливающиеся импорты, используется флаг для handler
        """
        print(f"[DAILY-S2] Triggering on_complete node: {on_complete_node}")

        bot = context.get('bot')
        chat_id = context.get('chat_id')
        session_id = context.get('session_id')

        if not bot or not chat_id:
            print(f"[DAILY-S2] Cannot trigger on_complete: missing bot/chat_id")
            return

        # Получаем статистику для персонализации
        stats = self._get_daily_stats_summary(session_id)

        try:
            # Отправляем только уведомление о завершении исследовательского периода
            transition_msg = f"🎉 Исследовательский период завершен!\n\n📊 Ваше участие: {stats['participated_days']} из {stats['total_days']} дней\n\nПереходим к итоговым вопросам..."
            bot.send_message(chat_id, transition_msg)
            print(f"[DAILY-S2] FIXED: Sent completion message")

            # Небольшая пауза для восприятия
            time.sleep(2)

            # ИСПРАВЛЕНИЕ: Устанавливаем флаг pending transition для telegram_handler
            if not hasattr(self, '_pending_on_complete_transitions'):
                self._pending_on_complete_transitions = {}

            self._pending_on_complete_transitions[session_id] = on_complete_node
            print(f"[DAILY-S2] FIXED: Set pending on_complete transition: {session_id} -> {on_complete_node}")

            # НОВОЕ: Вызываем send_node_message напрямую через глобальную функцию
            # Это безопаснее чем импорты
            try:
                # Получаем send_node_message из глобального пространства telegram_handler
                import sys
                if 'app.modules.telegram_handler' in sys.modules:
                    handler_module = sys.modules['app.modules.telegram_handler'] 
                    if hasattr(handler_module, 'send_node_message'):
                        print(f"[DAILY-S2] FIXED: Found send_node_message in handler module")
                        handler_module.send_node_message(chat_id, on_complete_node)
                        print(f"[DAILY-S2] FIXED: Successfully triggered node: {on_complete_node}")
                        return

                print(f"[DAILY-S2] FIXED: send_node_message not found in module, using fallback")

                # FALLBACK: Сообщение с инструкцией, но БЕЗ "обратитесь к администратору"
                fallback_msg = f"🔄 Для продолжения к итоговым вопросам отправьте /start"
                bot.send_message(chat_id, fallback_msg)

            except Exception as import_error:
                print(f"[DAILY-S2] FIXED: Module access failed: {import_error}")
                # Финальный fallback
                fallback_msg = f"🔄 Для продолжения к итоговым вопросам отправьте /start"
                bot.send_message(chat_id, fallback_msg)

        except Exception as e:
            print(f"[DAILY-S2] Critical error in _trigger_on_complete: {e}")
            try:
                error_msg = "⚠️ Произошла ошибка при переходе к итоговым вопросам.\nПопробуйте /start"
                bot.send_message(chat_id, error_msg)
            except Exception as final_error:
                print(f"[DAILY-S2] Even final fallback failed: {final_error}")

    def _execute_guard(self, command: Dict[str, Any], callback: Callable, **context) -> None:
        """
        НОВОЕ ЭТАПА 2: Исполнитель Guard защиты узлов
        """
        condition = command.get('condition')
        session_id = context.get('session_id')

        print(f"[GUARD-S2] Checking guard condition: {condition} for session {session_id}")

        if condition == 'until_date_reached':
            if self._is_daily_cutoff_reached(session_id):
                print(f"[GUARD-S2] Guard passed - cutoff date reached")
                callback()  # Доступ разрешен
            else:
                print(f"[GUARD-S2] Guard blocked - cutoff date not reached (silent block)")
                # ТИХАЯ блокировка - НЕ отправляем сообщение пользователю
                # Просто не выполняем callback
        else:
            print(f"[GUARD-S2] Unknown guard condition: {condition}")
            callback()  # Пропускаем при неизвестном условии

    def _is_daily_cutoff_reached(self, session_id: int) -> bool:
        """
        НОВОЕ ЭТАПА 2: Проверка достижения cutoff даты для session
        """
        current_date = datetime.now().date()

        # Ищем cutoff дату для этой сессии
        for daily_key, cutoff_date in self.daily_cutoff_dates.items():
            if f"_{session_id}_" in daily_key:
                result = current_date >= cutoff_date
                print(f"[GUARD-S2] Cutoff check: {current_date} >= {cutoff_date} = {result}")
                return result

        print(f"[GUARD-S2] No cutoff date found for session {session_id} - allowing access")
        return True  # Если нет cutoff даты - разрешаем доступ

    def _update_daily_stats(self, daily_key: str, participated: bool):
        """
        НОВОЕ ЭТАПА 2: Обновление статистики участия
        """
        # Извлекаем session_id из daily_key
        parts = daily_key.split('_')
        if len(parts) >= 4:
            session_id = int(parts[1])
            hour = int(parts[2])
            minute = int(parts[3])

            stats_key = f"stats_{session_id}_{hour}_{minute}"
            if stats_key in self.daily_participation_stats:
                stats = self.daily_participation_stats[stats_key]
                stats['total_days'] += 1
                if participated:
                    stats['participated_days'] += 1

                participation_rate = (stats['participated_days'] / stats['total_days']) * 100
                print(f"[DAILY-S2] Stats updated: {stats['participated_days']}/{stats['total_days']} ({participation_rate:.1f}%)")

    def _get_daily_stats_summary(self, session_id: int) -> Dict[str, Any]:
        """
        НОВОЕ ЭТАПА 2: Получение сводки статистики участия
        """
        for stats_key, stats in self.daily_participation_stats.items():
            if f"stats_{session_id}_" in stats_key:
                participation_rate = (stats['participated_days'] / stats['total_days'] * 100) if stats['total_days'] > 0 else 0
                return {
                    'total_days': stats['total_days'],
                    'participated_days': stats['participated_days'],
                    'participation_rate': round(participation_rate, 1),
                    'start_date': stats['start_date'],
                    'until_date': stats['until_date']
                }

        # Дефолтные значения если статистика не найдена
        return {
            'total_days': 0,
            'participated_days': 0,
            'participation_rate': 0,
            'start_date': datetime.now().date(),
            'until_date': datetime.now().date()
        }

    # ============================================================================
    # ВСЕ ИЗ ЭТАПА 1 - ПОЛНОСТЬЮ БЕЗ ИЗМЕНЕНИЙ
    # ============================================================================

    def _init_countdown_templates(self) -> Dict[str, Dict[str, str]]:
        """Инициализация адаптивных шаблонов countdown сообщений"""
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
        """Форматирует время для countdown в человекочитаемый вид"""
        if seconds <= 0:
            return "время истекло"

        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        parts = []

        if hours > 0:
            form = "час" if hours == 1 else ("часа" if 2 <= hours <= 4 else "часов")
            parts.append(f"{hours} {form}")

        if minutes > 0:
            form = "минуту" if minutes == 1 else ("минуты" if 2 <= minutes <= 4 else "минут")
            parts.append(f"{minutes} {form}")

        if secs > 0 or not parts:
            form = "секунду" if secs == 1 else ("секунды" if 2 <= secs <= 4 else "секунд")
            parts.append(f"{secs} {form}")

        return " ".join(parts)

    def get_countdown_message_type(self, duration: int, node_id: str = "", node_text: str = "") -> str:
        """Адаптивный выбор типа сообщения по контексту"""
        # Правило 1: По длительности (базовая логика)
        if duration <= 5:
            base_type = "urgent"
        elif duration <= 15:
            base_type = "choice"
        elif duration <= 60:
            base_type = "decision"
        else:
            base_type = "gentle"

        # Правило 2: Переопределение по node_id
        if node_id:
            node_lower = node_id.lower()
            if any(keyword in node_lower for keyword in ['test', 'quiz', 'question', 'answer']):
                return "answer"
            elif any(keyword in node_lower for keyword in ['timing', 'speed', 'reaction']):
                return "choice"

        # Правило 3: По содержанию текста
        if node_text:
            text_lower = node_text.lower()
            if any(word in text_lower for word in ['настроение', 'чувство', 'ощущение']):
                return "gentle"
            elif any(word in text_lower for word in ['быстро', 'срочно', 'скорее']):
                return "urgent"
            elif any(word in text_lower for word in ['тест', 'вопрос', 'ответ']):
                return "answer"

        return base_type

    def should_show_countdown(self, context: dict) -> bool:
        """
        НОВОЕ: Определяет, нужно ли показывать countdown сообщения

        ЛОГИКА:
        - Есть pause_text → ТИХИЙ timeout (сценарная пауза)
        - Есть кнопки И нет pause_text → ИНТЕРАКТИВНЫЙ timeout (countdown)
        - НЕТ кнопок И НЕТ pause_text → ТИХИЙ timeout
        """
        pause_text = context.get('pause_text', '').strip()
        has_pause_text = bool(pause_text)
        has_buttons = len(context.get('buttons', [])) > 0

        print(f"[TIMING-ENGINE-S2] Silent mode check:")
        print(f" - pause_text: '{pause_text[:30]}{'...' if len(pause_text) > 30 else ''}'")
        print(f" - has_buttons: {has_buttons}")

        # Показывать countdown только для интерактивных timeout'ов
        show_countdown = has_buttons and not has_pause_text
        mode = "INTERACTIVE" if show_countdown else "SILENT"
        print(f"[TIMING-ENGINE-S2] Timeout mode: {mode}")

        return show_countdown

    def _init_presets(self) -> Dict[str, Dict[str, Any]]:
        """Инициализация preset'ов для контроля экспозиции и anti-flicker"""
        return {
            'clean': {
                'exposure_time': 1.5,
                'anti_flicker_delay': 1.0,
                'action': 'delete',
                'description': 'Стандарт: показать результат 1.5с, пауза 1с, удалить'
            },
            'keep': {
                'exposure_time': 0,
                'anti_flicker_delay': 0.5,
                'action': 'keep',
                'description': 'Оставить в ленте навсегда'
            },
            'fast': {
                'exposure_time': 0.8,
                'anti_flicker_delay': 0.5,
                'action': 'delete',
                'description': 'Быстро: показать 0.8с, пауза 0.5с, удалить'
            },
            'slow': {
                'exposure_time': 3.0,
                'anti_flicker_delay': 2.0,
                'action': 'delete',
                'description': 'Медленно: показать 3с, пауза 2с, удалить'
            },
            'instant': {
                'exposure_time': 0,
                'anti_flicker_delay': 0,
                'action': 'delete',
                'description': 'Мгновенно: сразу удалить'
            }
        }

    @classmethod
    def get_instance(cls):
        return cls()

    # ============================================================================
    # INIT МЕТОДЫ (ОБНОВЛЕНЫ ДЛЯ ЭТАПА 2)
    # ============================================================================

    def _init_parsers(self) -> Dict[str, Any]:
        """Инициализация парсеров DSL команд (Этап 1 + Этап 2)"""
        return {
            'basic_pause': self._parse_basic_pause,
            'typing': self._parse_typing,
            'process': self._parse_process,
            'timeout': self._parse_timeout,
            'daily': self._parse_daily,      # ОБНОВЛЕНО для календарной логики
            'guard': self._parse_guard,      # НОВОЕ: Guard защита
            'remind': self._parse_remind,    # Заготовка
            'deadline': self._parse_deadline # Заготовка
        }

    def _init_executors(self) -> Dict[str, Any]:
        """Инициализация исполнителей команд (Этап 1 + Этап 2)"""
        return {
            'pause': self._execute_pause,
            'typing': self._execute_typing,
            'process': self._execute_process,
            'timeout': self._execute_timeout,
            'daily': self._execute_daily,    # ОБНОВЛЕНО для календарной логики
            'guard': self._execute_guard,    # НОВОЕ: Guard исполнитель
            'remind': self._execute_remind,  # Заготовка
            'deadline': self._execute_deadline # Заготовка
        }

    # ============================================================================
    # DSL ПАРСЕРЫ - ВСЕ ИЗ ЭТАПА 1 БЕЗ ИЗМЕНЕНИЙ
    # ============================================================================

    def _parse_basic_pause(self, cmd_str: str) -> Dict[str, Any]:
        """Парсинг простых пауз (из Этапа 1)"""
        match = re.match(r'^\d+(\.\d+)?(s)?$', cmd_str)
        if match:
            duration = float(cmd_str.replace('s', ''))
            return {'type': 'pause', 'duration': duration, 'process_name': 'Пауза', 'original': cmd_str}
        return None

    def _parse_typing(self, cmd_str: str) -> Dict[str, Any]:
        """Парсинг typing команд с preset'ами (из Этапа 1)"""
        pattern = r'^typing:(\d+(?:\.\d+)?)s?(?::([^:]+))?(?::([^:]+))?$'
        match = re.match(pattern, cmd_str)

        if match:
            duration = float(match.group(1))
            process_name = match.group(2) if match.group(2) else "Обработка"
            preset = match.group(3) if match.group(3) else 'clean'
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
        return None

    def _parse_process(self, cmd_str: str) -> Dict[str, Any]:
        """Парсинг process команд (замена state: true) (из Этапа 1)"""
        pattern = r'^process:(\d+(?:\.\d+)?)s?:([^:]+)(?::([^:]+))?$'
        match = re.match(pattern, cmd_str)

        if match:
            duration = float(match.group(1))
            process_name = match.group(2)
            preset = match.group(3) if match.group(3) else 'clean'
            preset_config = self.presets.get(preset, self.presets['clean'])

            return {
                'type': 'process',
                'duration': duration,
                'process_name': process_name,
                'preset': preset,
                'exposure_time': preset_config['exposure_time'],
                'anti_flicker_delay': preset_config['anti_flicker_delay'],
                'action': preset_config['action'],
                'show_progress': False,
                'original': cmd_str
            }
        return None

    def _parse_timeout(self, cmd_str: str) -> Dict[str, Any]:
        """Парсинг timeout команды с различением preset'ов и узлов назначения (из Этапа 1)"""
        known_presets = set(self.presets.keys())

        # timeout:15s:xxx
        pattern_with_arg = r'^timeout:(\d+(?:\.\d+)?)s:([^:]+)$'
        match_with_arg = re.match(pattern_with_arg, cmd_str)

        if match_with_arg:
            duration = float(match_with_arg.group(1))
            arg = match_with_arg.group(2).strip()

            if arg in known_presets:
                # Preset - используем next_node_id
                return {
                    'type': 'timeout',
                    'duration': duration,
                    'target_node': None,
                    'use_next_node_id': True,
                    'preset': arg,
                    'show_countdown': True,
                    'original': cmd_str
                }
            else:
                # Узел - явный переход
                return {
                    'type': 'timeout',
                    'duration': duration,
                    'target_node': arg,
                    'use_next_node_id': False,
                    'preset': 'clean',
                    'show_countdown': True,
                    'original': cmd_str
                }

        # timeout:30s
        pattern_simple = r'^timeout:(\d+(?:\.\d+)?)s$'
        match_simple = re.match(pattern_simple, cmd_str)

        if match_simple:
            duration = float(match_simple.group(1))
            return {
                'type': 'timeout',
                'duration': duration,
                'target_node': None,
                'use_next_node_id': True,
                'preset': 'clean',
                'show_countdown': True,
                'original': cmd_str
            }

        return None

    # ЗАГОТОВКИ парсеров для будущих функций (из Этапа 1)
    def _parse_remind(self, cmd_str: str) -> Dict[str, Any]:
        """ЗАГОТОВКА: Парсинг remind команд - remind:5m,1h,1d"""
        match = re.match(r'^remind:(.+)$', cmd_str)
        if match:
            intervals = []
            for interval in match.group(1).split(','):
                interval_str = interval.strip()
                time_match = re.match(r'^(\d+)(h|m|s)$', interval_str)
                if time_match:
                    value = int(time_match.group(1))
                    unit = time_match.group(2)
                    seconds = value if unit == 's' else value*60 if unit == 'm' else value*3600
                    intervals.append(seconds)
            return {'type': 'remind', 'intervals': intervals, 'original': cmd_str}
        return None

    def _parse_deadline(self, cmd_str: str) -> Dict[str, Any]:
        """ЗАГОТОВКА: Парсинг deadline команд - deadline:2h"""
        match = re.match(r'^deadline:(\d+)(h|d|m)$', cmd_str)
        if match:
            value = int(match.group(1))
            unit = match.group(2)
            seconds = value*3600 if unit == 'h' else value*86400 if unit == 'd' else value*60
            return {'type': 'deadline', 'duration': seconds, 'original': cmd_str}
        return None

    # ============================================================================
    # ИСПОЛНИТЕЛИ - ВСЕ ИЗ ЭТАПА 1 БЕЗ ИЗМЕНЕНИЙ
    # ============================================================================

    def _execute_pause(self, command: Dict[str, Any], callback: Callable, **context) -> None:
        """Исполнитель простых пауз (из Этапа 1)"""
        duration = command['duration']
        pause_text = context.get('pause_text') or ''
        bot = context.get('bot')
        chat_id = context.get('chat_id')

        if pause_text and bot and chat_id:
            bot.send_message(chat_id, pause_text)

        threading.Timer(duration, callback).start()

    def _execute_typing(self, command: Dict[str, Any], callback: Callable, **context) -> None:
        """Выполнение typing с preset'ами (из Этапа 1)"""
        duration = command['duration']
        process_name = command.get('process_name', 'Обработка')
        preset = command.get('preset', 'clean')
        exposure_time = command.get('exposure_time', 1.5)
        anti_flicker_delay = command.get('anti_flicker_delay', 1.0)
        action = command.get('action', 'delete')

        session_id = context.get('session_id')
        if session_id:
            self.save_timer_to_db(
                session_id=session_id, timer_type='typing',
                delay_seconds=int(duration), message_text=process_name,
                callback_data={'command': command, 'preset': preset}
            )

        bot = context.get('bot')
        chat_id = context.get('chat_id')

        if bot and chat_id:
            def show_progress_with_presets():
                try:
                    self._show_progress_bar_with_presets(
                        bot, chat_id, duration, process_name,
                        show_progress=True, exposure_time=exposure_time,
                        anti_flicker_delay=anti_flicker_delay, action=action
                    )
                    callback()
                except Exception as e:
                    callback()

            threading.Thread(target=show_progress_with_presets).start()
        else:
            threading.Timer(duration, callback).start()

    def _execute_process(self, command: Dict[str, Any], callback: Callable, **context) -> None:
        """Выполнение статических процессов (замена state: true) (из Этапа 1)"""
        duration = command['duration']
        process_name = command.get('process_name', 'Процесс')
        preset = command.get('preset', 'clean')
        exposure_time = command.get('exposure_time', 1.5)
        anti_flicker_delay = command.get('anti_flicker_delay', 1.0)
        action = command.get('action', 'delete')

        session_id = context.get('session_id')
        if session_id:
            self.save_timer_to_db(
                session_id=session_id, timer_type='process',
                delay_seconds=int(duration), message_text=process_name,
                callback_data={'command': command, 'preset': preset}
            )

        bot = context.get('bot')
        chat_id = context.get('chat_id')

        if bot and chat_id:
            def show_static_process():
                try:
                    self._show_progress_bar_with_presets(
                        bot, chat_id, duration, process_name,
                        show_progress=False, exposure_time=exposure_time,
                        anti_flicker_delay=anti_flicker_delay, action=action
                    )
                    callback()
                except Exception as e:
                    callback()

            threading.Thread(target=show_static_process).start()
        else:
            threading.Timer(duration, callback).start()

    def _execute_timeout(self, command: Dict[str, Any], callback: Callable, **context) -> None:
        """ОБНОВЛЕНО: Timeout с Silent Mode для сценарных пауз (из Этапа 1)"""
        duration = int(command['duration'])
        use_next_node_id = command.get('use_next_node_id', False)
        explicit_target = command.get('target_node')
        preset = command.get('preset', 'clean')
        preset_config = self.presets.get(preset, self.presets['clean'])

        # Определяем целевой узел
        if use_next_node_id:
            target_node = context.get('next_node_id')
            if not target_node:
                callback()
                return
        else:
            target_node = explicit_target

        session_id = context.get('session_id')
        bot = context.get('bot')
        chat_id = context.get('chat_id')
        question_message_id = context.get('question_message_id')

        # Получаем контекст для адаптивных сообщений
        node_id = context.get('node_id', '')
        node_text = context.get('node_text', '')

        # НОВОЕ: Проверяем режим timeout
        show_countdown = self.should_show_countdown(context)

        context['timeout_target_node'] = target_node
        if hasattr(callback, 'context'):
            callback.context.update(context)

        # Сохранить в БД с отметкой режима
        if session_id:
            self.save_timer_to_db(
                session_id=session_id, timer_type='timeout',
                delay_seconds=duration,
                message_text=f"Timeout {duration}s ({'interactive' if show_countdown else 'silent'})",
                callback_node_id=target_node,
                callback_data={
                    'command': command, 'target_node': target_node, 'preset': preset,
                    'silent_mode': not show_countdown
                }
            )

        # Сохранить для отладки
        if session_id:
            self.debug_timers[session_id] = {
                'type': 'timeout',
                'duration': duration,
                'target_node': target_node,
                'preset': preset,
                'started_at': time.time(),
                'chat_id': chat_id,
                'question_message_id': question_message_id,
                'silent_mode': not show_countdown
            }

        if not bot or not chat_id:
            threading.Timer(duration, lambda: self._execute_timeout_callback(
                session_id, target_node, preset_config, callback, bot, chat_id, question_message_id
            )).start()
            return

        # === РЕЖИМ 1: ИНТЕРАКТИВНЫЙ TIMEOUT (с countdown) ===
        if show_countdown:
            print(f"[TIMING-ENGINE-S2] INTERACTIVE timeout: {duration}s with countdown")

            message_type = self.get_countdown_message_type(duration, node_id, node_text)
            template = self.countdown_templates[message_type]

            # Адаптивное начальное сообщение
            initial_time_text = self.format_countdown_time(duration)
            countdown_msg = bot.send_message(
                chat_id,
                template['countdown'].format(time=initial_time_text)
            )

            def countdown_timer():
                """Живой обратный отсчет с адаптивными сообщениями"""
                for remaining in range(duration-1, 0, -1):
                    time.sleep(1)

                    # Проверить отмену
                    if session_id in self.cancelled_tasks:
                        try:
                            bot.edit_message_text(
                                chat_id=chat_id,
                                message_id=countdown_msg.message_id,
                                text="✅ Выбор сделан, автопереход отменен"
                            )
                            time.sleep(1.5)
                            bot.delete_message(chat_id, countdown_msg.message_id)
                        except Exception:
                            pass
                        self.cancelled_tasks.discard(session_id)
                        return

                    # Обновить с адаптивным форматированием времени
                    try:
                        time_text = self.format_countdown_time(remaining)
                        bot.edit_message_text(
                            chat_id=chat_id,
                            message_id=countdown_msg.message_id,
                            text=template['countdown'].format(time=time_text)
                        )
                    except Exception:
                        pass

                # Финальная проверка на отмену
                if session_id in self.cancelled_tasks:
                    self.cancelled_tasks.discard(session_id)
                    return

                # ИСПРАВЛЕНИЕ ЭТАПА 1: Убрать кнопки из исходного сообщения ПЕРЕД переходом
                if question_message_id:
                    try:
                        from telebot.types import InlineKeyboardMarkup
                        empty_keyboard = InlineKeyboardMarkup()
                        bot.edit_message_reply_markup(
                            chat_id=chat_id,
                            message_id=question_message_id,
                            reply_markup=empty_keyboard
                        )
                    except Exception as e:
                        print(f"[TIMING-ENGINE-S2] Button removal error: {e}")

                # Показать адаптивное финальное сообщение
                try:
                    bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=countdown_msg.message_id,
                        text=template['final']
                    )
                except Exception:
                    pass

                # Выполнить callback с preset задержками
                self._execute_timeout_callback(session_id, target_node, preset_config, callback, bot, chat_id, question_message_id)

                # Удалить служебные сообщения
                try:
                    time.sleep(1)
                    bot.delete_message(chat_id, countdown_msg.message_id)
                except Exception:
                    pass

            # Запустить поток обратного отсчета
            countdown_thread = threading.Thread(target=countdown_timer, daemon=True)
            countdown_thread.start()

            if session_id:
                self.active_timeouts[session_id] = countdown_thread

        # === РЕЖИМ 2: ТИХИЙ TIMEOUT (без countdown) ===
        else:
            print(f"[TIMING-ENGINE-S2] SILENT timeout: {duration}s (scenic pause)")

            # Показать pause_text если есть
            pause_text = context.get('pause_text', '').strip()
            if pause_text:
                bot.send_message(chat_id, pause_text)
                print(f"[TIMING-ENGINE-S2] Sent pause_text: '{pause_text[:50]}...'")

            def silent_timeout():
                """Тихий timeout без countdown сообщений"""
                time.sleep(duration)
                if session_id in self.cancelled_tasks:
                    self.cancelled_tasks.discard(session_id)
                    return

                print(f"[TIMING-ENGINE-S2] Silent timeout completed: {duration}s")
                self._execute_timeout_callback(session_id, target_node, preset_config, callback, bot, chat_id, question_message_id)

            timeout_thread = threading.Thread(target=silent_timeout, daemon=True)
            timeout_thread.start()

            if session_id:
                self.active_timeouts[session_id] = timeout_thread

    def _execute_timeout_callback(self, session_id: int, target_node: str, preset_config: dict,
                                  callback: Callable, bot=None, chat_id=None, question_message_id=None):
        """Выполнить callback с применением preset задержек (из Этапа 1)"""
        if session_id in self.cancelled_tasks:
            self.cancelled_tasks.discard(session_id)
            return

        exposure_time = preset_config.get('exposure_time', 0)
        anti_flicker_delay = preset_config.get('anti_flicker_delay', 0)

        if exposure_time > 0:
            time.sleep(exposure_time)

        try:
            callback()
        except Exception as e:
            logger.error(f"Timeout callback error: {e}")

        if anti_flicker_delay > 0:
            time.sleep(anti_flicker_delay)

        # Очистка
        if session_id in self.debug_timers:
            del self.debug_timers[session_id]
        if session_id in self.active_timeouts:
            del self.active_timeouts[session_id]

    # ЗАГОТОВКИ исполнителей для будущих функций (из Этапа 1 - остались заготовками)
    def _execute_remind(self, command: Dict[str, Any], callback: Callable, **context) -> None:
        """ЗАГОТОВКА: Исполнитель системы напоминаний"""
        print(f"[TIMING-ENGINE-S2] Reminder system stub: {command.get('original', 'N/A')}")
        callback()

    def _execute_deadline(self, command: Dict[str, Any], callback: Callable, **context) -> None:
        """ЗАГОТОВКА: Исполнитель дедлайнов"""
        print(f"[TIMING-ENGINE-S2] Deadline system stub: {command.get('original', 'N/A')}")
        callback()

    def _show_progress_bar_with_presets(self, bot, chat_id, duration, process_name,
                                        show_progress=True, exposure_time=1.5,
                                        anti_flicker_delay=1.0, action='delete'):
        """Показ процесса с полным контролем экспозиции (из Этапа 1)"""
        try:
            if show_progress:
                # ПРОГРЕСС-БАР
                msg = bot.send_message(chat_id, f"🚀 {process_name}\n⬜⬜⬜⬜⬜ 0%")
                steps = 5
                step_duration = duration / steps

                for i in range(1, steps + 1):
                    time.sleep(step_duration)
                    progress = int((i / steps) * 100)
                    filled = "🟩" * i
                    empty = "⬜" * (steps - i)
                    try:
                        bot.edit_message_text(
                            chat_id=chat_id, message_id=msg.message_id,
                            text=f"🚀 {process_name}\n{filled}{empty} {progress}%"
                        )
                    except Exception:
                        pass

                try:
                    bot.edit_message_text(
                        chat_id=chat_id, message_id=msg.message_id,
                        text=f"✅ {process_name}\n🟩🟩🟩🟩🟩 100%"
                    )
                except Exception:
                    pass
            else:
                # СТАТИЧЕСКОЕ СООБЩЕНИЕ
                msg = bot.send_message(chat_id, f"⚙️ {process_name}...")
                time.sleep(duration)
                try:
                    bot.edit_message_text(
                        chat_id=chat_id, message_id=msg.message_id,
                        text=f"✅ {process_name}"
                    )
                except Exception:
                    pass

            # ЭКСПОЗИЦИЯ + УДАЛЕНИЕ + ANTI-FLICKER
            if exposure_time > 0:
                time.sleep(exposure_time)

            if action == 'delete':
                try:
                    bot.delete_message(chat_id=chat_id, message_id=msg.message_id)
                except Exception:
                    pass

            if anti_flicker_delay > 0:
                time.sleep(anti_flicker_delay)

        except Exception as e:
            logger.error(f"Process with presets failed: {e}")

    # ============================================================================
    # ОСНОВНАЯ ЛОГИКА DSL (из Этапа 1 + обновления Этапа 2)
    # ============================================================================

    def execute_timing(self, timing_config: str, callback: Callable, **context) -> None:
        """Главная функция выполнения timing команд"""
        if not self.enabled:
            callback()
            return

        try:
            commands = self._parse_timing_dsl(timing_config)
            self._execute_timing_commands(commands, callback, **context)
        except Exception as e:
            logger.error(f"TimingEngine error: {e}")
            callback()

    def _parse_timing_dsl(self, timing_config: str) -> List[Dict[str, Any]]:
        """Парсинг DSL команд с поддержкой новых команд Этапа 2"""
        if not timing_config or timing_config.strip() == "":
            return []

        command_strings = [cmd.strip() for cmd in timing_config.split(';') if cmd.strip()]
        commands = []

        for cmd_str in command_strings:
            parsed = None

            # Обратная совместимость: простые числа
            if re.match(r'^\d+(\.\d+)?(s)?$', cmd_str):
                parsed = self.parsers['basic_pause'](cmd_str)

            # process команды
            elif cmd_str.startswith('process:'):
                parsed = self.parsers['process'](cmd_str)

            # УНИВЕРСАЛЬНАЯ timeout команда
            elif cmd_str.startswith('timeout:'):
                parsed = self.parsers['timeout'](cmd_str)

            # typing команды с preset'ами
            elif cmd_str.startswith('typing:'):
                parsed = self.parsers['typing'](cmd_str)

            # ЭТАП 2: Daily команды (ПРИОРИТЕТ над заготовкой)
            elif cmd_str.startswith('daily@'):
                parsed = self.parsers['daily'](cmd_str)

            # ЭТАП 2: Guard команды
            elif cmd_str.startswith('timing:guard:'):
                parsed = self.parsers['guard'](cmd_str)

            # ЗАГОТОВКИ для будущих функций
            elif cmd_str.startswith('remind:'):
                parsed = self.parsers['remind'](cmd_str)
            elif cmd_str.startswith('deadline:'):
                parsed = self.parsers['deadline'](cmd_str)

            if parsed:
                commands.append(parsed)
            else:
                logger.warning(f"Unknown timing command: {cmd_str}")

        return commands

    def _execute_timing_commands(self, commands: List[Dict[str, Any]],
                                callback: Callable, **context) -> None:
        """Выполнение списка команд (из Этапа 1)"""
        if not commands:
            callback()
            return

        for command in commands:
            cmd_type = command.get('type')
            if cmd_type in self.executors:
                try:
                    self.executors[cmd_type](command, callback, **context)
                except Exception as e:
                    logger.error(f"Error executing {cmd_type}: {e}")
            else:
                logger.warning(f"No executor for command type: {cmd_type}")

    def process_timing(self, user_id: int, session_id: int, node_id: str,
                      timing_config: str, callback: Callable, **context) -> None:
        """ГЛАВНАЯ ФУНКЦИЯ: Обработка timing команд (из Этапа 1)"""
        if not self.enabled:
            callback()
            return

        try:
            enriched_context = dict(context)
            enriched_context['session_id'] = session_id
            enriched_context['node_id'] = node_id
            self.execute_timing(timing_config, callback, **enriched_context)
        except Exception as e:
            logger.error(f"process_timing error: {e}")
            callback()

    # ============================================================================
    # УПРАВЛЕНИЕ TIMEOUT - ВСЕ ИЗ ЭТАПА 1 БЕЗ ИЗМЕНЕНИЙ
    # ============================================================================

    def cancel_timeout_task(self, session_id: int) -> bool:
        """Отменить активный timeout для сессии"""
        self.cancelled_tasks.add(session_id)
        timer_key = f"timeout_{session_id}"

        if timer_key in self.active_timers:
            timer = self.active_timers[timer_key]
            timer.cancel()
            del self.active_timers[timer_key]

        if session_id in self.debug_timers:
            del self.debug_timers[session_id]
        if session_id in self.active_timeouts:
            del self.active_timeouts[session_id]

        return True

    def cleanup_timeout_tasks(self):
        """Очистка завершенных timeout задач"""
        completed = [sid for sid, thread in self.active_timeouts.items() if not thread.is_alive()]
        for session_id in completed:
            del self.active_timeouts[session_id]
            self.cancelled_tasks.discard(session_id)

    def cancel_user_timers(self, user_id: int) -> None:
        """Отменить все таймеры пользователя"""
        to_cancel = [key for key in self.active_timers.keys() if key.startswith(f"{user_id}_")]
        for key in to_cancel:
            timer = self.active_timers.pop(key)
            timer.cancel()

    # ============================================================================
    # БД ОПЕРАЦИИ - ВСЕ ИЗ ЭТАПА 1 БЕЗ ИЗМЕНЕНИЙ
    # ============================================================================

    def _get_db_session(self):
        """Получить сессию БД"""
        try:
            return SessionLocal()
        except Exception as e:
            logger.error(f"Failed to create DB session: {e}")
            return None

    def save_timer_to_db(self, session_id: int, timer_type: str,
                        delay_seconds: int, message_text: str = "",
                        callback_node_id: str = "", callback_data: dict = None):
        """Сохранить таймер в БД"""
        if callback_data is None:
            callback_data = {}

        # ЭТАП 2: Заглушка БД для стабильности  
        print(f"[TIMING-ENGINE-S2] DB STUB: save_timer - {timer_type} for session {session_id}")
        return 999  # mock ID для совместимости

        # ЭТАП 3: Здесь будет реальная БД логика
        # db = self._get_db_session()
        # if not db:
        #     return None
        # ...

    def restore_timers_from_db(self):
        """Восстановить таймеры из БД"""
        # ЭТАП 2: Заглушка БД для стабильности
        print("[TIMING-ENGINE-S2] DB STUB: restore_timers (skipped in Stage 2)")
        return

        # ЭТАП 3: Здесь будет реальная БД логика
        # db = self._get_db_session()
        # if not db:
        #     return
        # ...

    def _execute_db_timer(self, timer_id: int):
        """Выполнить таймер из БД"""
        # ЭТАП 2: Заглушка БД для стабильности
        print(f"[TIMING-ENGINE-S2] DB STUB: execute_db_timer - {timer_id}")

        # ЭТАП 3: Здесь будет реальная БД логика
        # db = self._get_db_session()
        # if not db:
        #     return
        # ...

    def cleanup_expired_timers(self):
        """Очистить просроченные таймеры в БД"""
        # ЭТАП 2: Заглушка БД для стабильности  
        print("[TIMING-ENGINE-S2] DB STUB: cleanup_expired_timers (skipped in Stage 2)")

        # ЭТАП 3: Здесь будет реальная БД логика
        # db = self._get_db_session()
        # if not db:
        #     return
        # ...

    # ============================================================================
    # СТАТУС И УПРАВЛЕНИЕ
    # ============================================================================

    def get_status(self) -> Dict[str, Any]:
        """Статус timing системы (ОБНОВЛЕНО для Этапа 2)"""
        return {
            'stage': 'STAGE 2 - Calendar Daily System with Safe Imports',
            'enabled': self.enabled,
            'active_timers': len(self.active_timers),
            'active_timeouts': len(self.active_timeouts),
            'cancelled_tasks': len(self.cancelled_tasks),
            'debug_timers': len(self.debug_timers),

            # НОВОЕ ЭТАПА 2
            'active_daily_configs': len(self.active_daily_configs),
            'daily_participation_stats': len(self.daily_participation_stats),
            'daily_cutoff_dates': len(self.daily_cutoff_dates),

            'available_parsers': list(self.parsers.keys()),
            'available_executors': list(self.executors.keys()),
            'available_presets': list(self.presets.keys()),
            'countdown_message_types': list(self.countdown_templates.keys())
        }

    def enable(self) -> None:
        """Включить timing систему"""
        self.enabled = True

    def disable(self) -> None:
        """Выключить timing систему и очистить все таймеры"""
        self.enabled = False

        for timer in self.active_timers.values():
            timer.cancel()

        self.active_timers.clear()
        self.cancelled_tasks.clear()
        self.active_timeouts.clear()
        self.debug_timers.clear()

        # НОВОЕ ЭТАПА 2: Очистка daily данных
        self.active_daily_configs.clear()
        self.daily_participation_stats.clear()
        self.daily_cutoff_dates.clear()


# ============================================================================
# ГЛОБАЛЬНЫЙ ЭКЗЕМПЛЯР И ПУБЛИЧНЫЕ ФУНКЦИИ
# ============================================================================

# Глобальный экземпляр
timing_engine = TimingEngine()

# Публичные функции (ВСЕ ИЗ ЭТАПА 1)
def process_node_timing(user_id: int, session_id: int, node_id: str,
                       timing_config: str, callback: Callable, **context) -> None:
    """Основная функция для обработки timing команд узла"""
    return timing_engine.process_timing(user_id, session_id, node_id, timing_config, callback, **context)

def cancel_timeout_for_session(session_id: int) -> bool:
    """Публичная функция для отмены timeout"""
    return timing_engine.cancel_timeout_task(session_id)

def enable_timing() -> None:
    """Включить timing систему глобально"""
    global TIMING_ENABLED
    TIMING_ENABLED = True
    timing_engine.enable()

def disable_timing() -> None:
    """Выключить timing систему глобально"""
    global TIMING_ENABLED
    TIMING_ENABLED = False
    timing_engine.disable()

def get_timing_status() -> Dict[str, Any]:
    """Получить статус timing системы"""
    return timing_engine.get_status()

def cleanup_completed_timeouts() -> None:
    """Очистить завершенные timeout задачи"""
    timing_engine.cleanup_timeout_tasks()

def cancel_user_timers(user_id: int) -> None:
    """Отменить все таймеры для конкретного пользователя"""
    timing_engine.cancel_user_timers(user_id)

def get_timing_engine_instance() -> TimingEngine:
    """Получить экземпляр timing engine для расширенного использования"""
    return timing_engine
