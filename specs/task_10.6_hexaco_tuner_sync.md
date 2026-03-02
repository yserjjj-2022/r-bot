# Task 10.6: HEXACO & Personality Tuner Synchronization

## Контекст проблемы
В текущей реализации UI (Streamlit) и бэкенда (API/DB) существует рассинхронизация между двумя панелями управления агентом: новой «HEXACO Editor» и старой «Personality Tuner» (сырые гиперпараметры R-Core). 

**Текущие баги:**
1. **Потеря имени пресета**: При выборе пресета (например, `Machiavellian`) в Streamlit и сохранении, после перезагрузки страницы дропдаун сбрасывается. В базе данных (в PostgreSQL) УЖЕ ЕСТЬ колонка `personality_preset` (тип text), но она **не прописана** в SQLAlchemy-модели `AgentProfileModel` и в Pydantic-моделях API. Из-за этого ORM просто игнорирует это поле при чтении и записи.
2. **Рассинхрон параметров**: Когда пользователь меняет значения в «HEXACO Editor», они сохраняются в поле `hexaco_profile` в БД. Однако старая панель «Personality Tuner» продолжает использовать `sliders_preset`, и R-Core Kernel при инициализации берет неактуальные данные из `sliders_preset`.
3. **Bug в вызове API**: Метод `apply_preset` в `app_streamlit.py` не передает имя профиля в `requests.post`, из-за чего пресет применяется к дефолтному профилю, а не к текущему.

## Задача для локального агента

Необходимо обновить SQLAlchemy-модель, API и интерфейс Streamlit, чтобы они работали как единое целое. HEXACO должен выступать как высокоуровневый интерфейс, который автоматически пересчитывает и обновляет `sliders_preset` под капотом.

### Шаг 1: Обновление схемы БД (`src/r_core/infrastructure/db.py`)
1. Колонка в БД уже существует! Нам нужно просто добавить маппинг в класс `AgentProfileModel`:
   ```python
   personality_preset: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
   ```
   *(Никаких миграций в `init_models()` писать НЕ НАДО, так как колонка уже физически есть в базе).*

### Шаг 2: Обновление API (`src/interfaces/api.py`)
1. В Pydantic-моделях `HexacoProfileRequest` и `HexacoProfileResponse` добавить поле `personality_preset: Optional[str] = None`.
2. В эндпоинте `get_character_profile`:
   - Убедиться, что `personality_preset=profile.personality_preset` отдается в респонсе.
3. В эндпоинте `update_character_profile`:
   - Сохранять `request.personality_preset` в `profile.personality_preset`, если оно передано.
   - **КРИТИЧНО**: После обновления `hexaco_profile`, прогонять его через `TraitTranslationEngine` и **АВТОМАТИЧЕСКИ ПЕРЕЗАПИСЫВАТЬ** `profile.sliders_preset` полученными значениями:
     ```python
     translator = TraitTranslationEngine(profile.hexaco_profile)
     translated = translator.translate()
     profile.sliders_preset = {
         "empathy_bias": translated.empathy_bias,
         "risk_tolerance": translated.risk_tolerance,
         "dominance_level": translated.dominance_level,
         "pace_setting": translated.pace_setting,
         "chaos_level": translated.chaos_level,
         "persistence": translated.persistence,
         "pred_sensitivity": translated.pred_sensitivity,
         "learning_speed": profile.sliders_preset.get("learning_speed", 0.5), # Сохраняем те, что не зависят от HEXACO
         "pred_threshold": profile.sliders_preset.get("pred_threshold", 0.65)
     }
     ```
4. В эндпоинте `apply_preset`:
   - Устанавливать `profile.personality_preset = preset_name`.
   - Также прогонять пресет через `TraitTranslationEngine` и обновлять `profile.sliders_preset`.

### Шаг 3: Обновление UI (`app_streamlit.py`)
1. **Фикс API клиента**: В `def apply_preset(preset_name: str, profile_name: str) -> Optional[dict]:` добавить параметр `profile_name` и передавать его в `params={"profile_name": profile_name}` при POST-запросе.
2. В сайдбаре при выборе светлых/темных пресетов:
   ```python
   preset_hexaco = apply_preset(selected_light, st.session_state.bot_name)
   ```
3. После сохранения профиля (`save_character_profile` или `apply_preset`) обновлять не только `st.session_state.hexaco_profile`, но и извлекать из ответа API (поле `sliders_preset`) обновленные значения для `st.session_state.sliders`. Это заставит ползунки в «Personality Tuner» сдвинуться на новые значения, и ядро запустится с правильными весами.

## Ожидаемый результат
- Выбранный пресет читается из существующей колонки в БД и отображается при перезагрузке страницы.
- Изменение HEXACO и нажатие "Save" мгновенно сдвигает ползунки в Personality Tuner.
- R-Core Kernel инициализируется с переведенными значениями HEXACO.