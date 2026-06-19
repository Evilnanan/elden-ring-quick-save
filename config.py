"""配置持久化 — 将用户偏好保存到 JSON 文件

配置文件存放在 <程序所在目录>/config.json
"""

import json
import os
from typing import TypedDict

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


class ManualAccount(TypedDict):
    """手动添加的账号信息"""

    steam_id: str
    save_path: str


class AppConfig(TypedDict):
    save_hotkey: str
    load_hotkey: str
    manual_accounts: list[ManualAccount]


class AppConfigPartial(TypedDict, total=False):
    save_hotkey: str
    load_hotkey: str
    manual_accounts: list[ManualAccount]


_DEFAULT_CONFIG: AppConfig = {
    "save_hotkey": ",",
    "load_hotkey": ".",
    "manual_accounts": [],
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
        if "manual_accounts" in data and isinstance(data["manual_accounts"], list):
            validated: list[ManualAccount] = []
            for item in data["manual_accounts"]:
                if (
                    isinstance(item, dict)
                    and isinstance(item.get("steam_id"), str)
                    and isinstance(item.get("save_path"), str)
                    and item["steam_id"].strip()
                    and item["save_path"].strip()
                ):
                    validated.append(
                        {"steam_id": item["steam_id"], "save_path": item["save_path"]}
                    )
            config["manual_accounts"] = validated
    return config


def save_config(partial: AppConfigPartial) -> None:
    """合并写入配置 — 只更新传入的字段，其余保留原有值"""
    config = load_config()
    config.update(partial)
    path = _config_path()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


# ═══════════════════════════════════════════════════════════════
# 手动账号管理辅助函数
# ═══════════════════════════════════════════════════════════════


def load_manual_accounts() -> dict[str, str]:
    """加载手动添加的账号，返回 {steam_id: save_path}"""
    cfg = load_config()
    return {a["steam_id"]: a["save_path"] for a in cfg["manual_accounts"]}


def save_manual_accounts(accounts: dict[str, str]) -> None:
    """持久化手动添加的账号"""
    manual_list: list[ManualAccount] = [
        {"steam_id": sid, "save_path": path} for sid, path in accounts.items()
    ]
    save_config({"manual_accounts": manual_list})
