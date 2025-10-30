# rollback_instructions.md

План полного отката репозитория к состоянию коммита d5f615eb8460240e578c9ab767514cd563a6833b (30 Oct 2025 13:18 UTC):

1) Локально:
- git fetch origin
- git checkout main
- git reset --hard d5f615eb8460240e578c9ab767514cd563a6833b
- git push origin main --force

2) Проверка:
- Убедиться, что telegram_handler.py, timing_engine.py и связанные файлы соответствуют истории до внедрения TemporalAction.
- Запустить бота, проверить: картинки, калькулятор, базовые паузы из CSV (без новых таймеров).

3) После стабилизации:
- Создать ветку feature/timing-v2
- Внедрять новую функцию тайминга по шагам с отдельными PR и ревью.
