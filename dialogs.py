"""对话框：热键修改、存档、读档、重命名"""

import tkinter as tk
from collections.abc import Callable
from tkinter import messagebox, ttk

from save_manager import SaveInfo

import keyboard

from utils import fuzzy_match, key_display, sanitize_filename, validate_filename

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
        self.attributes("-topmost", True)

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
        self, saves: list[SaveInfo], on_save: Callable, on_close: Callable | None = None
    ):
        super().__init__()
        self.title("快速存档")
        self.resizable(False, False)
        self.grab_set()
        self.attributes("-topmost", True)

        self._saves = saves
        self._on_save = on_save
        self._on_close = on_close

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

        # 获取焦点
        self.lift()
        self.focus_force()
        self._search_entry.focus_set()

    def _build_ui(self) -> None:
        f = ttk.Frame(self, padding=12)
        f.pack(fill="both", expand=True)

        # 搜索输入
        ttk.Label(f, text="搜索 / 输入存档名:").pack(anchor="w")
        self._search_var = tk.StringVar()
        vcmd = (self.register(self._validate_filename_input), "%P")
        self._search_entry = ttk.Entry(
            f,
            textvariable=self._search_var,
            width=30,
            validate="key",
            validatecommand=vcmd,
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

    def _validate_filename_input(self, proposed: str) -> bool:
        """Entry validatecommand：输入时自动剥离非法字符"""
        cleaned = sanitize_filename(proposed)
        if cleaned != proposed:
            self._search_var.set(cleaned)
            return False
        return True


class LoadDialog(tk.Toplevel):
    """快速读档对话框：模糊搜索 + 从已有存档中选择
    独立顶层窗口，与主窗口无父子关系"""

    def __init__(
        self, saves: list[SaveInfo], on_load: Callable, on_close: Callable | None = None
    ):
        super().__init__()
        self.title("快速读档")
        self.resizable(False, False)
        self.grab_set()
        self.attributes("-topmost", True)

        self._saves = saves
        self._on_load = on_load
        self._on_close = on_close

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

        # 获取焦点
        self.lift()
        self.focus_force()
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
    """重命名存档对话框"""

    def __init__(self, parent, old_name: str, on_rename: Callable) -> None:
        super().__init__(parent)
        self.title("重命名存档")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.attributes("-topmost", True)

        self._on_rename = on_rename

        f = ttk.Frame(self, padding=12)
        f.pack()

        ttk.Label(f, text="新名称:").pack(anchor="w")
        self._var = tk.StringVar(value=old_name)
        vcmd = (self.register(self._validate_filename_input), "%P")
        entry = ttk.Entry(
            f,
            textvariable=self._var,
            width=24,
            validate="key",
            validatecommand=vcmd,
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

    def _validate_filename_input(self, proposed: str) -> bool:
        """Entry validatecommand：输入时自动剥离非法字符"""
        cleaned = sanitize_filename(proposed)
        if cleaned != proposed:
            self._var.set(cleaned)
            return False
        return True
