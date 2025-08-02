# restructured_bot/modules/channel_config.py

import os
import json

from . import core

CONFIG_FILE = os.path.join(core.DATA_DIR, "config.json")


def get_config() -> dict:
    """Retourne la configuration complète (channel, etc.)."""
    return core.load_json(CONFIG_FILE, {})


def save_config(config: dict) -> None:
    """Sauvegarde la configuration."""
    core.save_json(CONFIG_FILE, config)


def get_config_value(key: str, default=None):
    """Récupère une valeur spécifique de la configuration."""
    return get_config().get(key, default)


def set_config_value(key: str, value) -> None:
    """Modifie une valeur spécifique dans la configuration."""
    config = get_config()
    config[key] = value
    save_config(config)


def get_channel_id() -> int | None:
    """Raccourci : retourne l’ID du channel d’annonce."""
    return get_config_value("channel_id")


def set_channel_id(channel_id: int) -> None:
    """Raccourci : définit l’ID du channel d’annonce."""
    set_config_value("channel_id", channel_id)
