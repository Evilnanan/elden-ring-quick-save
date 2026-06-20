"""Elden Ring 存档文件管理

所有存档存放在 <程序所在目录>/saves/<steam_id>/<profile>/ 下
每个存档就是一个以用户命名保存的 .sl2 文件
"""

import os
import shutil
import time
from typing import TypedDict

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


class SaveInfo(TypedDict):
    name: str
    path: str
    mtime: float  # 存档时间（修改时间）
    atime: float  # 读档时间（访问时间）


def _saves_dir(steam_id: str, profile: str) -> str:
    """返回此 Steam ID + Profile 的存档存储目录，若不存在则创建"""
    base = os.path.join(_SCRIPT_DIR, "saves")
    target = os.path.join(base, steam_id, profile)
    os.makedirs(target, exist_ok=True)
    return target


def _migrate_legacy(steam_id: str) -> None:
    """将旧版直接存放在 saves/<steam_id>/ 下的 .sl2 文件迁移到「默认」profile"""
    steam_dir = os.path.join(_SCRIPT_DIR, "saves", steam_id)
    if not os.path.isdir(steam_dir):
        return
    try:
        entries = list(os.scandir(steam_dir))
    except OSError:
        return

    sl2_files = [e for e in entries if e.is_file() and e.name.endswith(".sl2")]
    if not sl2_files:
        return

    default_dir = os.path.join(steam_dir, "默认")
    os.makedirs(default_dir, exist_ok=True)
    for entry in sl2_files:
        dst = os.path.join(default_dir, entry.name)
        if not os.path.exists(dst):
            os.rename(entry.path, dst)


def list_saves(steam_id: str, profile: str) -> list[SaveInfo]:
    """列出所有存档，按最近活动时间（max(atime, mtime)）倒序排列"""
    # 对「默认」profile 执行旧版数据迁移
    if profile == "默认":
        _migrate_legacy(steam_id)

    d = _saves_dir(steam_id, profile)
    results: list[SaveInfo] = []
    try:
        for entry in os.scandir(d):
            if entry.is_file() and entry.name.endswith(".sl2"):
                name = entry.name[:-4]  # 去掉 .sl2
                st = entry.stat()
                results.append(
                    {
                        "name": name,
                        "path": entry.path,
                        "mtime": st.st_mtime,
                        "atime": st.st_atime,
                    }
                )
    except OSError:
        pass
    results.sort(key=lambda x: max(x["atime"], x["mtime"]), reverse=True)
    return results


def _profile_last_activity(steam_id: str, profile: str) -> float:
    """返回某个 profile 下所有存档的最近活动时间（max(atime, mtime)），无存档时返回 0"""
    d = os.path.join(_SCRIPT_DIR, "saves", steam_id, profile)
    latest = 0.0
    try:
        for entry in os.scandir(d):
            if entry.is_file() and entry.name.endswith(".sl2"):
                st = entry.stat()
                latest = max(latest, st.st_atime, st.st_mtime)
    except OSError:
        pass
    return latest


def list_profiles(steam_id: str) -> list[str]:
    """列出某 Steam ID 下已有的 profile 目录，按最近活动时间降序排列"""
    steam_dir = os.path.join(_SCRIPT_DIR, "saves", steam_id)
    profiles: list[tuple[str, float]] = []
    try:
        for entry in os.scandir(steam_dir):
            if entry.is_dir():
                activity = _profile_last_activity(steam_id, entry.name)
                profiles.append((entry.name, activity))
    except OSError:
        pass
    # 按最近活动时间降序，同名时按名称排序保证稳定
    profiles.sort(key=lambda x: (-x[1], x[0]))
    return [p[0] for p in profiles]


def exists(steam_id: str, profile: str, name: str) -> bool:
    """检查指定存档名是否已存在"""
    return os.path.isfile(os.path.join(_saves_dir(steam_id, profile), f"{name}.sl2"))


def create_save(steam_id: str, profile: str, name: str, source_path: str) -> bool:
    """将 ER0000.sl2 复制为 <name>.sl2。若同名文件已存在则覆盖"""
    dst = os.path.join(_saves_dir(steam_id, profile), f"{name}.sl2")
    if not os.path.isfile(source_path):
        raise FileNotFoundError(f"游戏存档不存在: {source_path}")
    shutil.copy2(source_path, dst)
    return True


def load_save(steam_id: str, profile: str, name: str, target_path: str) -> bool:
    """将 <name>.sl2 复制回游戏目录覆盖 ER0000.sl2

    读档后更新源文件访问时间，用于排序
    """
    src = os.path.join(_saves_dir(steam_id, profile), f"{name}.sl2")
    if not os.path.isfile(src):
        raise FileNotFoundError(f"存档不存在: {name}")

    shutil.copy2(src, target_path)

    # 更新源文件的访问时间为当前时间，记录本次读档
    os.utime(src, (time.time(), os.path.getmtime(src)))
    return True


def delete_save(steam_id: str, profile: str, name: str) -> bool:
    """删除指定存档"""
    path = os.path.join(_saves_dir(steam_id, profile), f"{name}.sl2")
    if os.path.isfile(path):
        os.remove(path)
        return True
    return False


def delete_profile(steam_id: str, profile: str) -> bool:
    """删除整个 profile 目录及其下所有存档。「默认」不允许删除"""
    if profile == "默认":
        return False
    profile_dir = os.path.join(_SCRIPT_DIR, "saves", steam_id, profile)
    if os.path.isdir(profile_dir):
        shutil.rmtree(profile_dir)
        return True
    return False


def rename_save(steam_id: str, profile: str, old_name: str, new_name: str) -> bool:
    """重命名存档"""
    old_path = os.path.join(_saves_dir(steam_id, profile), f"{old_name}.sl2")
    new_path = os.path.join(_saves_dir(steam_id, profile), f"{new_name}.sl2")
    if not os.path.isfile(old_path):
        raise FileNotFoundError(f"存档不存在: {old_name}")
    if os.path.isfile(new_path):
        raise FileExistsError(f"存档已存在: {new_name} (请先删除或覆盖)")
    os.rename(old_path, new_path)
    return True
