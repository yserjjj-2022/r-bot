diff --git a/app/modules/timing_engine.py b/app/modules/timing_engine.py
index 3f71880..f6d0b2e 100644
--- a/app/modules/timing_engine.py
+++ b/app/modules/timing_engine.py
@@
-from app.modules.database.models import ActiveTimer, utc_now
-from app.modules.database import SessionLocal
+from app.modules.database.models import ActiveTimer, utc_now
+from app.modules.database import SessionLocal
+from app.modules.timing_primitives.dynamic_pause import DynamicPause
@@
-    def _execute_typing(self, command: Dict[str, Any], callback: Callable, **context) -> None:
-        """Выполнение typing с preset'ами"""
-        duration = command['duration']
-        process_name = command.get('process_name', 'Обработка')
-        preset = command.get('preset', 'clean')
-        exposure_time = command.get('exposure_time', 1.5)
-        anti_flicker_delay = command.get('anti_flicker_delay', 1.0)
-        action = command.get('action', 'delete')
-
-        session_id = context.get('session_id')
-        if session_id:
-            self.save_timer_to_db(
-                session_id=session_id, timer_type='typing',
-                delay_seconds=int(duration), message_text=process_name,
-                callback_data={'command': command, 'preset': preset}
-            )
-
-        bot = context.get('bot')
-        chat_id = context.get('chat_id')
-        if bot and chat_id:
-            def show_progress_with_presets():
-                try:
-                    self._show_progress_bar_with_presets(
-                        bot, chat_id, duration, process_name, 
-                        show_progress=True, exposure_time=exposure_time,
-                        anti_flicker_delay=anti_flicker_delay, action=action
-                    )
-                    callback()
-                except Exception as e:
-                    callback()
-
-            threading.Thread(target=show_progress_with_presets).start()
-        else:
-            threading.Timer(duration, callback).start()
+    def _execute_typing(self, command: Dict[str, Any], callback: Callable, **context) -> None:
+        """Выполнение typing через примитив DynamicPause (этап 1: безопасная пауза)"""
+        duration = float(command.get('duration', 0))
+        process_name = command.get('process_name', 'Обработка')
+
+        bot = context.get('bot')
+        chat_id = context.get('chat_id')
+
+        pause = DynamicPause(bot=bot, chat_id=chat_id, duration=duration, fill_type='silent', message_text=process_name)
+        pause.execute(on_complete_callback=callback)
@@
-    def _execute_process(self, command: Dict[str, Any], callback: Callable, **context) -> None:
-        """Выполнение статических процессов (замена state: true)"""
-        duration = command['duration']
-        process_name = command.get('process_name', 'Процесс')
-        preset = command.get('preset', 'clean')
-        exposure_time = command.get('exposure_time', 1.5)
-        anti_flicker_delay = command.get('anti_flicker_delay', 1.0)
-        action = command.get('action', 'delete')
-
-        session_id = context.get('session_id')
-        if session_id:
-            self.save_timer_to_db(
-                session_id=session_id, timer_type='process',
-                delay_seconds=int(duration), message_text=process_name,
-                callback_data={'command': command, 'preset': preset}
-            )
-
-        bot = context.get('bot')
-        chat_id = context.get('chat_id')
-        if bot and chat_id:
-            def show_static_process():
-                try:
-                    self._show_progress_bar_with_presets(
-                        bot, chat_id, duration, process_name,
-                        show_progress=False, exposure_time=exposure_time,
-                        anti_flicker_delay=anti_flicker_delay, action=action
-                    )
-                    callback()
-                except Exception as e:
-                    callback()
-
-            threading.Thread(target=show_static_process).start()
-        else:
-            threading.Timer(duration, callback).start()
+    def _execute_process(self, command: Dict[str, Any], callback: Callable, **context) -> None:
+        """Выполнение process через примитив DynamicPause (этап 1: безопасная пауза)"""
+        duration = float(command.get('duration', 0))
+        process_name = command.get('process_name', 'Процесс')
+
+        bot = context.get('bot')
+        chat_id = context.get('chat_id')
+
+        pause = DynamicPause(bot=bot, chat_id=chat_id, duration=duration, fill_type='silent', message_text=process_name)
+        pause.execute(on_complete_callback=callback)
