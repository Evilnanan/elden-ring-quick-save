"""Steam 账号发现与 Elden Ring 存档路径定位"""

import os
import re
import struct
import winreg
from typing import TypedDict

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_SAVES_DIR = os.path.join(_SCRIPT_DIR, "saves")
_SAVEPATH_FILE = ".savepath"


class AccountInfo(TypedDict):
    """统一的账号信息"""

    name: str  # 用户名，手动添加的为空字符串
    save_path: str  # 存档文件的完整路径
    is_manual: bool  # 是否为手动添加


# ═══════════════════════════════════════════════════════════════
# 手动账号 — .savepath 文件操作
# ═══════════════════════════════════════════════════════════════


def get_manual_accounts() -> dict[str, str]:
    """扫描 saves/ 目录，返回所有手动添加的账号 {steam_id: save_path}

    手动账号的特征是 saves/<steam_id>/.savepath 文件存在，
    文件内容为存档路径。
    """
    result: dict[str, str] = {}
    if not os.path.isdir(_SAVES_DIR):
        return result
    try:
        for entry in os.scandir(_SAVES_DIR):
            if entry.is_dir():
                marker = os.path.join(entry.path, _SAVEPATH_FILE)
                if os.path.isfile(marker):
                    try:
                        with open(marker, "r", encoding="utf-8") as f:
                            save_path = f.read().strip()
                        if save_path:
                            result[entry.name] = save_path
                    except OSError:
                        pass
    except OSError:
        pass
    return result


def set_manual_account(steam_id: str, save_path: str) -> None:
    """创建手动账号的 .savepath 标记文件"""
    account_dir = os.path.join(_SAVES_DIR, steam_id)
    os.makedirs(account_dir, exist_ok=True)
    marker = os.path.join(account_dir, _SAVEPATH_FILE)
    with open(marker, "w", encoding="utf-8") as f:
        f.write(save_path)


def remove_manual_account_marker(steam_id: str) -> None:
    """删除手动账号的 .savepath 标记文件（不删除存档目录）"""
    marker = os.path.join(_SAVES_DIR, steam_id, _SAVEPATH_FILE)
    if os.path.isfile(marker):
        os.remove(marker)


# ═══════════════════════════════════════════════════════════════
# Steam 自动检测
# ═══════════════════════════════════════════════════════════════


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


# ═══════════════════════════════════════════════════════════════
# 统一账号获取
# ═══════════════════════════════════════════════════════════════


def get_all_accounts() -> dict[str, AccountInfo]:
    """获取所有账号（自动检测 + 手动添加），返回 {steam_id: AccountInfo}

    手动添加的排在最前面（优先显示），自动检测的按存档活动时间排序。
    """
    result: dict[str, AccountInfo] = {}

    # ── 手动添加的账号（通过 saves/ 下的 .savepath 标记文件识别）──
    for sid, save_path in get_manual_accounts().items():
        result[sid] = AccountInfo(
            name="",
            save_path=save_path,
            is_manual=True,
        )

    # ── 自动检测的 Steam 账号 ──
    for sid, name in get_all_steam_accounts().items():
        if sid not in result:  # 手动添加的同 ID 优先
            result[sid] = AccountInfo(
                name=name,
                save_path=get_elden_ring_save_path(sid),
                is_manual=False,
            )

    return result
