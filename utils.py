"""工具函数"""

import re

# Windows 文件名非法字符
_ILLEGAL_CHARS_RE = re.compile(r'[<>:"/\\|?*]')

# Windows 保留文件名（不区分大小写）
_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def sanitize_filename(name: str) -> str:
    """移除文件名中的非法字符"""
    return _ILLEGAL_CHARS_RE.sub("", name)


def validate_filename(name: str) -> str | None:
    """验证文件名是否合法。返回 None 表示合法，否则返回错误信息字符串。"""
    if not name or not name.strip():
        return "名称不能为空"
    if _ILLEGAL_CHARS_RE.search(name):
        return '名称不能包含以下字符：< > : " / \\ | ? *'
    if name.upper() in _RESERVED_NAMES:
        return f"「{name}」是 Windows 保留名称，不能使用"
    if len(name) > 200:
        return "名称过长（最多 200 个字符）"
    return None


def fuzzy_match(keyword: str, name: str) -> bool:
    """空格拆分多词条匹配：每个词必须在名称中出现（不区分大小写）"""
    if not keyword.strip():
        return True
    name_lower = name.lower()
    return all(kw in name_lower for kw in keyword.lower().split())


def key_display(key: str) -> str:
    """友好显示键名，支持组合键"""
    name_map = {
        "ctrl": "Ctrl",
        "alt": "Alt",
        "shift": "Shift",
        "win": "Win",
        " ": "Space",
        "space": "Space",
    }
    parts = key.split("+")
    return " + ".join(name_map.get(p, p) for p in parts)
