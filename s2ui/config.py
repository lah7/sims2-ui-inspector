"""
Configuration to persist settings between sessions.
"""
import configparser
import os
import sys


def get_config_folder() -> str:
    """
    Get a path to the app's save folder. Create the directory if necessary.
    """
    match sys.platform:
        case "linux":
            config_dir = os.path.join(os.getenv("XDG_CONFIG_HOME", os.path.expanduser("~/.config")), "s2ui_inspector")
        case "win32":
            config_dir = os.path.join(os.getenv("LOCALAPPDATA", ""), "s2ui_inspector")
        case "darwin":
            config_dir = os.path.join(os.getenv("HOME", ""), "Library", "Application Support", "s2ui_inspector")
        case _:
            raise OSError("Unknown platform for storing configuration files")

    if not os.path.exists(config_dir):
        os.makedirs(config_dir)

    return config_dir


class Preferences:
    """
    Persistent configuration for the application set by the user.
    """
    def __init__(self):
        self.config = configparser.ConfigParser()
        self.config_file = os.path.join(get_config_folder(), "settings.ini")
        self.config.read(self.config_file)

    def _get_key(self, group: str, key: str) -> str:
        """Get a key from the configuration file"""
        if not self.config.has_section(group):
            self.config.add_section(group)
        return self.config.get(group, key, fallback="")

    def _update_key(self, group: str, key: str, value: str):
        """Update the configuration file with the current settings"""
        if not self.config.has_section(group):
            self.config.add_section(group)
        self.config.set(group, key, value)
        with open(self.config_file, "w", encoding="utf-8") as f:
            self.config.write(f)

    def get_last_opened_dir(self) -> str:
        """Get the last opened package or game directory"""
        return self._get_key("General", "last_opened_dir")

    def set_last_opened_dir(self, directory: str):
        """Remember the last opened file or game directory"""
        self._update_key("General", "last_opened_dir", directory)
