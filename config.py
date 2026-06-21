"""配置持久化 — 将用户偏好保存到 JSON 文件

配置文件存放在 <程序所在目录>/config.json
"""

import json
import os
from typing import TypedDict

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# 默认 profile 名称
DEFAULT_PROFILE = "默认"


class AppConfig(TypedDict):
    save_hotkey: str
    load_hotkey: str
    toggle_readonly_hotkey: str
    beep_enabled: bool


class AppConfigPartial(TypedDict, total=False):
    save_hotkey: str
    load_hotkey: str
    toggle_readonly_hotkey: str
    beep_enabled: bool


_DEFAULT_CONFIG: AppConfig = {
    "save_hotkey": ",",
    "load_hotkey": ".",
    "toggle_readonly_hotkey": "/",
    "beep_enabled": True,
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
        for key in ("save_hotkey", "load_hotkey", "toggle_readonly_hotkey"):
            if key in data and isinstance(data[key], str) and data[key].strip():
                config[key] = data[key]
        if "beep_enabled" in data and isinstance(data["beep_enabled"], bool):
            config["beep_enabled"] = data["beep_enabled"]
    return config


def save_config(partial: AppConfigPartial) -> None:
    """合并写入配置 — 只更新传入的字段，其余保留原有值"""
    config = load_config()
    config.update(partial)
    path = _config_path()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


# ═══════════════════════════════════════════════════════════════
# 一次性迁移 — 将旧版 config.json 中的 manual_accounts 转为 .savepath 文件
# ═══════════════════════════════════════════════════════════════


def migrate_manual_accounts_from_config() -> None:
    """将 config.json 中残留的 manual_accounts 迁移到 saves/<sid>/.savepath

    这是从旧版本到 .savepath 方案的一次性迁移。
    迁移完成后从 config.json 中删除 manual_accounts 字段。
    """
    path = _config_path()
    if not os.path.isfile(path):
        return

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return

    if not isinstance(data, dict):
        return

    manual = data.get("manual_accounts")
    if not isinstance(manual, list) or not manual:
        return

    saves_base = os.path.join(_SCRIPT_DIR, "saves")
    migrated = 0
    for item in manual:
        if not (
            isinstance(item, dict)
            and isinstance(item.get("steam_id"), str)
            and isinstance(item.get("save_path"), str)
            and item["steam_id"].strip()
            and item["save_path"].strip()
        ):
            continue
        sid = item["steam_id"]
        save_path = item["save_path"]
        account_dir = os.path.join(saves_base, sid)
        os.makedirs(account_dir, exist_ok=True)
        marker = os.path.join(account_dir, ".savepath")
        with open(marker, "w", encoding="utf-8") as f:
            f.write(save_path)
        migrated += 1

    if not migrated:
        return

    # 从 config.json 中移除 manual_accounts
    data.pop("manual_accounts", None)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
