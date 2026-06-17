from app.config.settings import settings


def test_app_name():
    assert "Goals" in settings.APP_NAME


def test_default_port():
    assert settings.PORT == 8002


def test_momentum_window_positive():
    assert settings.MOMENTUM_WINDOW_DAYS > 0


def test_low_threshold_range():
    assert 0 < settings.MOMENTUM_LOW_THRESHOLD < 100
