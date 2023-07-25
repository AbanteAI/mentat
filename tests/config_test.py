from mentat.config_manager import ConfigManager


def test_user_config(change_cwd):
    config = ConfigManager()

    assert not config.allow_32k()
