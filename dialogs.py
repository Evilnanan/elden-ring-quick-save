"""对话框：热键修改、存档、读档、重命名、手动添加账号"""

import sys
import tkinter as tk
from collections.abc import Callable
from tkinter import filedialog, messagebox, ttk

from save_manager import SaveInfo

import keyboard

from utils import fuzzy_match, key_display, sanitize_filename, validate_filename

# ═══════════════════════════════════════════════════════════════
# Windows 焦点抢占 — 绕过 SetForegroundWindow 限制
# ═══════════════════════════════════════════════════════════════

if sys.platform == "win32":
    import ctypes as _ctypes

    def _win32_force_focus(hwnd: int) -> bool:
        """通过 AttachThreadInput 绕过 Windows 焦点抢占限制

        Windows 默认禁止后台进程使用 SetForegroundWindow 抢夺焦点。
        短暂将当前线程附加到前台线程的输入队列后，即可合法转移焦点。

        返回 True 表示成功；返回 False 时调用方可回退到 focus_force()。
        """
        try:
            user32 = _ctypes.windll.user32
            kernel32 = _ctypes.windll.kernel32

            if hwnd == user32.GetForegroundWindow():
                return True  # 已在前台，无需操作

            current_thread = kernel32.GetCurrentThreadId()
            foreground_thread = user32.GetWindowThreadProcessId(
                user32.GetForegroundWindow(), None
            )

            attached = False
            if current_thread != foreground_thread:
                user32.AttachThreadInput(current_thread, foreground_thread, True)
                attached = True

            # SW_SHOW = 5 — 激活并显示窗口
            user32.ShowWindow(hwnd, 5)
            user32.SetForegroundWindow(hwnd)
            user32.SetFocus(hwnd)

            if attached:
                user32.AttachThreadInput(current_thread, foreground_thread, False)
            return True
        except Exception:
            return False

else:

    def _win32_force_focus(hwnd: int) -> bool:
        return False


# ═══════════════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════════════


def bring_to_front(dlg: tk.Toplevel) -> None:
    """将对话框提至前台并聚焦"""
    dlg.lift()
    dlg.attributes("-topmost", True)
    dlg.after(0, lambda: dlg.attributes("-topmost", False))
    if not _win32_force_focus(dlg.winfo_id()):
        dlg.focus_force()  # AttachThreadInput 失败时回退


# ═══════════════════════════════════════════════════════════════
# 安全文件名输入框
# ═══════════════════════════════════════════════════════════════


class SafeFilenameEntry(ttk.Entry):
    """文件名输入框：输入时自动剥离 Windows 非法字符（<>:"/\\|?*）"""

    def __init__(self, master, textvariable: tk.StringVar, **kwargs) -> None:
        self._safe_var = textvariable
        super().__init__(
            master,
            textvariable=textvariable,
            validate="key",
            validatecommand=(master.register(self._sanitize), "%P"),
            **kwargs,
        )

    def _sanitize(self, proposed: str) -> bool:
        cleaned = sanitize_filename(proposed)
        if cleaned != proposed:
            self._safe_var.set(cleaned)
            return False
        return True


# ═══════════════════════════════════════════════════════════════
# 热键修改对话框
# ═══════════════════════════════════════════════════════════════


class HotkeyRebindDialog(tk.Toplevel):
    """弹窗让用户按下新按键来绑定热键

    使用 Tkinter 自身的 KeyPress 事件捕获，避免 keyboard 库阻塞导致的修饰键卡键
    """

    # Tkinter keysym → keyboard 库键名映射
    _KEY_MAP: dict[str, str] = {
        "comma": ",",
        "period": ".",
        "slash": "/",
        "backslash": "\\",
        "minus": "-",
        "equal": "=",
        "bracketleft": "[",
        "bracketright": "]",
        "semicolon": ";",
        "apostrophe": "'",
        "grave": "`",
        "space": "space",
        "return": "enter",
        "escape": "esc",
        "prior": "page up",
        "next": "page down",
        "insert": "insert",
        "delete": "delete",
        "home": "home",
        "end": "end",
        "up": "up",
        "down": "down",
        "left": "left",
        "right": "right",
    }

    def __init__(self, parent, current_key: str, on_confirm: Callable) -> None:
        super().__init__(parent)
        self.title("修改热键")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self._on_confirm = on_confirm
        self._new_key: str | None = None

        f = ttk.Frame(self, padding=16)
        f.pack()

        ttk.Label(f, text=f"当前热键: {key_display(current_key)}").pack(pady=(0, 8))
        self._label = ttk.Label(f, text="请按下新的热键...", font=("", 10, "bold"))
        self._label.pack(pady=4)

        btn_frame = ttk.Frame(f)
        btn_frame.pack(pady=(12, 0))
        self._ok_btn = ttk.Button(
            btn_frame, text="确定", state="disabled", command=self._confirm
        )
        self._ok_btn.pack(side="left", padx=4)
        ttk.Button(btn_frame, text="取消", command=self.destroy).pack(
            side="left", padx=4
        )

        self.protocol("WM_DELETE_WINDOW", self.destroy)

        # 居中于父窗口
        self.update_idletasks()
        w, h = self.winfo_width(), self.winfo_height()
        self.geometry(f"{w}x{h}+{parent.winfo_x() + 60}+{parent.winfo_y() + 60}")

        # 用 Tkinter 自身事件捕获按键，避免 keyboard 库阻塞
        self.bind("<KeyPress>", self._on_key_press)
        self.bind("<Alt-Key>", self._on_key_press)  # Windows 兜底
        self.focus_set()

    def _on_key_press(self, event: tk.Event) -> None:
        keysym = event.keysym.lower()

        # 忽略纯修饰键
        if keysym in (
            "control_l",
            "control_r",
            "shift_l",
            "shift_r",
            "alt_l",
            "alt_r",
            "meta_l",
            "meta_r",
            "super_l",
            "super_r",
            "caps_lock",
            "num_lock",
            "scroll_lock",
            "win_l",
            "win_r",
            "windows",
        ):
            return

        # keysym 为空时尝试从 char 恢复（某些 Ctrl+字母 组合可能发生）
        if not keysym and event.char:
            code = ord(event.char)
            if code < 32:  # 控制字符 → 对应字母
                keysym = chr(code + 96)
            else:
                keysym = event.char

        if not keysym:
            return

        # 翻译为 keyboard 库键名
        key = self._KEY_MAP.get(keysym, keysym)

        # 用 keyboard.is_pressed() 检测物理修饰键状态（比 event.state 更可靠）
        mods: list[str] = []
        if keyboard.is_pressed("ctrl"):
            mods.append("ctrl")
        if keyboard.is_pressed("shift"):
            mods.append("shift")
        if keyboard.is_pressed("alt"):
            mods.append("alt")

        hotkey = "+".join(mods + [key]) if mods else key
        self._new_key = hotkey
        self._label.config(text=f"新热键: {key_display(hotkey)}")
        self._ok_btn.config(state="normal")

    def _confirm(self) -> None:
        if self._new_key:
            self._on_confirm(self._new_key)
        self.destroy()


# ═══════════════════════════════════════════════════════════════
# 存档对话框（热键触发）
# ═══════════════════════════════════════════════════════════════


class SaveDialog(tk.Toplevel):
    """快速存档对话框：模糊搜索 + 选择已有或输入新名称
    独立顶层窗口，与主窗口无父子关系"""

    def __init__(
        self,
        saves: list[SaveInfo],
        on_save: Callable,
        on_close: Callable | None = None,
        on_delete: Callable | None = None,
        on_rename: Callable | None = None,
    ):
        super().__init__()
        self.title("快速存档")
        self.resizable(False, False)
        self.grab_set()

        self._saves = saves
        self._on_save = on_save
        self._on_close = on_close
        self._on_delete = on_delete
        self._on_rename = on_rename

        self._build_ui()
        self._refresh_list()
        self._search_var.trace_add("write", lambda *_: self._refresh_list())

        # 居中于屏幕
        self.update_idletasks()
        w, h = self.winfo_width(), self.winfo_height()
        x = (self.winfo_screenwidth() - w) // 2
        y = (self.winfo_screenheight() - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")

        self.protocol("WM_DELETE_WINDOW", self.destroy)

        # 绑定回车和 Escape
        self.bind("<Return>", lambda e: self._confirm())
        self.bind("<Escape>", lambda e: self.destroy())

        # 获取焦点（延迟到窗口完全就绪，避免干扰居中）
        self.after_idle(self.bring_to_front)

    def bring_to_front(self) -> None:
        """对话框置顶并将焦点放到搜索输入框"""
        bring_to_front(self)
        self._search_entry.focus_set()

    def _build_ui(self) -> None:
        f = ttk.Frame(self, padding=12)
        f.pack(fill="both", expand=True)

        # 搜索输入
        ttk.Label(f, text="搜索 / 输入存档名:").pack(anchor="w")
        self._search_var = tk.StringVar()
        self._search_entry = SafeFilenameEntry(
            f,
            textvariable=self._search_var,
            width=30,
        )
        self._search_entry.pack(fill="x", pady=(2, 6))

        # 已有存档列表
        list_frame = ttk.Frame(f)
        list_frame.pack(fill="both", expand=True)
        self._listbox = tk.Listbox(
            list_frame, height=8, width=36, exportselection=False
        )
        scrollbar = ttk.Scrollbar(
            list_frame, orient="vertical", command=self._listbox.yview
        )
        self._listbox.config(yscrollcommand=scrollbar.set)
        self._listbox.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self._listbox.bind("<<ListboxSelect>>", self._on_select)
        self._listbox.bind("<Double-Button-1>", lambda e: self._confirm())
        self._listbox.bind("<Button-3>", self._on_listbox_right_click)

        ttk.Label(f, text="选择已有 = 覆盖,  输入新名 = 新建").pack(pady=(4, 2))

        # 按钮
        btn_frame = ttk.Frame(f)
        btn_frame.pack(pady=(6, 0))
        self._ok_btn = ttk.Button(btn_frame, text="确定", command=self._confirm)
        self._ok_btn.pack(side="left", padx=4)
        ttk.Button(btn_frame, text="取消", command=self.destroy).pack(
            side="left", padx=4
        )

    def _refresh_list(self) -> None:
        keyword = self._search_var.get()
        self._listbox.delete(0, "end")
        for s in self._saves:
            name = s["name"]
            if fuzzy_match(keyword, name):
                self._listbox.insert("end", name)

    def _on_select(self, event: tk.Event) -> None:
        sel = self._listbox.curselection()
        if sel:
            name = self._listbox.get(sel[0])
            self._search_var.set(name)

    def destroy(self) -> None:
        """关闭窗口时回调 on_close，确保主窗口清理状态"""
        if self._on_close:
            cb = self._on_close
            self._on_close = None  # 防止重复调用
            cb()
        super().destroy()

    def _confirm(self) -> None:
        text = self._search_var.get().strip()
        if not text:
            messagebox.showwarning("提示", "请输入存档名称", parent=self)
            return
        err = validate_filename(text)
        if err:
            messagebox.showwarning("提示", err, parent=self)
            return
        exact = any(s["name"] == text for s in self._saves)
        if exact:
            if not messagebox.askyesno(
                "确认覆盖", f"存档「{text}」已存在，确定覆盖？", parent=self
            ):
                return
        self._on_save(text)
        self.destroy()

    # ── 右键菜单 ──────────────────────────────────────

    def _on_listbox_right_click(self, event: tk.Event) -> None:
        if self._on_delete is None and self._on_rename is None:
            return
        idx = self._listbox.nearest(event.y)
        if idx < 0:
            return
        self._listbox.selection_clear(0, "end")
        self._listbox.selection_set(idx)

        menu = tk.Menu(self, tearoff=0)
        if self._on_rename is not None:
            menu.add_command(label="重命名", command=self._menu_rename)
        if self._on_delete is not None:
            menu.add_command(label="删除", command=self._menu_delete)
        menu.post(event.x_root, event.y_root)

    def _menu_rename(self) -> None:
        sel = self._listbox.curselection()
        if not sel:
            return
        old_name = self._listbox.get(sel[0])

        def do_rename(new_name: str) -> None:
            assert self._on_rename is not None
            self._on_rename(old_name, new_name)
            for s in self._saves:
                if s["name"] == old_name:
                    s["name"] = new_name
                    break
            self._refresh_list()

        RenameDialog(self, old_name, do_rename)

    def _menu_delete(self) -> None:
        sel = self._listbox.curselection()
        if not sel:
            return
        name = self._listbox.get(sel[0])
        if not messagebox.askyesno(
            "确认删除", f"确定删除存档「{name}」？此操作不可恢复", parent=self
        ):
            return
        assert self._on_delete is not None
        self._on_delete(name)
        self._saves = [s for s in self._saves if s["name"] != name]
        self._refresh_list()


class LoadDialog(tk.Toplevel):
    """快速读档对话框：模糊搜索 + 从已有存档中选择
    独立顶层窗口，与主窗口无父子关系"""

    def __init__(
        self,
        saves: list[SaveInfo],
        on_load: Callable,
        on_close: Callable | None = None,
        on_delete: Callable | None = None,
        on_rename: Callable | None = None,
    ):
        super().__init__()
        self.title("快速读档")
        self.resizable(False, False)
        self.grab_set()

        self._saves = saves
        self._on_load = on_load
        self._on_close = on_close
        self._on_delete = on_delete
        self._on_rename = on_rename

        self._build_ui()
        self._refresh_list()
        # 预填第一个存档名作为提示，全选以便直接回车读档或输入搜索
        if self._saves:
            self._search_var.set(self._saves[0]["name"])
            self._search_entry.selection_range(0, "end")
        self._search_var.trace_add("write", lambda *_: self._refresh_list())

        # 居中于屏幕
        self.update_idletasks()
        w, h = self.winfo_width(), self.winfo_height()
        x = (self.winfo_screenwidth() - w) // 2
        y = (self.winfo_screenheight() - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")

        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.bind("<Return>", lambda e: self._confirm())
        self.bind("<Escape>", lambda e: self.destroy())

        # 获取焦点（延迟到窗口完全就绪，避免干扰居中）
        self.after_idle(self.bring_to_front)

    def bring_to_front(self) -> None:
        """对话框置顶并将焦点放到搜索输入框"""
        bring_to_front(self)
        self._search_entry.focus_set()

    def _build_ui(self) -> None:
        f = ttk.Frame(self, padding=12)
        f.pack(fill="both", expand=True)

        ttk.Label(f, text="搜索存档:").pack(anchor="w")
        self._search_var = tk.StringVar()
        self._search_entry = ttk.Entry(f, textvariable=self._search_var, width=30)
        self._search_entry.pack(fill="x", pady=(2, 6))

        list_frame = ttk.Frame(f)
        list_frame.pack(fill="both", expand=True)
        self._listbox = tk.Listbox(
            list_frame, height=8, width=36, exportselection=False
        )
        scrollbar = ttk.Scrollbar(
            list_frame, orient="vertical", command=self._listbox.yview
        )
        self._listbox.config(yscrollcommand=scrollbar.set)
        self._listbox.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self._listbox.bind("<Double-Button-1>", lambda e: self._confirm())
        self._listbox.bind("<Button-3>", self._on_listbox_right_click)

        btn_frame = ttk.Frame(f)
        btn_frame.pack(pady=(6, 0))
        self._ok_btn = ttk.Button(btn_frame, text="确定", command=self._confirm)
        self._ok_btn.pack(side="left", padx=4)
        ttk.Button(btn_frame, text="取消", command=self.destroy).pack(
            side="left", padx=4
        )

    def _refresh_list(self) -> None:
        keyword = self._search_var.get()
        self._listbox.delete(0, "end")
        for s in self._saves:
            name = s["name"]
            if fuzzy_match(keyword, name):
                self._listbox.insert("end", name)

    # ── 右键菜单 ──────────────────────────────────────

    def _on_listbox_right_click(self, event: tk.Event) -> None:
        if self._on_delete is None and self._on_rename is None:
            return
        idx = self._listbox.nearest(event.y)
        if idx < 0:
            return
        self._listbox.selection_clear(0, "end")
        self._listbox.selection_set(idx)

        menu = tk.Menu(self, tearoff=0)
        if self._on_rename is not None:
            menu.add_command(label="重命名", command=self._menu_rename)
        if self._on_delete is not None:
            menu.add_command(label="删除", command=self._menu_delete)
        menu.post(event.x_root, event.y_root)

    def _menu_rename(self) -> None:
        sel = self._listbox.curselection()
        if not sel:
            return
        old_name = self._listbox.get(sel[0])

        def do_rename(new_name: str) -> None:
            assert self._on_rename is not None
            self._on_rename(old_name, new_name)
            for s in self._saves:
                if s["name"] == old_name:
                    s["name"] = new_name
                    break
            self._refresh_list()

        RenameDialog(self, old_name, do_rename)

    def _menu_delete(self) -> None:
        sel = self._listbox.curselection()
        if not sel:
            return
        name = self._listbox.get(sel[0])
        if not messagebox.askyesno(
            "确认删除", f"确定删除存档「{name}」？此操作不可恢复", parent=self
        ):
            return
        assert self._on_delete is not None
        self._on_delete(name)
        self._saves = [s for s in self._saves if s["name"] != name]
        self._refresh_list()

    def destroy(self) -> None:
        """关闭窗口时回调 on_close，确保主窗口清理状态"""
        if self._on_close:
            cb = self._on_close
            self._on_close = None  # 防止重复调用
            cb()
        super().destroy()

    def _confirm(self) -> None:
        sel = self._listbox.curselection()
        if sel:
            name = self._listbox.get(sel[0])
        else:
            text = self._search_var.get().strip()
            if text and any(s["name"] == text for s in self._saves):
                name = text
            else:
                messagebox.showwarning("提示", "请从列表中选择一个存档", parent=self)
                return
        self._on_load(name)
        self.destroy()


# ═══════════════════════════════════════════════════════════════
# 重命名对话框
# ═══════════════════════════════════════════════════════════════


class RenameDialog(tk.Toplevel):
    """重命名对话框（存档 / 账号 / 分类共用）"""

    def __init__(
        self,
        parent,
        old_name: str,
        on_rename: Callable,
        title: str = "重命名存档",
    ) -> None:
        super().__init__(parent)
        self.title(title)
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self._on_rename = on_rename

        f = ttk.Frame(self, padding=12)
        f.pack()

        ttk.Label(f, text="新名称:").pack(anchor="w")
        self._var = tk.StringVar(value=old_name)
        entry = SafeFilenameEntry(
            f,
            textvariable=self._var,
            width=24,
        )
        entry.pack(fill="x", pady=(2, 6))
        entry.focus_set()
        entry.selection_range(0, "end")

        btn_frame = ttk.Frame(f)
        btn_frame.pack(pady=(4, 0))
        ttk.Button(btn_frame, text="确定", command=self._confirm).pack(
            side="left", padx=4
        )
        ttk.Button(btn_frame, text="取消", command=self.destroy).pack(
            side="left", padx=4
        )

        self.bind("<Return>", lambda e: self._confirm())
        self.bind("<Escape>", lambda e: self.destroy())

        self.update_idletasks()
        w, h = self.winfo_width(), self.winfo_height()
        self.geometry(f"{w}x{h}+{parent.winfo_x() + 60}+{parent.winfo_y() + 60}")

    def _confirm(self) -> None:
        name = self._var.get().strip()
        if not name:
            messagebox.showwarning("提示", "名称不能为空", parent=self)
            return
        err = validate_filename(name)
        if err:
            messagebox.showwarning("提示", err, parent=self)
            return
        self._on_rename(name)
        self.destroy()


# ═══════════════════════════════════════════════════════════════
# 手动添加账号对话框
# ═══════════════════════════════════════════════════════════════


class ManualAccountDialog(tk.Toplevel):
    """手动添加账号的对话框：输入 Steam ID 和存档文件路径"""

    def __init__(
        self,
        parent,
        existing_ids: set[str],
        on_confirm: Callable[[str, str], None],
    ) -> None:
        super().__init__(parent)
        self.title("手动添加账号")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self._existing_ids = existing_ids
        self._on_confirm = on_confirm

        f = ttk.Frame(self, padding=12)
        f.pack()

        # ── Steam ID ────────────────────────────────────
        ttk.Label(f, text="名称:").pack(anchor="w")
        self._id_var = tk.StringVar()
        self._id_entry = SafeFilenameEntry(
            f,
            textvariable=self._id_var,
            width=36,
        )
        self._id_entry.pack(fill="x", pady=(2, 8))

        # ── 存档路径 ─────────────────────────────────────
        ttk.Label(f, text="存档文件路径:").pack(anchor="w")
        path_frame = ttk.Frame(f)
        path_frame.pack(fill="x", pady=(2, 8))
        self._path_var = tk.StringVar()
        ttk.Entry(path_frame, textvariable=self._path_var, width=28).pack(
            side="left", fill="x", expand=True
        )
        ttk.Button(path_frame, text="浏览...", command=self._browse).pack(
            side="left", padx=(4, 0)
        )

        # ── 按钮 ────────────────────────────────────────
        btn_frame = ttk.Frame(f)
        btn_frame.pack(pady=(4, 0))
        ttk.Button(btn_frame, text="确定", command=self._confirm).pack(
            side="left", padx=4
        )
        ttk.Button(btn_frame, text="取消", command=self.destroy).pack(
            side="left", padx=4
        )

        self.bind("<Return>", lambda e: self._confirm())
        self.bind("<Escape>", lambda e: self.destroy())
        self.protocol("WM_DELETE_WINDOW", self.destroy)

        # 居中于父窗口
        self.update_idletasks()
        w, h = self.winfo_width(), self.winfo_height()
        self.geometry(f"{w}x{h}+{parent.winfo_x() + 60}+{parent.winfo_y() + 60}")

        # 自动聚焦到 ID 输入框
        self._id_entry.focus_set()

    def _browse(self) -> None:
        """打开文件浏览器选择存档文件"""
        path = filedialog.askopenfilename(
            title="选择存档文件",
            filetypes=[
                ("存档文件", "*.sl2"),
                ("所有文件", "*.*"),
            ],
        )
        if path:
            self._path_var.set(path)

    def _confirm(self) -> None:
        steam_id = self._id_var.get().strip()
        save_path = self._path_var.get().strip()

        if not steam_id:
            messagebox.showwarning("提示", "请输入 Steam ID", parent=self)
            return
        err = validate_filename(steam_id)
        if err:
            messagebox.showwarning("提示", f"Steam ID 不合法：{err}", parent=self)
            return
        if not save_path:
            messagebox.showwarning("提示", "请选择或输入存档文件路径", parent=self)
            return
        if steam_id in self._existing_ids:
            messagebox.showwarning(
                "提示",
                f"Steam ID「{steam_id}」已存在",
                parent=self,
            )
            return

        self._on_confirm(steam_id, save_path)
        self.destroy()


# ═══════════════════════════════════════════════════════════════
# 新建分类（Profile）对话框
# ═══════════════════════════════════════════════════════════════


class CreateProfileDialog(tk.Toplevel):
    """新建分类对话框：输入 profile 名称，校验文件名合法性"""

    def __init__(
        self,
        parent,
        existing_names: set[str],
        on_confirm: Callable[[str], None],
    ) -> None:
        super().__init__(parent)
        self.title("新建分类")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self._existing_names = existing_names
        self._on_confirm = on_confirm

        f = ttk.Frame(self, padding=12)
        f.pack()

        ttk.Label(f, text="分类名称:").pack(anchor="w")
        self._var = tk.StringVar()
        entry = SafeFilenameEntry(
            f,
            textvariable=self._var,
            width=24,
        )
        entry.pack(fill="x", pady=(2, 6))
        entry.focus_set()

        btn_frame = ttk.Frame(f)
        btn_frame.pack(pady=(4, 0))
        ttk.Button(btn_frame, text="确定", command=self._confirm).pack(
            side="left", padx=4
        )
        ttk.Button(btn_frame, text="取消", command=self.destroy).pack(
            side="left", padx=4
        )

        self.bind("<Return>", lambda e: self._confirm())
        self.bind("<Escape>", lambda e: self.destroy())
        self.protocol("WM_DELETE_WINDOW", self.destroy)

        self.update_idletasks()
        w, h = self.winfo_width(), self.winfo_height()
        self.geometry(f"{w}x{h}+{parent.winfo_x() + 60}+{parent.winfo_y() + 60}")

    def _confirm(self) -> None:
        name = self._var.get().strip()
        if not name:
            messagebox.showwarning("提示", "分类名称不能为空", parent=self)
            return
        err = validate_filename(name)
        if err:
            messagebox.showwarning("提示", err, parent=self)
            return
        if name in self._existing_names:
            messagebox.showwarning("提示", f"分类「{name}」已存在", parent=self)
            return
        self._on_confirm(name)
        self.destroy()
