# Task 7: Dynamic Phatic Threshold (Personalized Verbosity) & Memory Fix

## Концепция
Сейчас система считает сообщение "фатическим" (phatic), если в нём меньше 4 слов (жесткий хардкод в `pipeline.py`). Это не учитывает индивидуальный стиль общения пользователя. Нужно научить бота адаптироваться к "многословности" (verbosity) пользователя и динамически вычислять порог фатичности.

⚠️ **Критический багфикс**: В процессе проектирования обнаружен баг в `src/r_core/memory.py` в методе `update_user_profile`. Старая логика стирала не-trait атрибуты при попытке обновления профиля. Это необходимо исправить, иначе статистика слов не сохранится.

## Инструкция по реализации для локального агента

### Шаг 1: Исправление бага в `memory.py` и логика сохранения
В файле `src/r_core/memory.py`:

1. **Исправь метод `PostgresMemoryStore.update_user_profile`**. Замени блок `if "attributes" in data:` на:
```python
            if "attributes" in data: 
                current_attrs = dict(profile.attributes) if profile.attributes else {}
                
                # 1. Обновляем обычные ключи (например, avg_word_count)
                non_trait_data = {k: v for k, v in data["attributes"].items() if k != "personality_traits"}
                current_attrs.update(non_trait_data)
                
                # 2. Логика для traits
                if "personality_traits" in data["attributes"]:
                    traits = current_attrs.get("personality_traits", [])
                    new_traits_data = data["attributes"]["personality_traits"]
                    
                    if isinstance(new_traits_data, list):
                        MAX_SLOTS = 7
                        for candidate in new_traits_data:
                            match_found = False
                            for existing in traits:
                                if existing.get("name", "").lower() == candidate.get("name", "").lower():
                                    existing["weight"] = min(1.0, existing.get("weight", 0.5) + 0.1)
                                    existing["last_reinforced"] = datetime.utcnow().isoformat()
                                    match_found = True
                                    break
                            
                            if not match_found:
                                candidate["weight"] = candidate.get("weight", 0.5)
                                candidate["last_reinforced"] = datetime.utcnow().isoformat()
                                traits.append(candidate)
                        
                        if len(traits) > MAX_SLOTS:
                            traits.sort(key=lambda x: x.get("weight", 0.0), reverse=True)
                            traits = traits[:MAX_SLOTS]
                        
                        current_attrs["personality_traits"] = traits

                profile.attributes = current_attrs
```

2. **В классе `MemorySystem` добавь новый метод**:
```python
    async def update_verbosity_stats(self, user_id: int, word_count: int):
        profile = await self.store.get_user_profile(user_id)
        if profile:
            attrs = dict(profile.get("attributes", {}))
            current_avg = attrs.get("avg_word_count", 5.0)
            msg_analyzed = attrs.get("messages_analyzed", 0)
            
            new_msg_analyzed = msg_analyzed + 1
            new_avg = ((current_avg * msg_analyzed) + word_count) / new_msg_analyzed
            
            attrs["avg_word_count"] = float(f"{new_avg:.2f}")
            attrs["messages_analyzed"] = new_msg_analyzed
            
            await self.store.update_user_profile(user_id, {"attributes": attrs})
```

3. **Вызови этот метод** внутри `MemorySystem.memorize_event` сразу после сохранения сообщения в историю:
```python
        # 1. Save Raw User Message to History (STM)
        await self.store.save_chat_message(
            message.user_id, message.session_id, "user", message.text
        )
        
        # Update verbosity stats for Dynamic Phatic Threshold
        if message.text:
            word_count = len(message.text.split())
            await self.update_verbosity_stats(message.user_id, word_count)
```

### Шаг 2: Внедрение Dynamic Phatic Threshold
В файле `src/r_core/pipeline.py` в секции `=== Защита от коротких фраз (Phatic Bypass) ===` замени старый хардкод проверки длины на следующий код:

```python
        # === Защита от коротких фраз (Phatic Bypass) ===
        is_short_or_phatic = False
        word_count = 0
        if message.text:
            word_count = len(message.text.split())
            
            # Извлекаем статистику пользователя
            attributes = user_profile.get("attributes", {}) if user_profile else {}
            avg_word_count = attributes.get("avg_word_count", 5.0)
            dynamic_phatic_threshold = max(2, min(5, int(avg_word_count * 0.4)))
            
            phatic_patterns = ["ага", "ясно", "ок", "да", "нет", "хм", "мм", "угу", "ну", "понятно", "окей", "ладно", "чё", "да?", "и что?", "и что теперь?"]
            is_phatic_keyword = any(pattern in message.text.lower() for pattern in phatic_patterns)
            
            if word_count <= dynamic_phatic_threshold or (word_count <= dynamic_phatic_threshold + 1 and is_phatic_keyword):
                is_short_or_phatic = True
                print(f"[TopicTracker] ⏭️ Phatic message detected (words: {word_count}, threshold: {dynamic_phatic_threshold})")
```