# test_etap0.py
# Тестирование Этапа 0

from app.modules.database import models
from app.config.feature_flags import FeatureFlags, is_timing_enabled

def test_models_import():
    """Тест импорта новых моделей"""
    print("🧪 Тестирование импорта моделей...")
    
    try:
        # Проверяем что новые классы существуют
        assert hasattr(models, 'ActiveTimer')
        assert hasattr(models, 'ResearchGroup') 
        assert hasattr(models, 'GroupParticipant')
        assert hasattr(models, 'GroupEvent')
        
        print("✅ Все новые модели импортируются")
        return True
    except Exception as e:
        print(f"❌ Ошибка импорта: {e}")
        return False

def test_feature_flags():
    """Тест системы feature flags"""
    print("🧪 Тестирование feature flags...")
    
    try:
        # Проверяем базовую функциональность
        assert not FeatureFlags.ENABLE_AI_IMPORTANCE_ANALYSIS
        assert FeatureFlags.ENABLE_NEW_DB_FIELDS
        assert not is_timing_enabled()
        
        # Тестируем динамическое включение
        FeatureFlags.enable_feature('ENABLE_DELAYED_MESSAGES')
        assert FeatureFlags.ENABLE_DELAYED_MESSAGES
        assert is_timing_enabled()
        
        print("✅ Feature flags работают")
        return True
    except Exception as e:
        print(f"❌ Ошибка feature flags: {e}")
        return False

def test_utc_function():
    """Тест функции utc_now"""
    print("🧪 Тестирование utc_now...")
    
    try:
        from app.modules.database.models import utc_now
        import datetime
        
        now = utc_now()
        assert isinstance(now, datetime.datetime)
        assert now.tzinfo is not None  # Проверяем что timezone-aware
        
        print("✅ utc_now функция работает")
        return True
    except Exception as e:
        print(f"❌ Ошибка utc_now: {e}")
        return False

if __name__ == "__main__":
    print("🚀 ТЕСТИРОВАНИЕ ЭТАПА 0")
    print("=" * 50)
    
    tests = [
        test_models_import,
        test_feature_flags, 
        test_utc_function
    ]
    
    passed = 0
    for test in tests:
        if test():
            passed += 1
    
    print("=" * 50)
    print(f"📊 РЕЗУЛЬТАТ: {passed}/{len(tests)} тестов прошли")
    
    if passed == len(tests):
        print("🎉 ЭТАП 0 ГОТОВ! Можно переходить к Спринту 1!")
    else:
        print("⚠️  Есть проблемы, нужно исправить")
