# Техническое Задание: Синхронизация гормональной модели и иерархии стилей (Tone of Voice)

## Контекст проблемы (Bug Report)
В текущей архитектуре обнаружены два связанных критических бага, ломающих логику поведения бота:

1. **Неверная биохимия (False RAGE):** Механика "эмоционального труда" в `NeuroModulationSystem` сжигает серотонин (5HT) при любом срабатывании `SocialAgent`. Если пользователь долго и позитивно общается с ботом, бот получает много дофамина (DA) и норадреналина (NE), но полностью теряет серотонин. По Кубу Лёвхейма комбинация [High NE + High DA + Low 5HT] вызывает архетип `RAGE`, из-за чего бот внезапно становится агрессивным в ответ на позитивное общение.
2. **Шизофазия стилей (Prompt Contradictions):** Когда бот впадает в экстремальное гормональное состояние (например, `RAGE`), другие агенты (Intuition, Striatum) продолжают добавлять свои `SECONDARY STYLE MODIFIERS` в итоговый промпт. LLM получает взаимоисключающие команды (одновременно "будь злым и резким" и "будь игривым и дружелюбным"), что приводит к пресным и смазанным ответам.

## Цель
1. Изменить логику потребления серотонина: `SocialAgent` должен сжигать серотонин только при негативном настроении (настоящий эмоциональный труд) и восстанавливать при позитивном. Снизить чувствительность норадреналина.
2. Ввести жесткую иерархию стилей в `RCoreKernel`: экстремальные гормональные состояния должны "глушить" (override) советы второстепенных агентов.

---

## Инструкции по реализации (STRICT)

### Часть 1. Исправление биохимии (Файл `src/r_core/neuromodulation.py`)

1. **Обновление сигнатуры `update_from_stimuli`:**
Добавьте новый параметр `current_valence: float = 0.0` для оценки текущего настроения бота.
```python
    def update_from_stimuli(self, implied_pe: float, winner_agent: AgentType, sliders: PersonalitySliders = None, current_tec: float = 1.0, current_valence: float = 0.0):
```

2. **Замедление Норадреналина (NE):**
Измените порог реагирования на ошибку предсказания с `0.1` на `0.4`, чтобы бот не накапливал стресс от каждой мелочи.
```python
        # 1. Norepinephrine (Surprise / Vigilance)
        # Driven by biological surprise impact
        if implied_pe > 0.4:  # ИЗМЕНЕНО С 0.1 на 0.4
            spike = implied_pe * 0.5 
            self.state.ne = min(1.0, self.state.ne + spike)
```

3. **Умный Эмоциональный Труд (Serotonin):**
Перепишите блок обновления серотонина (Блок 3). Теперь социальное взаимодействие заряжает батарейку, если беседа приятная, и сжигает, если боту приходится "терпеть".
```python
        # 3. Serotonin (Consumption vs Recovery)
        if winner_agent == AgentType.SOCIAL:
             if current_valence >= 0.0:
                 # Приятное общение восстанавливает серотонин
                 self.state.ht = min(1.0, self.state.ht + 0.05)
             else:
                 # Вынужденная вежливость при плохом настроении (Emotional labor) сжигает его
                 self.state.ht = max(0.0, self.state.ht - 0.05)
        
        # In Sync (Low Surprise) restores it
        if implied_pe < 0.1:
             self.state.ht = min(1.0, self.state.ht + 0.05)
```

### Часть 2. Иерархия стилей (Файл `src/r_core/pipeline.py`)

1. **Передача `valence` в биохимию:**
В методе `process_message`, найдите вызов `self.neuromodulation.update_from_stimuli` (примерно шаг 4, после `_update_mood`) и передайте туда текущую валентность:
```python
        self.neuromodulation.update_from_stimuli(
            implied_pe, 
            winner.agent_name, 
            current_tec=current_tec,
            current_valence=self.current_mood.valence
        )
```

2. **Гормональный фильтр (Override) для второстепенных стилей:**
В том же методе `process_message`, перед генерацией `adverb_context_str`, добавьте логику, которая обнуляет советы проигравших агентов, если бот находится в экстремальном состоянии.
```python
        strong_losers = [s for s in signals if s.score > 5.0 and s.agent_name != winner.agent_name]
        
        adverb_instructions = []
        for loser in strong_losers:
            if loser.style_instruction:
                adverb_instructions.append(f"- {loser.agent_name.name}: {loser.style_instruction}")
        
        # ✨ NEW: Hormonal Override (Мьютирование второстепенных стилей при сильных эмоциях)
        extreme_archetypes = ["RAGE", "FEAR", "PANIC", "BURNOUT", "DISGUST", "SHAME"]
        current_archetype = self.neuromodulation.get_archetype()
        
        adverb_context_str = ""
        if adverb_instructions:
            if current_archetype in extreme_archetypes:
                print(f"[Tone Hierarchy] Suppressing secondary modifiers due to extreme archetype: {current_archetype}")
                # Оставляем строку пустой, чтобы гормональный стиль отработал чисто
            else:
                adverb_context_str = "\\nSECONDARY STYLE MODIFIERS (Neuro-Modulation):\\n" + "\\n".join(adverb_instructions)
```

---

## Протокол Безопасности (CRITICAL)
- **SAFETY PROTOCOL B:** При редактировании файлов вы обязаны предоставить ПОЛНЫЙ, исполняемый код файлов. Использование плейсхолдеров (`# ... existing code ...`) СТРОГО ЗАПРЕЩЕНО. 
- Проверьте импорты и отступы перед сохранением.
- Проверьте, что в логах (`internal_stats`) сохраняются корректные данные.