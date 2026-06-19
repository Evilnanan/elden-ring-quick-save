"""Elden Ring 快速 SL 工具 — Tkinter 主界面

功能：
- Steam 账号自动发现与选择
- 命名存档管理（列表、重命名、删除）
- 全局热键存档/读档（默认 , 存档、. 读档）
- 模糊搜索过滤
"""

import queue
import tkinter as tk
from datetime import datetime
from tkinter import messagebox, ttk

from config import load_config, save_config
from dialogs import HotkeyRebindDialog, LoadDialog, RenameDialog, SaveDialog
from hotkey import HotkeyAction, HotkeyManager
from save_manager import (
    SaveInfo,
    create_save,
    delete_save,
    list_saves,
    load_save,
    rename_save,
)
from steam_helper import get_all_steam_accounts, get_elden_ring_save_path
from utils import fuzzy_match
from typing import Literal

# ═══════════════════════════════════════════════════════════════
# 主应用窗口
# ═══════════════════════════════════════════════════════════════


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("老头环快速SL工具")
        self.resizable(True, True)
        self.minsize(420, 340)

        # ── 状态 ────────────────────────────────────────
        self._accounts: dict[str, str] = {}  # steam_id → account_name
        self._current_steam_id: str | None = None
        self._saves: list[SaveInfo] = []
        cfg = load_config()
        self._hotkey = HotkeyManager(
            save_hotkey=cfg["save_hotkey"],
            load_hotkey=cfg["load_hotkey"],
        )
        self._dialog_open = False  # 防止热键重入

        # ── 构建界面 ────────────────────────────────────
        self._build_ui()
        self._load_accounts()

        # ── 热键 ────────────────────────────────────────
        self._hotkey.start()
        self._poll_hotkey_queue()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── UI 构建 ────────────────────────────────────────

    def _build_ui(self) -> None:

        # ── 第一行: Steam 账号选择 ──────────────────────
        top_frame = ttk.Frame(self, padding=(8, 8, 8, 0))
        top_frame.pack(fill="x")

        ttk.Label(top_frame, text="Steam ID:").pack(side="left")
        self._steam_var = tk.StringVar()
        self._steam_combo = ttk.Combobox(
            top_frame,
            textvariable=self._steam_var,
            state="readonly",
            width=22,
        )
        self._steam_combo.pack(side="left", padx=8, pady=4)
        self._steam_combo.bind("<<ComboboxSelected>>", self._on_account_changed)
        ttk.Button(top_frame, text="刷新", command=self._load_accounts).pack(
            side="left"
        )

        # 用户名
        self._name_label = ttk.Label(top_frame, text="", foreground="gray")
        self._name_label.pack(side="left", padx=12)

        # ── 搜索 ────────────────────────────────────────
        search_frame = ttk.Frame(self, padding=(8, 6, 8, 0))
        search_frame.pack(fill="x")
        ttk.Label(search_frame, text="搜索:").pack(side="left")
        self._search_var = tk.StringVar()
        self._search_entry = ttk.Entry(
            search_frame, textvariable=self._search_var, width=24
        )
        self._search_entry.pack(side="left", padx=8, pady=4)
        self._search_var.trace_add("write", lambda *_: self._refresh_save_list())

        # ── 存档列表 ────────────────────────────────────
        list_frame = ttk.Frame(self, padding=(8, 4, 8, 4))
        list_frame.pack(fill="both", expand=True)

        columns = ("name", "atime", "mtime")
        self._tree = ttk.Treeview(
            list_frame,
            columns=columns,
            show="headings",
            height=6,
            selectmode="extended",
        )
        self._tree.heading("name", text="存档名称")
        self._tree.heading("atime", text="读取时间")
        self._tree.heading("mtime", text="保存时间")
        self._tree.column("name", width=180, minwidth=100)
        self._tree.column("atime", width=90, minwidth=75)
        self._tree.column("mtime", width=90, minwidth=75)

        scrollbar = ttk.Scrollbar(
            list_frame, orient="vertical", command=self._tree.yview
        )
        self._tree.config(yscrollcommand=scrollbar.set)

        self._tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # ── 操作按钮 ────────────────────────────────────
        btn_frame = ttk.Frame(self, padding=(8, 0, 8, 4))
        btn_frame.pack(fill="x")
        ttk.Button(btn_frame, text="重命名", command=self._rename_selected).pack(
            side="left",
            padx=(0, 4),
        )
        ttk.Button(btn_frame, text="删除选中", command=self._delete_selected).pack(
            side="left"
        )

        # ── 热键栏 ──────────────────────────────────────
        hotkey_frame = ttk.Frame(self, padding=(8, 4, 8, 8))
        hotkey_frame.pack(fill="x")

        ttk.Label(hotkey_frame, text="热键:").pack(side="left")

        self._save_key_var = tk.StringVar(value=self._hotkey.save_hotkey)
        self._load_key_var = tk.StringVar(value=self._hotkey.load_hotkey)

        ttk.Label(hotkey_frame, text="存档").pack(side="left", padx=(8, 2))
        self._save_key_label = ttk.Label(
            hotkey_frame,
            textvariable=self._save_key_var,
            relief="sunken",
            width=6,
            anchor="center",
            background="white",
            cursor="hand2",
        )
        self._save_key_label.pack(side="left")
        self._save_key_label.bind("<Button-1>", lambda e: self._rebind_hotkey("save"))

        ttk.Label(hotkey_frame, text="读档").pack(side="left", padx=(8, 2))
        self._load_key_label = ttk.Label(
            hotkey_frame,
            textvariable=self._load_key_var,
            relief="sunken",
            width=6,
            anchor="center",
            background="white",
            cursor="hand2",
        )
        self._load_key_label.pack(side="left")
        self._load_key_label.bind("<Button-1>", lambda e: self._rebind_hotkey("load"))

    # ── Steam 账号加载 ────────────────────────────────

    def _load_accounts(self) -> None:
        self._accounts = get_all_steam_accounts()
        ids = list(self._accounts.keys())
        self._steam_combo["values"] = ids
        if ids:
            self._steam_var.set(ids[0])
            self._on_account_changed()
        else:
            self._steam_var.set("")
            self._name_label.config(text="未检测到 Steam 账号")
            self._current_steam_id = None
            self._refresh_save_list()

    def _on_account_changed(self, event=None) -> None:
        sid = self._steam_var.get()
        self._current_steam_id = sid
        name = self._accounts.get(sid, "")
        self._name_label.config(text=f"用户名: {name}" if name else "")
        self._refresh_save_list()

    # ── 存档列表刷新 ──────────────────────────────────

    def _refresh_save_list(self) -> None:
        for item in self._tree.get_children():
            self._tree.delete(item)

        if not self._current_steam_id:
            self._saves = []
            return

        self._saves = list_saves(self._current_steam_id)
        keyword = self._search_var.get()

        for s in self._saves:
            if fuzzy_match(keyword, s["name"]):
                mtime_str = datetime.fromtimestamp(s["mtime"]).strftime(
                    "%Y-%m-%d %H:%M"
                )
                atime_str = datetime.fromtimestamp(s["atime"]).strftime(
                    "%Y-%m-%d %H:%M"
                )
                self._tree.insert("", "end", values=(s["name"], atime_str, mtime_str))

    # ── 重命名 & 删除 ─────────────────────────────────

    def _get_selected_save_names(self) -> list[str]:
        sel = self._tree.selection()
        if not sel:
            with self._hotkey.suppressed():
                messagebox.showwarning("提示", "请先在列表中选择存档")
            return []
        return [self._tree.item(i, "values")[0] for i in sel]

    def _rename_selected(self) -> None:
        if not self._current_steam_id:
            return
        names = self._get_selected_save_names()
        if not names:
            return
        steam_id = self._current_steam_id
        old_name = names[0]

        def do_rename(new_name: str) -> None:
            try:
                rename_save(steam_id, old_name, new_name)
                self._refresh_save_list()
            except FileExistsError:
                messagebox.showerror("错误", f"存档「{new_name}」已存在，请换一个名称")
            except Exception as e:
                messagebox.showerror("错误", f"重命名失败: {e}")

        with self._hotkey.suppressed():
            dlg = RenameDialog(self, old_name, do_rename)
            self.wait_window(dlg)

    def _delete_selected(self) -> None:
        if not self._current_steam_id:
            return
        names = self._get_selected_save_names()
        if not names:
            return
        steam_id = self._current_steam_id
        with self._hotkey.suppressed():
            if len(names) == 1:
                msg = f"确定删除存档「{names[0]}」？此操作不可恢复"
            else:
                lines = "\n".join(f"  • {n}" for n in names)
                msg = f"确定删除以下 {len(names)} 个存档？此操作不可恢复\n\n{lines}"
            confirmed = messagebox.askyesno("确认删除", msg)
        if confirmed:
            for name in names:
                delete_save(steam_id, name)
            self._refresh_save_list()

    # ── 热键修改 ──────────────────────────────────────

    def _rebind_hotkey(self, which: Literal["save", "load"]) -> None:
        """单独修改存档或读档热键"""
        is_save = which == "save"
        current = self._hotkey.save_hotkey if is_save else self._hotkey.load_hotkey

        def on_key(key: str) -> None:
            if is_save:
                self._hotkey.set_save_hotkey(key)
                self._save_key_var.set(key)
                save_config({"save_hotkey": key})
            else:
                self._hotkey.set_load_hotkey(key)
                self._load_key_var.set(key)
                save_config({"load_hotkey": key})

        with self._hotkey.suppressed():
            dlg = HotkeyRebindDialog(self, current, on_key)
            self.wait_window(dlg)

    # ── 热键队列轮询 ──────────────────────────────────

    def _poll_hotkey_queue(self) -> None:
        """定期检查热键事件队列"""
        q = self._hotkey.event_queue
        while not q.empty():
            try:
                action = q.get_nowait()
                self._handle_hotkey(action)
            except queue.Empty:
                break
        self.after(100, self._poll_hotkey_queue)

    def _handle_hotkey(self, action: HotkeyAction) -> None:
        if self._dialog_open:
            return
        if not self._current_steam_id:
            with self._hotkey.suppressed():
                messagebox.showwarning("提示", "请先选择一个 Steam 账号")
            return

        steam_id = self._current_steam_id

        self._dialog_open = True
        _suppress_guard = self._hotkey.suppressed()
        _suppress_guard.__enter__()

        save_path = get_elden_ring_save_path(steam_id)

        def on_dialog_close() -> None:
            self._dialog_open = False
            _suppress_guard.__exit__(None, None, None)

        if action == HotkeyAction.SAVE:

            def do_save(name: str) -> None:
                try:
                    create_save(steam_id, name, save_path)
                    self._refresh_save_list()
                except Exception as e:
                    messagebox.showerror("存档失败", str(e))

            SaveDialog(self._saves, do_save, on_close=on_dialog_close)

        elif action == HotkeyAction.LOAD:
            if not self._saves:
                messagebox.showwarning("提示", "还没有任何存档，请先存档")
                self._dialog_open = False
                _suppress_guard.__exit__(None, None, None)
                return

            def do_load(name: str) -> None:
                try:
                    load_save(steam_id, name, save_path)
                    self._refresh_save_list()
                except Exception as e:
                    messagebox.showerror("读档失败", str(e))

            LoadDialog(self._saves, do_load, on_close=on_dialog_close)

    # ── 关闭 ──────────────────────────────────────────

    def _on_close(self) -> None:
        self._hotkey.stop()
        self.destroy()


# ═══════════════════════════════════════════════════════════════
# 入口
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    app = App()
    app.mainloop()
