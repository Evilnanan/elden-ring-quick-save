"""配置持久化 — 将用户偏好保存到 JSON 文件

配置文件存放在 <程序所在目录>/config.json
"""

import json
import os
from typing import TypedDict

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


class AppConfig(TypedDict):
    save_hotkey: str
    load_hotkey: str


class AppConfigPartial(TypedDict, total=False):
    save_hotkey: str
    load_hotkey: str


_DEFAULT_CONFIG: AppConfig = {
    "save_hotkey": ",",
    "load_hotkey": ".",
}


def _config_path() -> str:
    """配置文件路径（程序所在目录下的 config.json）"""
    return os.path.join(_SCRIPT_DIR, "config.json")


def load_config() -> AppConfig:
    """加载配置，文件不存在时返回默认值"""
    path = _config_path()
    if not os.path.isfile(path):
        return _DEFAULT_CONFIG.copy()

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return _DEFAULT_CONFIG.copy()

    config = _DEFAULT_CONFIG.copy()
    if isinstance(data, dict):
        for key in ("save_hotkey", "load_hotkey"):
            if key in data and isinstance(data[key], str) and data[key].strip():
                config[key] = data[key]
    return config


def save_config(partial: AppConfigPartial) -> None:
    """合并写入配置 — 只更新传入的字段，其余保留原有值"""
    config = load_config()
    config.update(partial)
    path = _config_path()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
