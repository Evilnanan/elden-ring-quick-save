"""Elden Ring 快速 SL 工具 — Tkinter 主界面"""

import os
import queue
import sys
import tkinter as tk

if sys.platform == "win32":
    import winsound
else:
    winsound = None  # type: ignore[assignment]
from datetime import datetime
from tkinter import messagebox, ttk

from config import (
    DEFAULT_PROFILE,
    load_config,
    migrate_manual_accounts_from_config,
    save_config,
)
from dialogs import (
    CreateProfileDialog,
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
    delete_profile,
    delete_save,
    is_readonly,
    list_profiles,
    list_saves,
    load_save,
    rename_profile,
    rename_save,
    set_readonly,
)
from steam_helper import (
    AccountInfo,
    get_all_accounts,
    remove_manual_account_marker,
    rename_manual_account,
    set_manual_account,
)
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
        self.minsize(480, 380)

        # ── 状态 ────────────────────────────────────────
        self._accounts: dict[str, AccountInfo] = {}  # steam_id → AccountInfo
        self._display_to_id: dict[str, str] = {}  # 下拉框显示 → steam_id
        self._current_steam_id: str | None = None
        self._current_profile: str = DEFAULT_PROFILE
        self._saves: list[SaveInfo] = []
        cfg = load_config()
        self._hotkey = HotkeyManager(
            save_hotkey=cfg["save_hotkey"],
            load_hotkey=cfg["load_hotkey"],
            toggle_readonly_hotkey=cfg["toggle_readonly_hotkey"],
        )

        # ── 一次性迁移旧版 manual_accounts ────────────────
        migrate_manual_accounts_from_config()

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

        ttk.Label(top_frame, text="账号:").pack(side="left")
        self._steam_var = tk.StringVar()
        self._steam_combo = ttk.Combobox(
            top_frame,
            textvariable=self._steam_var,
            state="readonly",
            width=41,
        )
        self._steam_combo.pack(side="left", padx=8, pady=4)
        self._steam_combo.bind("<<ComboboxSelected>>", self._on_account_changed)
        ttk.Button(top_frame, text="↻", width=3, command=self._load_accounts).pack(
            side="left", padx=(2, 0)
        )
        self._remove_manual_btn = ttk.Button(
            top_frame,
            text="✕",
            width=3,
            state="disabled",
            command=self._remove_manual_account,
        )
        self._remove_manual_btn.pack(side="left", padx=(2, 0))
        self._rename_manual_btn = ttk.Button(
            top_frame,
            text="≡",
            width=3,
            state="disabled",
            command=self._rename_manual_account,
        )
        self._rename_manual_btn.pack(side="left", padx=(2, 0))

        # ── 第二行: Profile 分类选择 ────────────────────
        profile_frame = ttk.Frame(self, padding=(8, 4, 8, 0))
        profile_frame.pack(fill="x")

        ttk.Label(profile_frame, text="分类:").pack(side="left")
        self._profile_var = tk.StringVar()
        self._profile_combo = ttk.Combobox(
            profile_frame,
            textvariable=self._profile_var,
            state="readonly",
            width=34,
        )
        self._profile_combo.pack(side="left", padx=8, pady=4)
        self._profile_combo.bind("<<ComboboxSelected>>", self._on_profile_changed)
        self._remove_profile_btn = ttk.Button(
            profile_frame,
            text="✕",
            width=3,
            state="disabled",
            command=self._remove_profile,
        )
        self._remove_profile_btn.pack(side="left", padx=(2, 0))
        self._rename_profile_btn = ttk.Button(
            profile_frame,
            text="≡",
            width=3,
            state="disabled",
            command=self._rename_profile,
        )
        self._rename_profile_btn.pack(side="left", padx=(2, 0))

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

        # 右键菜单
        self._tree.bind("<Button-3>", self._on_tree_right_click)

        # ── 热键栏 ──────────────────────────────────────
        hotkey_frame = ttk.Frame(self, padding=(8, 4, 8, 8))
        hotkey_frame.pack(fill="x")

        ttk.Label(hotkey_frame, text="热键:").pack(side="left")

        self._hotkey_enabled_var = tk.BooleanVar(value=self._hotkey.enabled)
        self._hotkey_toggle = ttk.Checkbutton(
            hotkey_frame,
            text="启用",
            variable=self._hotkey_enabled_var,
            command=self._on_hotkey_toggle,
        )
        self._hotkey_toggle.pack(side="left", padx=(4, 4))

        self._save_key_var = tk.StringVar(value=self._hotkey.save_hotkey)
        self._load_key_var = tk.StringVar(value=self._hotkey.load_hotkey)

        self._save_text_label = ttk.Label(
            hotkey_frame, text="存档", cursor="hand2"
        )
        self._save_text_label.pack(side="left", padx=(8, 2))
        self._save_text_label.bind(
            "<Button-1>", lambda e: self._hotkey.event_queue.put(HotkeyAction.SAVE)
        )

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

        self._load_text_label = ttk.Label(
            hotkey_frame, text="读档", cursor="hand2"
        )
        self._load_text_label.pack(side="left", padx=(8, 2))
        self._load_text_label.bind(
            "<Button-1>", lambda e: self._hotkey.event_queue.put(HotkeyAction.LOAD)
        )

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

        self._toggle_readonly_key_var = tk.StringVar(
            value=self._hotkey.toggle_readonly_hotkey
        )
        self._readonly_state_var = tk.StringVar(value="")

        self._readonly_text_label = ttk.Label(
            hotkey_frame, text="只读", cursor="hand2"
        )
        self._readonly_text_label.pack(side="left", padx=(8, 2))
        self._readonly_text_label.bind(
            "<Button-1>", lambda e: self._hotkey.event_queue.put(
                HotkeyAction.TOGGLE_READONLY
            )
        )
        self._toggle_readonly_key_label = ttk.Label(
            hotkey_frame,
            textvariable=self._toggle_readonly_key_var,
            relief="sunken",
            width=6,
            anchor="center",
            background="white",
            cursor="hand2",
        )
        self._toggle_readonly_key_label.pack(side="left")
        self._toggle_readonly_key_label.bind(
            "<Button-1>", lambda e: self._rebind_hotkey("toggle_readonly")
        )

        self._readonly_state_label = ttk.Label(
            hotkey_frame,
            textvariable=self._readonly_state_var,
            width=6,
            anchor="center",
            cursor="hand2",
        )
        self._readonly_state_label.pack(side="left", padx=(4, 0))
        self._readonly_state_label.bind("<Button-1>", self._on_readonly_click)

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
        displays.append(self._ADD_ACCOUNT_ENTRY)
        self._steam_combo["values"] = displays
        if self._accounts:
            self._steam_var.set(displays[0])
            self._on_account_changed()
        else:
            self._steam_var.set("")
            self._current_steam_id = None
            self._load_profiles()
            self._refresh_save_list()

    _ADD_ACCOUNT_ENTRY = "—— 添加 ——"
    _ADD_PROFILE_ENTRY = "—— 新建 ——"

    def _on_account_changed(self, event=None) -> None:
        display = self._steam_var.get()
        if display == self._ADD_ACCOUNT_ENTRY:
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
            self._rename_manual_btn.config(state="normal")
        else:
            self._remove_manual_btn.config(state="disabled")
            self._rename_manual_btn.config(state="disabled")
        self._load_profiles()
        self._refresh_readonly_state()

    # ── Profile 分类管理 ──────────────────────────────

    def _load_profiles(self) -> None:
        """刷新 profile 下拉框，按最近活动时间排序，默认选中最活跃的"""
        sid = self._current_steam_id
        if not sid:
            self._profile_combo["values"] = []
            self._profile_var.set("")
            self._current_profile = DEFAULT_PROFILE
            self._remove_profile_btn.config(state="disabled")
            self._rename_profile_btn.config(state="disabled")
            self._refresh_save_list()
            return

        # 从磁盘扫描已有 profile，已按最近活动时间降序排列
        dir_profiles = list_profiles(sid)

        # "默认"始终在列表最前（若磁盘上尚不存在则手动补上）
        if DEFAULT_PROFILE in dir_profiles:
            others = [p for p in dir_profiles if p != DEFAULT_PROFILE]
        else:
            others = dir_profiles
        values = [DEFAULT_PROFILE] + others + [self._ADD_PROFILE_ENTRY]

        # 当前选中：最活跃的那个
        current = dir_profiles[0] if dir_profiles else DEFAULT_PROFILE

        self._profile_combo["values"] = values
        self._profile_var.set(current)
        self._current_profile = current
        self._update_profile_btn_state()
        self._refresh_save_list()

    def _update_profile_btn_state(self) -> None:
        """「默认」profile 不允许删除和重命名"""
        if self._current_profile == DEFAULT_PROFILE:
            self._remove_profile_btn.config(state="disabled")
            self._rename_profile_btn.config(state="disabled")
        else:
            self._remove_profile_btn.config(state="normal")
            self._rename_profile_btn.config(state="normal")

    def _on_profile_changed(self, event=None) -> None:
        display = self._profile_var.get()
        if display == self._ADD_PROFILE_ENTRY:
            # 还原为上次选中的 profile
            prev = self._current_profile
            self._profile_var.set(prev)
            self._create_profile()
            return

        if not self._current_steam_id:
            return

        self._current_profile = display or DEFAULT_PROFILE
        self._update_profile_btn_state()
        self._refresh_save_list()

    def _remove_profile(self) -> None:
        """删除当前选中的 profile 及其中所有存档"""
        sid = self._current_steam_id
        profile = self._current_profile
        if not sid or profile == DEFAULT_PROFILE:
            return

        with self._hotkey.suppressed():
            confirmed = messagebox.askyesno(
                "确认删除",
                f"确定删除分类「{profile}」及其中的所有存档？\n此操作不可恢复",
            )
        if not confirmed:
            return

        delete_profile(sid, profile)
        self._load_profiles()

    def _create_profile(self) -> None:
        """弹出对话框新建分类，直接在磁盘上创建目录"""
        sid = self._current_steam_id
        if not sid:
            return

        # 收集已有 profile 名称（用于重名校验）
        existing: set[str] = {DEFAULT_PROFILE}
        existing.update(list_profiles(sid))

        def on_confirm(name: str) -> None:
            # 在磁盘上创建空目录
            save_dir = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "saves", sid, name
            )
            os.makedirs(save_dir, exist_ok=True)
            # 刷新列表并选中新 profile
            self._load_profiles()
            self._profile_var.set(name)
            self._current_profile = name
            self._refresh_save_list()

        with self._hotkey.suppressed():
            dlg = CreateProfileDialog(self, existing, on_confirm)
            self.wait_window(dlg)

    # ── 手动添加 / 删除账号 ──────────────────────────

    def _add_manual_account(self) -> None:
        """弹出对话框添加账号"""
        existing_ids = set(self._accounts.keys())

        def on_confirm(steam_id: str, save_path: str) -> None:
            set_manual_account(steam_id, save_path)
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

        remove_manual_account_marker(sid)
        # 如果该 steam_id 目录下没有其他 profile 目录了，清理空目录
        self._load_accounts()

    # ── 存档列表刷新 ──────────────────────────────────

    def _refresh_save_list(self) -> None:
        for item in self._tree.get_children():
            self._tree.delete(item)

        if not self._current_steam_id:
            self._saves = []
            return

        self._saves = list_saves(self._current_steam_id, self._current_profile)
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
        profile = self._current_profile
        old_name = names[0]

        def do_rename(new_name: str) -> None:
            try:
                rename_save(steam_id, profile, old_name, new_name)
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
        profile = self._current_profile
        with self._hotkey.suppressed():
            if len(names) == 1:
                msg = f"确定删除存档「{names[0]}」？此操作不可恢复"
            else:
                lines = "\n".join(f"  • {n}" for n in names)
                msg = f"确定删除以下 {len(names)} 个存档？此操作不可恢复\n\n{lines}"
            confirmed = messagebox.askyesno("确认删除", msg)
        if confirmed:
            for name in names:
                delete_save(steam_id, profile, name)
            self._refresh_save_list()

    def _on_tree_right_click(self, event: tk.Event) -> None:
        """右键点击 Treeview：选中点击项并弹出菜单"""
        item = self._tree.identify_row(event.y)
        if not item:
            return
        # 若点击的项不在当前选中集合中，则单选它
        if item not in self._tree.selection():
            self._tree.selection_set(item)
        self._show_tree_menu(event)

    def _show_tree_menu(self, event: tk.Event) -> None:
        names = self._get_selected_save_names()
        if not names:
            return
        menu = tk.Menu(self, tearoff=0)
        if len(names) == 1:
            menu.add_command(label="重命名", command=self._rename_selected)
        menu.add_command(label="删除", command=self._delete_selected)
        menu.post(event.x_root, event.y_root)

    # ── 手动账号重命名 ────────────────────────────────

    def _rename_manual_account(self) -> None:
        """重命名手动添加的账号"""
        sid = self._current_steam_id
        if not sid:
            return
        info = self._accounts.get(sid)
        if info is None or not info["is_manual"]:
            return

        def do_rename(new_id: str) -> None:
            try:
                rename_manual_account(sid, new_id)
                self._load_accounts()
            except FileExistsError:
                messagebox.showerror("错误", f"账号「{new_id}」已存在，请换一个名称")
            except Exception as e:
                messagebox.showerror("错误", f"重命名失败: {e}")

        with self._hotkey.suppressed():
            dlg = RenameDialog(self, sid, do_rename, title="重命名账号")
            self.wait_window(dlg)

    # ── 分类重命名 ─────────────────────────────────────

    def _rename_profile(self) -> None:
        """重命名当前选中的分类"""
        sid = self._current_steam_id
        profile = self._current_profile
        if not sid or profile == DEFAULT_PROFILE:
            return

        def do_rename(new_name: str) -> None:
            try:
                rename_profile(sid, profile, new_name)
                self._load_profiles()
            except FileExistsError:
                messagebox.showerror(
                    "错误", f"分类「{new_name}」已存在，请换一个名称"
                )
            except Exception as e:
                messagebox.showerror("错误", f"重命名失败: {e}")

        with self._hotkey.suppressed():
            dlg = RenameDialog(self, profile, do_rename, title="重命名分类")
            self.wait_window(dlg)

    # ── 热键修改 ──────────────────────────────────────

    def _on_hotkey_toggle(self) -> None:
        """全局热键开关"""
        self._hotkey.set_enabled(self._hotkey_enabled_var.get())

    def _rebind_hotkey(self, which: Literal["save", "load", "toggle_readonly"]) -> None:
        """修改热键"""
        if which == "save":
            current = self._hotkey.save_hotkey
        elif which == "load":
            current = self._hotkey.load_hotkey
        else:
            current = self._hotkey.toggle_readonly_hotkey

        def on_key(key: str) -> None:
            if which == "save":
                self._hotkey.set_save_hotkey(key)
                self._save_key_var.set(key)
                save_config({"save_hotkey": key})
            elif which == "load":
                self._hotkey.set_load_hotkey(key)
                self._load_key_var.set(key)
                save_config({"load_hotkey": key})
            else:
                self._hotkey.set_toggle_readonly_hotkey(key)
                self._toggle_readonly_key_var.set(key)
                save_config({"toggle_readonly_hotkey": key})

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
        profile = self._current_profile
        account = self._accounts.get(steam_id)
        if account is None:
            return

        save_path = account["save_path"]

        # 右键菜单回调（Save / Load 对话框共用）
        def do_delete(name: str) -> None:
            delete_save(steam_id, profile, name)
            self._refresh_save_list()

        def do_rename(old_name: str, new_name: str) -> None:
            try:
                rename_save(steam_id, profile, old_name, new_name)
                self._refresh_save_list()
            except FileExistsError:
                messagebox.showerror("错误", f"存档「{new_name}」已存在")
            except Exception as e:
                messagebox.showerror("错误", f"重命名失败: {e}")

        if action == HotkeyAction.SAVE:
            _save_dlg_ref: list[SaveDialog] = []

            def do_save(name: str) -> None:
                try:
                    create_save(steam_id, profile, name, save_path)
                    self._refresh_save_list()
                except Exception as e:
                    messagebox.showerror("存档失败", str(e), parent=_save_dlg_ref[0])

            with self._hotkey.suppressed():
                save_dlg = SaveDialog(
                    self._saves,
                    do_save,
                    on_delete=do_delete,
                    on_rename=do_rename,
                )
                _save_dlg_ref.append(save_dlg)
                self.wait_window(save_dlg)

        elif action == HotkeyAction.LOAD:
            if not self._saves:
                with self._hotkey.suppressed():
                    messagebox.showwarning(
                        "提示", "还没有任何存档，请先存档", parent=self
                    )
                return

            _load_dlg_ref: list[LoadDialog] = []

            def do_load(name: str) -> None:
                try:
                    load_save(steam_id, profile, name, save_path)
                    self._refresh_save_list()
                except Exception as e:
                    messagebox.showerror("读档失败", str(e), parent=_load_dlg_ref[0])

            with self._hotkey.suppressed():
                load_dlg = LoadDialog(
                    self._saves,
                    do_load,
                    on_delete=do_delete,
                    on_rename=do_rename,
                )
                _load_dlg_ref.append(load_dlg)
                self.wait_window(load_dlg)

        elif action == HotkeyAction.TOGGLE_READONLY:
            self._toggle_readonly(save_path)

    # ── 只读状态指示器 ────────────────────────────────

    def _on_readonly_click(self, event: tk.Event) -> None:
        """点击只读指示器切换状态"""
        account = self._accounts.get(self._current_steam_id or "")
        if account is None:
            return
        self._toggle_readonly(account["save_path"])

    def _toggle_readonly(self, save_path: str) -> None:
        """切换游戏存档只读状态（热键 & 点击共用）"""
        if not os.path.isfile(save_path):
            return

        try:
            currently_ro = is_readonly(save_path)
        except OSError:
            return

        try:
            set_readonly(save_path, not currently_ro)
        except OSError as e:
            messagebox.showerror("错误", f"切换只读状态失败: {e}")
            return

        self._refresh_readonly_state(save_path)
        self._beep_readonly(not currently_ro)

    def _refresh_readonly_state(self, save_path: str | None = None) -> None:
        """更新只读状态标签"""
        if save_path is None:
            account = self._accounts.get(self._current_steam_id or "")
            if account is None:
                self._readonly_state_var.set("")
                return
            save_path = account["save_path"]

        if not os.path.isfile(save_path):
            self._readonly_state_var.set("")
            return

        try:
            ro = is_readonly(save_path)
        except OSError:
            self._readonly_state_var.set("")
            return

        self._readonly_state_var.set("🔒只读" if ro else "🔓可写")

    def _beep_readonly(self, locked: bool) -> None:
        """只读状态切换声音提示：高音 = 锁定，低音 = 解锁"""
        if winsound is None:
            return
        try:
            if locked:
                winsound.Beep(1000, 200)  # 高音 — 锁上
            else:
                winsound.Beep(500, 200)  # 低音 — 解锁
        except Exception:
            pass

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
