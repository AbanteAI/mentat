from mentat.config_manager import ConfigManager


def test_user_config():
    config = ConfigManager()

    assert config.allow_32k() is not None
