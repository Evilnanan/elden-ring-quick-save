"""全局热键监听，使用 keyboard 库实现低层键盘钩子

keyboard 库内部自带后台监听线程，无需额外创建线程
热键回调通过 queue.Queue 将事件发送到主线程，保证 Tkinter 线程安全
"""

import queue
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from enum import Enum

import keyboard


class HotkeyAction(Enum):
    SAVE = "save"
    LOAD = "load"
    TOGGLE_READONLY = "toggle_readonly"


class HotkeyManager:
    """管理全局热键注册、修改与取消"""

    def __init__(
        self,
        save_hotkey: str = ",",
        load_hotkey: str = ".",
        toggle_readonly_hotkey: str = "/",
    ) -> None:
        self._save_hotkey = save_hotkey
        self._load_hotkey = load_hotkey
        self._toggle_readonly_hotkey = toggle_readonly_hotkey
        self._queue: queue.Queue[HotkeyAction] = queue.Queue()
        self._running = False
        self._suppress_count = 0
        self._enabled = True
        self._save_handle: Callable[[], None] | None = None
        self._load_handle: Callable[[], None] | None = None
        self._toggle_readonly_handle: Callable[[], None] | None = None

    # ── 属性 ────────────────────────────────────────────

    @property
    def save_hotkey(self) -> str:
        return self._save_hotkey

    @property
    def load_hotkey(self) -> str:
        return self._load_hotkey

    @property
    def toggle_readonly_hotkey(self) -> str:
        return self._toggle_readonly_hotkey

    @property
    def event_queue(self) -> queue.Queue:
        return self._queue

    @property
    def enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, enabled: bool) -> None:
        """全局热键开关"""
        self._enabled = enabled

    # ── 热键修改 ────────────────────────────────────────

    def set_save_hotkey(self, key: str) -> None:
        """修改存档热键，运行中即时生效"""
        self._save_hotkey = key
        if self._running:
            self._rehook_save()

    def set_load_hotkey(self, key: str) -> None:
        """修改读档热键，运行中即时生效"""
        self._load_hotkey = key
        if self._running:
            self._rehook_load()

    def _rehook_save(self) -> None:
        if self._save_handle is not None:
            try:
                keyboard.remove_hotkey(self._save_handle)
            except Exception:
                pass
        self._save_handle = keyboard.add_hotkey(self._save_hotkey, self._on_save)

    def _rehook_load(self) -> None:
        if self._load_handle is not None:
            try:
                keyboard.remove_hotkey(self._load_handle)
            except Exception:
                pass
        self._load_handle = keyboard.add_hotkey(self._load_hotkey, self._on_load)

    def set_toggle_readonly_hotkey(self, key: str) -> None:
        """修改只读切换热键，运行中即时生效"""
        self._toggle_readonly_hotkey = key
        if self._running:
            self._rehook_toggle_readonly()

    def _rehook_toggle_readonly(self) -> None:
        if self._toggle_readonly_handle is not None:
            try:
                keyboard.remove_hotkey(self._toggle_readonly_handle)
            except Exception:
                pass
        self._toggle_readonly_handle = keyboard.add_hotkey(
            self._toggle_readonly_hotkey, self._on_toggle_readonly
        )

    # ── 屏蔽 ──────────────────────────────────────────

    @contextmanager
    def suppressed(self) -> Iterator[None]:
        """上下文管理器：暂时屏蔽热键事件，退出时自动恢复。支持嵌套。

        用法:
            with hotkey_manager.suppressed():
                ...  # 热键被屏蔽

        对于异步场景（跨回调），可手动调用 __enter__ / __exit__:
            guard = hotkey_manager.suppressed()
            guard.__enter__()
            ...
            guard.__exit__(None, None, None)
        """
        self._suppress_count += 1
        try:
            yield
        finally:
            self._suppress_count = max(0, self._suppress_count - 1)

    # ── 生命周期 ────────────────────────────────────────

    def start(self) -> None:
        """注册全局热键（keyboard 库自动管理后台线程）"""
        if self._running:
            return
        self._running = True

        self._save_handle = keyboard.add_hotkey(self._save_hotkey, self._on_save)
        self._load_handle = keyboard.add_hotkey(self._load_hotkey, self._on_load)
        self._toggle_readonly_handle = keyboard.add_hotkey(
            self._toggle_readonly_hotkey, self._on_toggle_readonly
        )

    def stop(self) -> None:
        """移除所有热键"""
        self._running = False
        try:
            keyboard.unhook_all()
        except Exception:
            pass
        self._save_handle = None
        self._load_handle = None
        self._toggle_readonly_handle = None

    def _on_save(self) -> None:
        if self._enabled and self._suppress_count == 0:
            self._queue.put(HotkeyAction.SAVE)

    def _on_load(self) -> None:
        if self._enabled and self._suppress_count == 0:
            self._queue.put(HotkeyAction.LOAD)

    def _on_toggle_readonly(self) -> None:
        if self._enabled and self._suppress_count == 0:
            self._queue.put(HotkeyAction.TOGGLE_READONLY)
