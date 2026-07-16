import json
from pathlib import Path


def _load_plugin(path: Path, class_name: str):
    import importlib.util

    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, class_name)()


def test_telegram_handler_declares_web_origin():
    plugin = _load_plugin(
        Path("/home/ghostrider/Projects/tokenade-plugins/plugins/telegram-handler/plugin.py"),
        "TelegramSiteHandler",
    )

    assert plugin.get_storage_origins() == ["https://web.telegram.org"]


def test_telegram_handler_validates_real_storage_shape():
    plugin = _load_plugin(
        Path("/home/ghostrider/Projects/tokenade-plugins/plugins/telegram-handler/plugin.py"),
        "TelegramSiteHandler",
    )
    session = {
        "storage": {
            "local": {
                "https://web.telegram.org": {
                    "dc5_auth_key": '"auth-key"',
                    "user_auth": '{"dcID":5,"id":"123"}',
                }
            }
        }
    }

    result = plugin.validate(session)

    assert result.success
    assert result.data["valid"] is True


def test_discord_handler_reads_canonical_storage_shape():
    plugin = _load_plugin(
        Path("/home/ghostrider/Projects/tokenade-plugins/plugins/discord-handler/plugin.py"),
        "DiscordSiteHandler",
    )
    session = {
        "cookies": [
            {"name": "__dcfduid", "domain": "discord.com"},
            {"name": "__sdcfduid", "domain": "discord.com"},
            {"name": "discord_locale", "domain": "discord.com"},
        ],
        "storage": {
            "local": {
                "https://discord.com": {"token": '"discord-token"'}
            }
        },
    }

    result = plugin.validate(session)

    assert result.success
    assert result.data["valid"] is True
