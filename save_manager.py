"""Elden Ring 存档文件管理

所有存档存放在 <程序所在目录>/saves/<steam_id>/ 下
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


def _saves_dir(steam_id: str) -> str:
    """返回此 Steam ID 的存档存储目录，若不存在则创建"""
    base = os.path.join(_SCRIPT_DIR, "saves")
    target = os.path.join(base, steam_id)
    os.makedirs(target, exist_ok=True)
    return target


def list_saves(steam_id: str) -> list[SaveInfo]:
    """列出所有存档，按最近活动时间（max(atime, mtime)）倒序排列"""
    d = _saves_dir(steam_id)
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


def exists(steam_id: str, name: str) -> bool:
    """检查指定存档名是否已存在"""
    return os.path.isfile(os.path.join(_saves_dir(steam_id), f"{name}.sl2"))


def create_save(steam_id: str, name: str, source_path: str) -> bool:
    """将 ER0000.sl2 复制为 <name>.sl2。若同名文件已存在则覆盖"""
    dst = os.path.join(_saves_dir(steam_id), f"{name}.sl2")
    if not os.path.isfile(source_path):
        raise FileNotFoundError(f"游戏存档不存在: {source_path}")
    shutil.copy2(source_path, dst)
    return True


def load_save(steam_id: str, name: str, target_path: str) -> bool:
    """将 <name>.sl2 复制回游戏目录覆盖 ER0000.sl2

    读档后更新源文件访问时间，用于排序
    """
    src = os.path.join(_saves_dir(steam_id), f"{name}.sl2")
    if not os.path.isfile(src):
        raise FileNotFoundError(f"存档不存在: {name}")

    shutil.copy2(src, target_path)

    # 更新源文件的访问时间为当前时间，记录本次读档
    os.utime(src, (time.time(), os.path.getmtime(src)))
    return True


def delete_save(steam_id: str, name: str) -> bool:
    """删除指定存档"""
    path = os.path.join(_saves_dir(steam_id), f"{name}.sl2")
    if os.path.isfile(path):
        os.remove(path)
        return True
    return False


def rename_save(steam_id: str, old_name: str, new_name: str) -> bool:
    """重命名存档"""
    old_path = os.path.join(_saves_dir(steam_id), f"{old_name}.sl2")
    new_path = os.path.join(_saves_dir(steam_id), f"{new_name}.sl2")
    if not os.path.isfile(old_path):
        raise FileNotFoundError(f"存档不存在: {old_name}")
    if os.path.isfile(new_path):
        raise FileExistsError(f"存档已存在: {new_name} (请先删除或覆盖)")
    os.rename(old_path, new_path)
    return True
