"""Steam 账号发现与 Elden Ring 存档路径定位"""

import os
import re
import struct
import winreg


def get_steam_install_path() -> str | None:
    """从 Windows 注册表获取 Steam 安装路径"""
    key_path = (
        r"SOFTWARE\WOW6432Node\Valve\Steam" if _is_64bit() else r"SOFTWARE\Valve\Steam"
    )
    try:
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path)
        value, _ = winreg.QueryValueEx(key, "InstallPath")
        winreg.CloseKey(key)
        return value
    except OSError:
        return None


def get_all_steam_accounts() -> dict[str, str]:
    """解析 loginusers.vdf，返回 {steam_id: account_name}

    按存档文件最近读档时间（atime）降序排列，未读取过的存档则取修改时间（mtime），
    无存档文件的排到最后。
    每个 steam_id 为 17 位数字字符串
    """
    accounts: dict[str, str] = {}
    steam_path = get_steam_install_path()
    if not steam_path:
        return accounts

    login_users_path = os.path.join(steam_path, "config", "loginusers.vdf")
    if not os.path.isfile(login_users_path):
        return accounts

    try:
        with open(login_users_path, "r", encoding="utf-8") as f:
            content = f.read()
    except OSError:
        return accounts

    # 匹配 "17位数字" { ... "AccountName" "名称" }
    pattern = re.compile(
        r'"(\d{17})"\s*\{[^}]*?"AccountName"\s*"([^"]+)"',
        re.DOTALL,
    )
    for match in pattern.finditer(content):
        accounts[match.group(1)] = match.group(2)

    # 按存档最近读档时间排序，未读取过的取修改时间，无存档的排最后
    def _save_atime(sid: str) -> float:
        save_path = get_elden_ring_save_path(sid)
        try:
            s = os.stat(save_path)
            # st_atime 是访问时间（读档会更新），st_mtime 是修改时间（存档会更新）
            # atime >= mtime 表示至少读过一次；atime < mtime 说明从未读取，用 mtime
            return max(s.st_atime, s.st_mtime)
        except OSError:
            return 0.0  # 无存档 → 排最后

    sorted_ids = sorted(accounts.keys(), key=_save_atime, reverse=True)
    return {sid: accounts[sid] for sid in sorted_ids}


def get_elden_ring_save_path(steam_id: str) -> str:
    """返回 ER0000.sl2 的完整路径"""
    appdata = os.getenv("APPDATA", "")
    return os.path.join(appdata, "EldenRing", steam_id, "ER0000.sl2")


def _is_64bit() -> bool:
    """检测当前系统是否为 64 位"""
    return struct.calcsize("P") * 8 == 64
