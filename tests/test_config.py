from app.config.settings import load_settings

def test_default_settings():
    """Test that default settings are loaded correctly."""
    settings = load_settings()
    assert settings.app_name == "NOVA"
    assert settings.version == "0.1.0"
    assert isinstance(settings.debug, bool)
