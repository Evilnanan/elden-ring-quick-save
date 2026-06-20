"""Elden Ring 快速 SL 工具 — Tkinter 主界面"""

import queue
import tkinter as tk
from datetime import datetime
from tkinter import messagebox, ttk

from config import load_config, load_manual_accounts, save_config, save_manual_accounts
from dialogs import (
    HotkeyRebindDialog,
    LoadDialog,
    ManualAccountDialog,
    RenameDialog,
    SaveDialog,
)
from hotkey import HotkeyAction, HotkeyManager
from save_manager import (
    SaveInfo,
    create_save,
    delete_save,
    list_saves,
    load_save,
    rename_save,
)
from steam_helper import AccountInfo, get_all_accounts
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
        self.minsize(480, 340)

        # ── 状态 ────────────────────────────────────────
        self._accounts: dict[str, AccountInfo] = {}  # steam_id → AccountInfo
        self._display_to_id: dict[str, str] = {}  # 下拉框显示 → steam_id
        self._current_steam_id: str | None = None
        self._saves: list[SaveInfo] = []
        cfg = load_config()
        self._hotkey = HotkeyManager(
            save_hotkey=cfg["save_hotkey"],
            load_hotkey=cfg["load_hotkey"],
        )
        self._save_dialog: SaveDialog | None = None
        self._load_dialog: LoadDialog | None = None

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
            width=34,
        )
        self._steam_combo.pack(side="left", padx=8, pady=4)
        self._steam_combo.bind("<<ComboboxSelected>>", self._on_account_changed)
        ttk.Button(top_frame, text="刷新", command=self._load_accounts).pack(
            side="left"
        )
        self._remove_manual_btn = ttk.Button(
            top_frame,
            text="✕",
            width=3,
            state="disabled",
            command=self._remove_manual_account,
        )
        self._remove_manual_btn.pack(side="left", padx=(2, 0))

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
        self._tree.column("name", width=200, minwidth=100)
        self._tree.column("atime", width=120, minwidth=75)
        self._tree.column("mtime", width=120, minwidth=75)

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
        self._accounts = get_all_accounts()
        # 构建下拉框显示字符串
        self._display_to_id = {}
        displays: list[str] = []
        for sid, info in self._accounts.items():
            if info["is_manual"]:
                label = f"{sid}"
            else:
                label = f"{sid} ({info['name']})"
            self._display_to_id[label] = sid
            displays.append(label)

        # 末尾追加"添加"入口
        displays.append(self._ADD_ENTRY)
        self._steam_combo["values"] = displays
        if self._accounts:
            self._steam_var.set(displays[0])
            self._on_account_changed()
        else:
            self._steam_var.set("")
            self._current_steam_id = None
            self._refresh_save_list()

    _ADD_ENTRY = "—— 添加 ——"

    def _on_account_changed(self, event=None) -> None:
        display = self._steam_var.get()
        if display == self._ADD_ENTRY:
            # 还原为上次选中的账号
            prev = self._current_steam_id or ""
            prev_display = next(
                (d for d, sid in self._display_to_id.items() if sid == prev), ""
            )
            self._steam_var.set(prev_display)
            self._add_manual_account()
            return

        sid = self._display_to_id.get(display)
        self._current_steam_id = sid
        info = self._accounts.get(sid) if sid else None
        if info and info["is_manual"]:
            self._remove_manual_btn.config(state="normal")
        else:
            self._remove_manual_btn.config(state="disabled")
        self._refresh_save_list()

    # ── 手动添加 / 删除账号 ──────────────────────────

    def _add_manual_account(self) -> None:
        """弹出对话框添加账号"""
        existing_ids = set(self._accounts.keys())

        def on_confirm(steam_id: str, save_path: str) -> None:
            # 持久化
            manual = load_manual_accounts()
            manual[steam_id] = save_path
            save_manual_accounts(manual)
            # 刷新
            self._load_accounts()

        with self._hotkey.suppressed():
            dlg = ManualAccountDialog(self, existing_ids, on_confirm)
            self.wait_window(dlg)

    def _remove_manual_account(self) -> None:
        """删除当前选中的手动添加的账号"""
        sid = self._current_steam_id
        if not sid:
            return
        info = self._accounts.get(sid)
        if info is None or not info["is_manual"]:
            return

        with self._hotkey.suppressed():
            confirmed = messagebox.askyesno(
                "确认删除",
                f"确定删除账号「{sid}」？\n（saves/ 下的存档文件不会被删除）",
            )
        if not confirmed:
            return

        manual = load_manual_accounts()
        manual.pop(sid, None)
        save_manual_accounts(manual)
        self._load_accounts()

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
        if not self._current_steam_id:
            with self._hotkey.suppressed():
                messagebox.showwarning("提示", "请先选择一个 Steam 账号", parent=self)
            return

        steam_id = self._current_steam_id
        account = self._accounts.get(steam_id)
        if account is None:
            return

        # ── 如果对应对话框已打开，则将其提到前台 ──────────
        if action == HotkeyAction.SAVE:
            if self._save_dialog is not None and self._save_dialog.winfo_exists():
                self._save_dialog.bring_to_front()
                return
        else:  # LOAD
            if self._load_dialog is not None and self._load_dialog.winfo_exists():
                self._load_dialog.bring_to_front()
                return

        # ── 关闭另一个对话框（如果打开着） ──────────────────
        if action == HotkeyAction.SAVE:
            if self._load_dialog is not None:
                if self._load_dialog.winfo_exists():
                    self._load_dialog.destroy()
                self._load_dialog = None
        else:
            if self._save_dialog is not None:
                if self._save_dialog.winfo_exists():
                    self._save_dialog.destroy()
                self._save_dialog = None

        save_path = account["save_path"]

        def on_dialog_close() -> None:
            if action == HotkeyAction.SAVE:
                self._save_dialog = None
            else:
                self._load_dialog = None

        if action == HotkeyAction.SAVE:

            def do_save(name: str) -> None:
                try:
                    create_save(steam_id, name, save_path)
                    self._refresh_save_list()
                except Exception as e:
                    assert self._save_dialog is not None  # 回调时对话框一定存在
                    messagebox.showerror("存档失败", str(e), parent=self._save_dialog)

            self._save_dialog = SaveDialog(
                self._saves, do_save, on_close=on_dialog_close
            )

        elif action == HotkeyAction.LOAD:
            if not self._saves:
                with self._hotkey.suppressed():
                    messagebox.showwarning(
                        "提示", "还没有任何存档，请先存档", parent=self
                    )
                return

            def do_load(name: str) -> None:
                try:
                    load_save(steam_id, name, save_path)
                    self._refresh_save_list()
                except Exception as e:
                    assert self._load_dialog is not None  # 回调时对话框一定存在
                    messagebox.showerror("读档失败", str(e), parent=self._load_dialog)

            self._load_dialog = LoadDialog(
                self._saves, do_load, on_close=on_dialog_close
            )

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
