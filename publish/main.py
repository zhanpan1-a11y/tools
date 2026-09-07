#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自动化互动工具 v6.5
改进：
  - 所有时间显示统一为 HH:MM:SS 格式（如 00:01:23）
  - 任务统计合并到运行控制区域，去除独立面板
  - 保持 v6.4 的暂停时填入进度、跳转后清空等功能
依赖：pip install pyautogui pyperclip pynput
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, Toplevel
import pyautogui
import pyperclip
import threading
import time
import re
import sys
import json
import os
from datetime import datetime
from pynput import mouse, keyboard

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.05

IS_MAC = sys.platform == 'darwin'
IS_WIN = sys.platform == 'win32'
SELECT_ALL_HOTKEY = ('command', 'a') if IS_MAC else ('ctrl', 'a')
PASTE_HOTKEY = ('command', 'v') if IS_MAC else ('ctrl', 'v')

kb = keyboard.Controller()
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'auto_config.json')


class CaptureDialog:
    """坐标捕获浮动窗 - 全局双击左键确认，右键取消"""
    def __init__(self, parent, target_name, callback):
        self.parent = parent
        self.target_name = target_name
        self.callback = callback
        self.running = True
        self.last_click_time = 0
        self.last_button = None

        self.win = Toplevel(parent)
        self.win.overrideredirect(True)
        self.win.attributes('-topmost', True)
        self.win.attributes('-alpha', 0.85)
        self.win.configure(bg='#1e293b')
        self.win.geometry("280x100")

        frame = tk.Frame(self.win, bg='#1e293b', padx=10, pady=10)
        frame.pack(fill=tk.BOTH, expand=True)

        lbl_hint = tk.Label(frame, text=f"目标：{target_name} | 双击左键确认 · 右键取消",
                            font=("Microsoft YaHei", 9), fg='#94a3b8', bg='#1e293b')
        lbl_hint.pack()

        self.coord_var = tk.StringVar(value="X: ---  Y: ---")
        lbl_coord = tk.Label(frame, textvariable=self.coord_var,
                             font=("JetBrains Mono", 20, "bold"),
                             fg='#38bdf8', bg='#1e293b')
        lbl_coord.pack(pady=(2, 0))

        self.win.bind("<Escape>", lambda e: self.on_cancel())
        self._start_tracking()
        self.listener = mouse.Listener(on_click=self._on_click)
        self.listener.start()

        self.win.update_idletasks()
        self._update_position()
        print("[Capture] 浮动窗打开，全局监听已启动。双击左键确认，右键取消。")

    def _start_tracking(self):
        def track():
            while self.running and self.win.winfo_exists():
                self._update_position()
                x, y = pyautogui.position()
                self.coord_var.set(f"X: {x}  Y: {y}")
                time.sleep(0.05)
        threading.Thread(target=track, daemon=True).start()

    def _update_position(self):
        try:
            mx, my = pyautogui.position()
            offset_x = 20
            offset_y = -30
            self.win.update_idletasks()
            w = self.win.winfo_width()
            h = self.win.winfo_height()
            x = mx + offset_x
            y = my + offset_y
            screen_w = self.win.winfo_screenwidth()
            screen_h = self.win.winfo_screenheight()
            if x + w > screen_w:
                x = screen_w - w - 5
            if y < 0:
                y = 5
            if y + h > screen_h:
                y = screen_h - h - 5
            self.win.geometry(f"+{int(x)}+{int(y)}")
        except:
            pass

    def _on_click(self, x, y, button, pressed):
        if not self.running or not pressed:
            return
        now = time.time()
        if button == mouse.Button.left:
            if now - self.last_click_time < 0.5 and self.last_button == mouse.Button.left:
                self.last_click_time = 0
                self.on_confirm()
            else:
                self.last_click_time = now
                self.last_button = button
        elif button == mouse.Button.right:
            self.on_cancel()

    def on_confirm(self):
        print("[Capture] 双击左键确认")
        x, y = pyautogui.position()
        self.running = False
        self._cleanup()
        self.callback(x, y)

    def on_cancel(self):
        print("[Capture] 右键取消")
        self.running = False
        self._cleanup()

    def _cleanup(self):
        if self.listener and self.listener.running:
            self.listener.stop()
        if self.win.winfo_exists():
            self.win.destroy()


class AutoInteractionTool:
    def __init__(self, root):
        self.root = root
        self.root.title("自动化互动工具 v6.5")
        self.root.geometry("1100x780")
        self.root.minsize(1000, 750)
        self.root.configure(bg="#f0f4f8")

        self.schedule_data = []
        self.coord_groups = []
        self.is_running = False
        self.paused = False
        self.sent_count = 0
        self.start_time = None
        self.start_timestamp = None
        self.log_file = None
        self.log_filename = None
        self.selected_group_index = tk.IntVar(value=0)
        self.scheduler_thread = None
        self.progress_running = False

        # UI 变量
        self.use_enter_var = tk.BooleanVar(value=False)
        self.loop_check = tk.BooleanVar(value=True)
        self.offset_var = tk.DoubleVar(value=1.5)
        self.file_var = tk.StringVar()
        self.group_name_var = tk.StringVar()
        self.progress_value = tk.DoubleVar(value=0.0)

        self.setup_styles()
        self.setup_ui()
        self.create_log_file()
        self.add_log(f"系统就绪 (平台: {'macOS' if IS_MAC else 'Windows' if IS_WIN else 'Linux'})", "INFO")
        self.add_log("正在加载配置...", "INFO")
        self.load_config()
        self.add_log("配置加载完成", "INFO")
        if self.file_var.get().strip():
            self.add_log(f"上次文件: {self.file_var.get()}", "INFO")
            self.load_file_from_path(self.file_var.get())
        self.add_default_group_if_empty()
        self.update_group_list()
        self.update_preview()
        self.update_stats()

    def setup_styles(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TFrame", background="#f0f4f8")
        style.configure("TLabel", background="#f0f4f8", font=("Microsoft YaHei", 10))
        style.configure("TLabelframe", background="#ffffff", font=("Microsoft YaHei", 10, "bold"), relief="solid", borderwidth=1)
        style.configure("TLabelframe.Label", background="#ffffff", font=("Microsoft YaHei", 10, "bold"))
        style.configure("Treeview", font=("Microsoft YaHei", 10), rowheight=26, background="#ffffff", fieldbackground="#ffffff")
        style.configure("Treeview.Heading", font=("Microsoft YaHei", 10, "bold"), background="#e2e8f0")
        style.map("Treeview", background=[("selected", "#dbeafe")])

        style.configure("Start.TButton", background="#22c55e", foreground="white",
                        font=("Microsoft YaHei", 12, "bold"), padding=6, relief="flat")
        style.map("Start.TButton", background=[("active", "#16a34a"), ("disabled", "#94a3a8")],
                  foreground=[("disabled", "#d1d5db")])
        style.configure("Stop.TButton", background="#94a3a8", foreground="white",
                        font=("Microsoft YaHei", 12, "bold"), padding=6, relief="flat")
        style.map("Stop.TButton", background=[("active", "#64748b"), ("!disabled", "#ef4444")],
                  foreground=[("disabled", "#d1d5db")])
        style.configure("Pause.TButton", background="#f59e0b", foreground="white",
                        font=("Microsoft YaHei", 12, "bold"), padding=6, relief="flat")
        style.map("Pause.TButton", background=[("active", "#d97706")])

        # 绿色进度条样式
        style.configure("green.Horizontal.TProgressbar",
                        background='#22c55e',
                        troughcolor='#e5e7eb',
                        bordercolor='#e5e7eb',
                        lightcolor='#22c55e',
                        darkcolor='#22c55e')

    def add_default_group_if_empty(self):
        if not self.coord_groups:
            group = {"name": "默认", "input_x": 0, "input_y": 0, "send_x": 0, "send_y": 0}
            self.coord_groups.append(group)
            self.update_group_list()
            self.save_config()

    def setup_ui(self):
        main = ttk.Frame(self.root, padding=12)
        main.pack(fill=tk.BOTH, expand=True)
        main.columnconfigure(1, weight=1)
        main.rowconfigure(2, weight=1)

        header = ttk.Frame(main)
        header.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 6))
        ttk.Label(header, text="🤖 自动化互动工具 v6.5", font=("Microsoft YaHei", 20, "bold"), foreground="#1e293b").pack(side=tk.LEFT)
        ttk.Label(header, text="  暂停·跳转·进度条", font=("Microsoft YaHei", 12), foreground="#64748b").pack(side=tk.LEFT, padx=(8, 0))

        ttk.Separator(main, orient="horizontal").grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 10))

        left = ttk.Frame(main)
        left.grid(row=2, column=0, sticky="nsew", padx=(0, 12))
        left.columnconfigure(0, weight=1)

        # 文件导入
        file_frame = ttk.LabelFrame(left, text=" 步骤 1：导入时间戳文件 ", padding=8)
        file_frame.pack(fill=tk.X, pady=(0, 8))
        file_frame.columnconfigure(1, weight=1)

        ttk.Label(file_frame, text="文件路径：").grid(row=0, column=0, sticky="w", pady=4)
        ttk.Entry(file_frame, textvariable=self.file_var, state="readonly").grid(row=0, column=1, sticky="ew", padx=6)
        ttk.Button(file_frame, text="浏览...", command=self.load_file, width=8).grid(row=0, column=2)
        hint = ttk.Label(file_frame, text="格式：HH:MM:SS, 文案内容  或  [HH.MM.SS] 文案内容", foreground="#94a3b8", font=("Consolas", 9))
        hint.grid(row=1, column=0, columnspan=3, sticky="w", pady=(2, 0))

        # 坐标组管理（高度压缩为 3 行）
        coord_group_frame = ttk.LabelFrame(left, text=" 步骤 2：管理坐标组 (循环顺序按列表顺序) ", padding=8)
        coord_group_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 8))

        list_frame = ttk.Frame(coord_group_frame)
        list_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 5))

        self.group_tree = ttk.Treeview(list_frame, columns=("name", "input", "send"), show="headings", height=3)
        self.group_tree.heading("name", text="组名")
        self.group_tree.heading("input", text="输入框坐标")
        self.group_tree.heading("send", text="发送按钮坐标")
        self.group_tree.column("name", width=100, anchor="center")
        self.group_tree.column("input", width=150, anchor="center")
        self.group_tree.column("send", width=150, anchor="center")
        self.group_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.group_tree.bind("<<TreeviewSelect>>", self.on_group_select)

        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.group_tree.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.group_tree.configure(yscrollcommand=scrollbar.set)

        group_btn_frame = ttk.Frame(coord_group_frame)
        group_btn_frame.pack(fill=tk.X, pady=(5, 0))
        ttk.Button(group_btn_frame, text="➕ 添加组", command=self.add_group).pack(side=tk.LEFT, padx=2)
        ttk.Button(group_btn_frame, text="➖ 删除组", command=self.remove_group).pack(side=tk.LEFT, padx=2)
        ttk.Button(group_btn_frame, text="⬆ 上移", command=self.move_group_up).pack(side=tk.LEFT, padx=2)
        ttk.Button(group_btn_frame, text="⬇ 下移", command=self.move_group_down).pack(side=tk.LEFT, padx=2)

        detail_frame = ttk.LabelFrame(coord_group_frame, text=" 当前组坐标详情 ", padding=5)
        detail_frame.pack(fill=tk.X, pady=(5, 0))

        name_row = ttk.Frame(detail_frame)
        name_row.pack(fill=tk.X, pady=2)
        ttk.Label(name_row, text="组名：").pack(side=tk.LEFT)
        self.group_name_entry = ttk.Entry(name_row, textvariable=self.group_name_var, width=15)
        self.group_name_entry.pack(side=tk.LEFT, padx=5)
        ttk.Button(name_row, text="更新组名", command=self.update_group_name).pack(side=tk.LEFT, padx=5)

        coord_row = ttk.Frame(detail_frame)
        coord_row.pack(fill=tk.X, pady=2)
        ttk.Label(coord_row, text="输入框 X:").pack(side=tk.LEFT)
        self.input_x = ttk.Entry(coord_row, width=8, justify="center", font=("Consolas", 11))
        self.input_x.pack(side=tk.LEFT, padx=(4, 2))
        ttk.Label(coord_row, text="Y:").pack(side=tk.LEFT)
        self.input_y = ttk.Entry(coord_row, width=8, justify="center", font=("Consolas", 11))
        self.input_y.pack(side=tk.LEFT, padx=(2, 8))
        ttk.Button(coord_row, text="捕获输入框", command=lambda: self.capture_coord("input"), width=12).pack(side=tk.LEFT)

        send_row = ttk.Frame(detail_frame)
        send_row.pack(fill=tk.X, pady=2)
        ttk.Label(send_row, text="发送按钮 X:").pack(side=tk.LEFT)
        self.send_x = ttk.Entry(send_row, width=8, justify="center", font=("Consolas", 11))
        self.send_x.pack(side=tk.LEFT, padx=(4, 2))
        ttk.Label(send_row, text="Y:").pack(side=tk.LEFT)
        self.send_y = ttk.Entry(send_row, width=8, justify="center", font=("Consolas", 11))
        self.send_y.pack(side=tk.LEFT, padx=(2, 8))
        ttk.Button(send_row, text="捕获发送按钮", command=lambda: self.capture_coord("send"), width=12).pack(side=tk.LEFT)

        global_frame = ttk.Frame(detail_frame)
        global_frame.pack(fill=tk.X, pady=(5, 0))
        self.enter_check = ttk.Checkbutton(global_frame, text="使用回车键发送（不点击按钮）",
                                            variable=self.use_enter_var, command=self.toggle_send_mode)
        self.enter_check.pack(side=tk.LEFT)
        self.loop_checkbtn = ttk.Checkbutton(global_frame, text="循环使用坐标组", variable=self.loop_check,
                                             command=self.save_config)
        self.loop_checkbtn.pack(side=tk.LEFT, padx=(15, 0))

        ttk.Label(global_frame, text="提前偏移(秒):", font=("Microsoft YaHei", 9)).pack(side=tk.LEFT, padx=(15, 5))
        self.offset_entry = ttk.Entry(global_frame, textvariable=self.offset_var, width=6)
        self.offset_entry.pack(side=tk.LEFT)
        self.offset_entry.bind("<KeyRelease>", lambda e: self.save_config())
        ttk.Label(global_frame, text="(建议1.5~3.0)", foreground="#94a3b8", font=("Microsoft YaHei", 8)).pack(side=tk.LEFT, padx=2)

        tip = ttk.Label(coord_group_frame, text="💡 点击「捕获」后，全局双击左键确认，右键取消",
                        foreground="#94a3b8", font=("Microsoft YaHei", 9))
        tip.pack(fill=tk.X, pady=(3, 0))

        # ====== 运行控制（合并了任务统计） ======
        ctrl_frame = ttk.LabelFrame(left, text=" 步骤 3：运行控制与统计 ", padding=8)
        ctrl_frame.pack(fill=tk.X, pady=(0, 0))

        # 第一行：按钮
        btn_row = ttk.Frame(ctrl_frame)
        btn_row.pack(fill=tk.X)
        btn_row.columnconfigure(0, weight=1)
        btn_row.columnconfigure(1, weight=1)
        btn_row.columnconfigure(2, weight=1)

        self.start_btn = ttk.Button(btn_row, text="▶  开始运行",
                                    style="Start.TButton", command=self.start_automation, cursor="hand2")
        self.start_btn.grid(row=0, column=0, sticky="ew", padx=(0, 4))

        self.pause_btn = ttk.Button(btn_row, text="⏸  暂停",
                                    style="Pause.TButton", command=self.toggle_pause,
                                    state="disabled", cursor="hand2")
        self.pause_btn.grid(row=0, column=1, sticky="ew", padx=(4, 0))

        self.stop_btn = ttk.Button(btn_row, text="⏹  停止",
                                   style="Stop.TButton", command=self.stop_automation,
                                   cursor="hand2", state="disabled")
        self.stop_btn.grid(row=0, column=2, sticky="ew", padx=(4, 0))

        # 第二行：跳转
        jump_frame = ttk.Frame(ctrl_frame)
        jump_frame.pack(fill=tk.X, pady=(6, 4))
        ttk.Label(jump_frame, text="跳转到 (秒 或 HH:MM:SS):").pack(side=tk.LEFT)
        self.jump_var = tk.StringVar()
        self.jump_entry = ttk.Entry(jump_frame, textvariable=self.jump_var, width=14)
        self.jump_entry.pack(side=tk.LEFT, padx=5)
        self.jump_btn = ttk.Button(jump_frame, text="⏩ 跳转", command=self.jump_to_time,
                                   state="disabled", cursor="hand2")
        self.jump_btn.pack(side=tk.LEFT, padx=2)

        # 第三行：进度条及信息
        progress_frame = ttk.Frame(ctrl_frame)
        progress_frame.pack(fill=tk.X, pady=(4, 4))

        self.progress_time_label = ttk.Label(progress_frame, text="00:00:00 / 00:00:00", font=("Consolas", 10))
        self.progress_time_label.pack(anchor=tk.W)

        self.progress_bar = ttk.Progressbar(progress_frame, variable=self.progress_value,
                                            maximum=100, style="green.Horizontal.TProgressbar")
        self.progress_bar.pack(fill=tk.X, pady=(2, 2))

        self.progress_count_label = ttk.Label(progress_frame, text="已发送: 0 | 剩余: 0", font=("Consolas", 10))
        self.progress_count_label.pack(anchor=tk.W)

        # ---- 任务统计（直接嵌入，无独立标签框） ----
        stat_frame = ttk.Frame(ctrl_frame)
        stat_frame.pack(fill=tk.X, pady=(2, 0))
        self.stat_total = ttk.Label(stat_frame, text="总任务: 0", font=("Microsoft YaHei", 10, "bold"), foreground="#334155")
        self.stat_total.pack(side=tk.LEFT, padx=(0, 16))
        self.stat_sent = ttk.Label(stat_frame, text="已发送: 0", font=("Microsoft YaHei", 10, "bold"), foreground="#22c55e")
        self.stat_sent.pack(side=tk.LEFT, padx=8)
        self.stat_pending = ttk.Label(stat_frame, text="待发送: 0", font=("Microsoft YaHei", 10, "bold"), foreground="#f59e0b")
        self.stat_pending.pack(side=tk.LEFT, padx=8)

        # 右侧面板
        right = ttk.Frame(main)
        right.grid(row=2, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(0, weight=3)
        right.rowconfigure(1, weight=4)

        preview_frame = ttk.LabelFrame(right, text=" 任务预览 ", padding=5)
        preview_frame.grid(row=0, column=0, sticky="nsew", pady=(0, 8))
        preview_frame.columnconfigure(0, weight=1)
        preview_frame.rowconfigure(0, weight=1)

        cols = ("时间", "文案内容", "状态")
        self.tree = ttk.Treeview(preview_frame, columns=cols, show="headings", height=8)
        self.tree.heading("时间", text="时间")
        self.tree.heading("文案内容", text="文案内容")
        self.tree.heading("状态", text="状态")
        self.tree.column("时间", width=80, anchor="center")
        self.tree.column("文案内容", width=360)
        self.tree.column("状态", width=70, anchor="center")
        self.tree.grid(row=0, column=0, sticky="nsew")

        vsb = ttk.Scrollbar(preview_frame, orient="vertical", command=self.tree.yview)
        vsb.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=vsb.set)

        log_frame = ttk.LabelFrame(right, text=" 运行日志 ", padding=5)
        log_frame.grid(row=1, column=0, sticky="nsew")
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)

        self.log_text = tk.Text(log_frame, wrap=tk.WORD, state="disabled", height=14,
                                font=("JetBrains Mono", 10), bg="#0f172a", fg="#e2e8f0",
                                insertbackground="white", relief=tk.FLAT, padx=8, pady=6)
        self.log_text.grid(row=0, column=0, sticky="nsew")

        log_vsb = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        log_vsb.grid(row=0, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=log_vsb.set)

        self.log_text.tag_config("time", foreground="#38bdf8")
        self.log_text.tag_config("reltime", foreground="#fbbf24")
        self.log_text.tag_config("info", foreground="#94a3b8")
        self.log_text.tag_config("success", foreground="#22c55e")
        self.log_text.tag_config("error", foreground="#ef4444")
        self.log_text.tag_config("warn", foreground="#f59e0b")

        log_btn_row = ttk.Frame(right)
        log_btn_row.grid(row=2, column=0, sticky="e", pady=(6, 0))
        ttk.Button(log_btn_row, text="🗑 清空日志", command=self.clear_logs, width=12).pack(side=tk.LEFT, padx=4)
        ttk.Button(log_btn_row, text="💾 导出日志", command=self.export_logs, width=12).pack(side=tk.LEFT, padx=4)

    # ---------- 配置保存与加载 ----------
    def save_config(self):
        config = {
            "coord_groups": self.coord_groups,
            "use_enter": self.use_enter_var.get(),
            "loop_enabled": self.loop_check.get(),
            "offset": self.offset_var.get(),
            "last_file": self.file_var.get()
        }
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"保存配置失败: {e}")

    def load_config(self):
        if not os.path.exists(CONFIG_FILE):
            return
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
            if "coord_groups" in config and config["coord_groups"]:
                self.coord_groups = config["coord_groups"]
            else:
                self.coord_groups = [{"name": "默认", "input_x": 0, "input_y": 0, "send_x": 0, "send_y": 0}]
            self.update_group_list()
            self.use_enter_var.set(config.get("use_enter", False))
            self.loop_check.set(config.get("loop_enabled", True))
            self.offset_var.set(config.get("offset", 1.5))
            self.file_var.set(config.get("last_file", ""))
            if self.coord_groups:
                self.group_tree.selection_set(self.group_tree.get_children()[0])
                self.on_group_select(None)
        except Exception as e:
            print(f"加载配置失败: {e}")
            if not self.coord_groups:
                self.coord_groups = [{"name": "默认", "input_x": 0, "input_y": 0, "send_x": 0, "send_y": 0}]
                self.update_group_list()

    def load_file_from_path(self, path):
        if not os.path.exists(path):
            self.add_log(f"上次文件不存在: {path}", "WARN")
            return
        self.file_var.set(path)
        self.schedule_data.clear()
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw_lines = f.readlines()
            for raw in raw_lines:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                m = re.match(r"^(\d{1,2}:\d{2}:\d{2})[,，\s]+(.+)$", line)
                if not m:
                    m = re.match(r"^(\d{1,2}:\d{2}:\d{2})(.+)$", line)
                if not m:
                    m = re.match(r"^\[(\d{1,2})\.(\d{2})\.(\d{2})\]\s*(.+)$", line)
                    if m:
                        h = int(m.group(1))
                        min_ = int(m.group(2))
                        sec = int(m.group(3))
                        text = m.group(4).strip()
                        t_str = f"{h:02d}:{min_:02d}:{sec:02d}"
                        t_ms = (h * 3600 + min_ * 60 + sec) * 1000
                        self.schedule_data.append({"time_str": t_str, "time_ms": t_ms, "text": text, "status": "等待"})
                        continue
                if m:
                    t_str = m.group(1)
                    text = m.group(2).strip()
                    t_ms = self.parse_time(t_str)
                    self.schedule_data.append({"time_str": t_str, "time_ms": t_ms, "text": text, "status": "等待"})
                else:
                    self.add_log(f"跳过无效行: {line}", "WARN")
            self.schedule_data.sort(key=lambda x: x["time_ms"])
            self.update_preview()
            self.update_stats()
            self.add_log(f"自动导入 {len(self.schedule_data)} 条任务", "SUCCESS")
            self.save_config()
        except Exception as e:
            self.add_log(f"自动导入失败: {e}", "ERROR")

    # ---------- 坐标组管理 ----------
    def add_group(self):
        count = len(self.coord_groups) + 1
        new_group = {"name": f"组{count}", "input_x": 0, "input_y": 0, "send_x": 0, "send_y": 0}
        self.coord_groups.append(new_group)
        self.update_group_list()
        self.group_tree.selection_set(self.group_tree.get_children()[-1])
        self.on_group_select(None)
        self.save_config()

    def remove_group(self):
        selection = self.group_tree.selection()
        if not selection:
            messagebox.showwarning("提示", "请先选中要删除的组")
            return
        if len(self.coord_groups) <= 1:
            messagebox.showwarning("提示", "至少保留一组坐标")
            return
        index = self.group_tree.index(selection[0])
        del self.coord_groups[index]
        self.update_group_list()
        new_index = min(index, len(self.coord_groups)-1)
        if new_index >= 0:
            self.group_tree.selection_set(self.group_tree.get_children()[new_index])
            self.on_group_select(None)
        self.save_config()

    def move_group_up(self):
        selection = self.group_tree.selection()
        if not selection:
            return
        index = self.group_tree.index(selection[0])
        if index == 0:
            return
        self.coord_groups[index], self.coord_groups[index-1] = self.coord_groups[index-1], self.coord_groups[index]
        self.update_group_list()
        self.group_tree.selection_set(self.group_tree.get_children()[index-1])
        self.on_group_select(None)
        self.save_config()

    def move_group_down(self):
        selection = self.group_tree.selection()
        if not selection:
            return
        index = self.group_tree.index(selection[0])
        if index == len(self.coord_groups)-1:
            return
        self.coord_groups[index], self.coord_groups[index+1] = self.coord_groups[index+1], self.coord_groups[index]
        self.update_group_list()
        self.group_tree.selection_set(self.group_tree.get_children()[index+1])
        self.on_group_select(None)
        self.save_config()

    def update_group_list(self):
        for item in self.group_tree.get_children():
            self.group_tree.delete(item)
        for i, group in enumerate(self.coord_groups):
            input_coord = f"({group['input_x']}, {group['input_y']})"
            send_coord = f"({group['send_x']}, {group['send_y']})"
            self.group_tree.insert("", tk.END, values=(group["name"], input_coord, send_coord))

    def on_group_select(self, event):
        selection = self.group_tree.selection()
        if not selection:
            return
        index = self.group_tree.index(selection[0])
        self.selected_group_index.set(index)
        group = self.coord_groups[index]
        self.group_name_var.set(group["name"])
        self.input_x.delete(0, tk.END)
        self.input_x.insert(0, str(group["input_x"]))
        self.input_y.delete(0, tk.END)
        self.input_y.insert(0, str(group["input_y"]))
        self.send_x.delete(0, tk.END)
        self.send_x.insert(0, str(group["send_x"]))
        self.send_y.delete(0, tk.END)
        self.send_y.insert(0, str(group["send_y"]))

    def update_group_name(self):
        selection = self.group_tree.selection()
        if not selection:
            return
        index = self.group_tree.index(selection[0])
        new_name = self.group_name_var.get().strip()
        if not new_name:
            messagebox.showwarning("提示", "组名不能为空")
            return
        self.coord_groups[index]["name"] = new_name
        self.update_group_list()
        self.group_tree.selection_set(self.group_tree.get_children()[index])
        self.on_group_select(None)
        self.save_config()

    def capture_coord(self, target):
        selection = self.group_tree.selection()
        if not selection:
            messagebox.showwarning("提示", "请先选中一个坐标组")
            return
        index = self.group_tree.index(selection[0])
        name = "输入框" if target == "input" else "发送按钮"
        self.add_log(f"准备捕获「{name}」坐标，请移动鼠标并双击左键确认", "INFO")

        def on_captured(x, y):
            group = self.coord_groups[index]
            if target == "input":
                group["input_x"] = x
                group["input_y"] = y
            else:
                group["send_x"] = x
                group["send_y"] = y
            self.input_x.delete(0, tk.END)
            self.input_x.insert(0, str(group["input_x"]))
            self.input_y.delete(0, tk.END)
            self.input_y.insert(0, str(group["input_y"]))
            self.send_x.delete(0, tk.END)
            self.send_x.insert(0, str(group["send_x"]))
            self.send_y.delete(0, tk.END)
            self.send_y.insert(0, str(group["send_y"]))
            self.update_group_list()
            self.group_tree.selection_set(self.group_tree.get_children()[index])
            self.add_log(f"「{name}」坐标已确认: ({x}, {y})", "SUCCESS")
            self.save_config()

        CaptureDialog(self.root, name, on_captured)

    def toggle_send_mode(self):
        if self.use_enter_var.get():
            self.add_log("发送模式已切换为：回车键发送", "INFO")
        else:
            self.add_log("发送模式已切换为：点击发送按钮", "INFO")
        self.save_config()

    # ---------- 文件导入 ----------
    def load_file(self):
        path = filedialog.askopenfilename(
            title="选择时间戳文件",
            filetypes=[("文本文件", "*.txt *.csv"), ("所有文件", "*.*")]
        )
        if not path:
            return
        self.file_var.set(path)
        self.schedule_data.clear()
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw_lines = f.readlines()
            for raw in raw_lines:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                m = re.match(r"^(\d{1,2}:\d{2}:\d{2})[,，\s]+(.+)$", line)
                if not m:
                    m = re.match(r"^(\d{1,2}:\d{2}:\d{2})(.+)$", line)
                if not m:
                    m = re.match(r"^\[(\d{1,2})\.(\d{2})\.(\d{2})\]\s*(.+)$", line)
                    if m:
                        h = int(m.group(1))
                        min_ = int(m.group(2))
                        sec = int(m.group(3))
                        text = m.group(4).strip()
                        t_str = f"{h:02d}:{min_:02d}:{sec:02d}"
                        t_ms = (h * 3600 + min_ * 60 + sec) * 1000
                        self.schedule_data.append({"time_str": t_str, "time_ms": t_ms, "text": text, "status": "等待"})
                        continue
                if m:
                    t_str = m.group(1)
                    text = m.group(2).strip()
                    t_ms = self.parse_time(t_str)
                    self.schedule_data.append({"time_str": t_str, "time_ms": t_ms, "text": text, "status": "等待"})
                else:
                    self.add_log(f"跳过无效行: {line}", "WARN")
            self.schedule_data.sort(key=lambda x: x["time_ms"])
            self.update_preview()
            self.update_stats()
            self.add_log(f"成功导入 {len(self.schedule_data)} 条任务", "SUCCESS")
            self.save_config()
        except Exception as e:
            messagebox.showerror("导入失败", str(e))
            self.add_log(f"导入失败: {e}", "ERROR")

    def parse_time(self, t_str):
        h, m, s = map(int, t_str.split(":"))
        return (h * 3600 + m * 60 + s) * 1000

    # ---------- 日志与统计 ----------
    def create_log_file(self):
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_filename = f"interaction_log_{ts}.txt"
        self.log_file = open(self.log_filename, "w", encoding="utf-8")
        header = f"自动化互动工具 v6.5 - 运行日志\n{'='*60}\n开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n平台: {'macOS' if IS_MAC else 'Windows' if IS_WIN else 'Linux'}\n{'='*60}\n"
        self.log_file.write(header)
        self.log_file.flush()

    def add_log(self, message, level="INFO"):
        real_time = datetime.now().strftime("%H:%M:%S")
        if self.start_timestamp is not None:
            elapsed = time.time() - self.start_timestamp
            hrs = int(elapsed // 3600)
            mins = int((elapsed % 3600) // 60)
            secs = int(elapsed % 60)
            rel_time = f"+{hrs:02d}:{mins:02d}:{secs:02d}"
        else:
            rel_time = "------"

        line = f"[{real_time}] [{rel_time}] [{level}] {message}\n"

        if self.log_file:
            self.log_file.write(line)
            self.log_file.flush()

        self.log_text.configure(state="normal")
        self.log_text.insert(tk.END, f"[{real_time}] ", "time")
        self.log_text.insert(tk.END, f"[{rel_time}] ", "reltime")

        tag = level.lower()
        if level == "ERROR":
            self.log_text.insert(tk.END, f"[{level}] ", "error")
            self.log_text.insert(tk.END, f"{message}\n", "error")
        elif level == "SUCCESS":
            self.log_text.insert(tk.END, f"[{level}] ", "success")
            self.log_text.insert(tk.END, f"{message}\n", "success")
        elif level == "WARN":
            self.log_text.insert(tk.END, f"[{level}] ", "warn")
            self.log_text.insert(tk.END, f"{message}\n", "warn")
        else:
            self.log_text.insert(tk.END, f"[{level}] ", "info")
            self.log_text.insert(tk.END, f"{message}\n", "info")

        self.log_text.see(tk.END)
        self.log_text.configure(state="disabled")

    def clear_logs(self):
        self.log_text.configure(state="normal")
        self.log_text.delete(1.0, tk.END)
        self.log_text.configure(state="disabled")
        self.add_log("日志已清空", "INFO")

    def export_logs(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
            initialfile=self.log_filename
        )
        if path:
            try:
                with open(self.log_filename, "r", encoding="utf-8") as f:
                    content = f.read()
                with open(path, "w", encoding="utf-8") as f:
                    f.write(content)
                self.add_log(f"日志已导出: {path}", "SUCCESS")
                messagebox.showinfo("导出成功", f"日志已保存到:\n{path}")
            except Exception as e:
                messagebox.showerror("导出失败", str(e))

    def update_preview(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        for item in self.schedule_data:
            st = item["status"]
            tag = ""
            if st == "已发送":
                tag = "sent"
            elif st == "发送中":
                tag = "sending"
            elif st == "失败":
                tag = "error"
            elif st == "已跳过":
                tag = "skipped"
            display_text = item["text"][:45] + "..." if len(item["text"]) > 45 else item["text"]
            self.tree.insert("", tk.END, values=(item["time_str"], display_text, st), tags=(tag,))
        self.tree.tag_configure("sent", foreground="#16a34a")
        self.tree.tag_configure("sending", foreground="#d97706")
        self.tree.tag_configure("error", foreground="#dc2626")
        self.tree.tag_configure("skipped", foreground="#6b7280")

    def update_stats(self):
        total = len(self.schedule_data)
        sent = sum(1 for x in self.schedule_data if x["status"] == "已发送")
        pending = total - sent
        self.stat_total.config(text=f"总任务: {total}")
        self.stat_sent.config(text=f"已发送: {sent}")
        self.stat_pending.config(text=f"待发送: {pending}")

    # ---------- 进度更新（HH:MM:SS 格式） ----------
    def _format_time(self, seconds):
        if seconds < 0:
            seconds = 0
        hrs = int(seconds // 3600)
        mins = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"{hrs:02d}:{mins:02d}:{secs:02d}"   # 始终显示两位小时

    def _update_progress_display(self):
        total_time = self._get_total_time()
        if total_time <= 0:
            return
        elapsed = time.time() - self.start_timestamp
        percent = min(100.0, (elapsed / total_time) * 100)
        self.progress_value.set(percent)
        elapsed_str = self._format_time(elapsed)
        total_str = self._format_time(total_time)
        self.progress_time_label.config(text=f"{elapsed_str} / {total_str}")
        sent = sum(1 for x in self.schedule_data if x["status"] == "已发送")
        total = len(self.schedule_data)
        remaining = max(0, total - sent)
        self.progress_count_label.config(text=f"已发送: {sent} | 剩余: {remaining}")

    def _update_progress_loop(self):
        while self.progress_running and self.is_running:
            if not self.paused and self.start_timestamp is not None:
                self.root.after(0, self._update_progress_display)
            time.sleep(0.5)

    def _get_total_time(self):
        if not self.schedule_data:
            return 0
        return max(item["time_ms"] for item in self.schedule_data) / 1000.0

    def _start_progress_updater(self):
        self.progress_running = True
        threading.Thread(target=self._update_progress_loop, daemon=True).start()

    def _stop_progress_updater(self):
        self.progress_running = False

    # ---------- 核心自动化 ----------
    def start_automation(self):
        if not self.schedule_data:
            messagebox.showwarning("提示", "请先导入时间戳文件")
            return

        invalid_groups = []
        for g in self.coord_groups:
            if g["input_x"] == 0 and g["input_y"] == 0:
                invalid_groups.append(g["name"])
        if invalid_groups:
            messagebox.showwarning("提示", f"以下坐标组的输入框未设置有效坐标：\n{', '.join(invalid_groups)}\n请捕获输入框坐标。")
            return

        use_enter = self.use_enter_var.get()
        if not use_enter:
            no_send_groups = []
            for g in self.coord_groups:
                if g["send_x"] == 0 and g["send_y"] == 0:
                    no_send_groups.append(g["name"])
            if no_send_groups:
                messagebox.showwarning("提示", f"以下坐标组的发送按钮未设置，请捕获或使用回车发送：\n{', '.join(no_send_groups)}")
                return

        if not messagebox.askokcancel("准备执行",
            "请将目标窗口置于最前方，确保输入框可见。\n\n"
            f"坐标组数：{len(self.coord_groups)}，循环模式：{'开启' if self.loop_check.get() else '关闭（仅用第一组）'}\n"
            f"提前偏移：{self.offset_var.get():.2f} 秒\n"
            "点击「确定」后开始执行。"):
            return

        self.is_running = True
        self.paused = False
        self.sent_count = 0
        self.start_time = datetime.now()
        self.start_timestamp = time.time()

        for item in self.schedule_data:
            if item["status"] != "已发送":
                item["status"] = "等待"
        self.update_preview()
        self.update_stats()

        self.progress_value.set(0.0)
        total_time = self._get_total_time()
        self.progress_time_label.config(text="00:00:00 / " + self._format_time(total_time))
        self.progress_count_label.config(text="已发送: 0 | 剩余: " + str(len(self.schedule_data)))

        self.start_btn.config(state="disabled")
        self.pause_btn.config(state="normal", text="⏸  暂停")
        self.stop_btn.config(state="normal")
        self.jump_btn.config(state="normal")

        self.add_log("=" * 50, "INFO")
        self.add_log("🚀 自动化任务已启动", "SUCCESS")
        self.add_log(f"平台: {'macOS' if IS_MAC else 'Windows' if IS_WIN else 'Linux'}")
        self.add_log(f"粘贴快捷键: {'Cmd+V' if IS_MAC else 'Ctrl+V'}")
        self.add_log(f"坐标组数量: {len(self.coord_groups)}")
        self.add_log(f"任务总数: {len(self.schedule_data)}")
        self.add_log(f"最大时间: {self._get_total_time():.2f} 秒", "INFO")
        self.add_log(f"提前偏移: {self.offset_var.get():.2f} 秒", "INFO")
        self.add_log("⚠️ 紧急停止：鼠标移到屏幕左上角", "WARN")
        self.add_log("=" * 50, "INFO")

        self._start_progress_updater()
        self._start_scheduler_thread(use_enter)

    def _start_scheduler_thread(self, use_enter):
        if self.scheduler_thread and self.scheduler_thread.is_alive():
            self.is_running = False
            self.scheduler_thread.join(timeout=0.5)
        self.is_running = True
        self.scheduler_thread = threading.Thread(target=self._scheduler, args=(use_enter,), daemon=True)
        self.scheduler_thread.start()

    def toggle_pause(self):
        if self.paused:
            self.paused = False
            self.pause_btn.config(text="⏸  暂停")
            self.add_log("▶ 已继续运行", "INFO")
        else:
            self.paused = True
            self.pause_btn.config(text="▶  继续")
            self.add_log("⏸ 已暂停运行", "WARN")
            if self.start_timestamp is not None:
                elapsed = time.time() - self.start_timestamp
                self.jump_var.set(self._format_time(elapsed))   # HH:MM:SS 格式

    def jump_to_time(self):
        if not self.is_running:
            messagebox.showinfo("提示", "请先开始运行")
            return
        raw = self.jump_var.get().strip()
        if not raw:
            return
        try:
            target_seconds = float(raw)
        except ValueError:
            try:
                parts = raw.split(':')
                if len(parts) == 3:
                    h = int(parts[0]); m = int(parts[1]); s = int(parts[2])
                    target_seconds = h * 3600 + m * 60 + s
                elif len(parts) == 2:
                    m = int(parts[0]); s = int(parts[1])
                    target_seconds = m * 60 + s
                else:
                    messagebox.showerror("错误", "无效的时间格式，请使用秒数或 HH:MM:SS")
                    return
            except:
                messagebox.showerror("错误", "无效的时间格式")
                return

        if target_seconds < 0:
            messagebox.showerror("错误", "时间不能为负数")
            return

        self.is_running = False
        if self.scheduler_thread and self.scheduler_thread.is_alive():
            self.scheduler_thread.join(timeout=0.5)
        self._stop_progress_updater()

        for item in self.schedule_data:
            if item["time_ms"] / 1000.0 >= target_seconds:
                item["status"] = "等待"
            else:
                item["status"] = "已跳过"

        self.start_timestamp = time.time() - target_seconds
        self.sent_count = 0
        self.update_preview()
        self.update_stats()
        self.add_log(f"⏩ 跳转到 {target_seconds:.2f} 秒，该时间之后的消息重新执行", "SUCCESS")

        self.is_running = True
        self.paused = False
        self.pause_btn.config(text="⏸  暂停")
        self.progress_value.set(0.0)
        total_time = self._get_total_time()
        self.progress_time_label.config(text="00:00:00 / " + self._format_time(total_time))
        sent = sum(1 for x in self.schedule_data if x["status"] == "已发送")
        total = len(self.schedule_data)
        remaining = total - sent
        self.progress_count_label.config(text=f"已发送: {sent} | 剩余: {remaining}")

        self.jump_var.set("")   # 清空输入框

        self._start_progress_updater()
        use_enter = self.use_enter_var.get()
        self._start_scheduler_thread(use_enter)

    def _scheduler(self, use_enter):
        t0 = self.start_timestamp
        group_count = len(self.coord_groups)
        loop = self.loop_check.get()
        offset = self.offset_var.get()
        if offset < 0:
            offset = 0.0

        for item in self.schedule_data:
            if not self.is_running:
                break
            if item["status"] in ("已发送", "已跳过"):
                continue
            while self.paused and self.is_running:
                time.sleep(0.05)
            if not self.is_running:
                break

            target_sec = item["time_ms"] / 1000.0
            now = time.time()
            wait_time = target_sec - (now - t0) - offset

            if wait_time > 0:
                end_wait = time.time() + wait_time
                while time.time() < end_wait and self.is_running:
                    if self.paused:
                        time.sleep(0.05)
                        continue
                    if self.start_timestamp != t0:
                        t0 = self.start_timestamp
                        new_wait = target_sec - (time.time() - t0) - offset
                        if new_wait > 0:
                            end_wait = time.time() + new_wait
                            continue
                        else:
                            break
                    time.sleep(0.01)

            if not self.is_running:
                break

            if loop and group_count > 1:
                group_index = self.sent_count % group_count
            else:
                group_index = 0
            group = self.coord_groups[group_index]

            start_exec = time.time()
            exec_offset = start_exec - t0
            self.root.after(0, lambda it=item: self._set_status(it, "发送中"))
            self.root.after(0, lambda t=item["time_str"], g=group["name"], of=exec_offset:
                            self.add_log(f"⏰ 触发 [{t}] 实际开始 {of:.2f}s (提前 {offset:.2f}s) 使用组「{g}」", "WARN"))

            ok = self._execute(item["text"], group, use_enter)
            end_exec = time.time()
            self.root.after(0, lambda: self.add_log(f"  发送耗时: {end_exec - start_exec:.2f} 秒", "INFO"))

            if ok:
                self.root.after(0, lambda it=item: self._set_status(it, "已发送"))
                short = item["text"][:35] + "..." if len(item["text"]) > 35 else item["text"]
                self.root.after(0, lambda s=short, g=group["name"]:
                                self.add_log(f"✅ 已发送 [{g}]: {s}", "SUCCESS"))
                self.sent_count += 1
            else:
                if self.paused:
                    self.root.after(0, lambda: self.add_log("  操作因暂停而中止", "WARN"))
                    while self.paused and self.is_running:
                        time.sleep(0.05)
                    if not self.is_running:
                        break
                    self.root.after(0, lambda it=item: self._set_status(it, "等待"))
                    continue
                else:
                    self.root.after(0, lambda it=item: self._set_status(it, "失败"))
                    short = item["text"][:35] + "..." if len(item["text"]) > 35 else item["text"]
                    self.root.after(0, lambda s=short: self.add_log(f"❌ 发送失败: {s}", "ERROR"))
            self.root.after(0, self.update_stats)

        if self.is_running:
            self.root.after(0, lambda: self.add_log("🎉 所有任务执行完毕！", "SUCCESS"))
            self.root.after(0, self.stop_automation)

    def _set_status(self, item, status):
        item["status"] = status
        self.update_preview()

    def _execute(self, text, group, use_enter):
        try:
            input_x = group["input_x"]
            input_y = group["input_y"]
            send_x = group["send_x"]
            send_y = group["send_y"]

            self.root.after(0, lambda: self.add_log(f"  坐标组「{group['name']}」输入框({input_x},{input_y}) 发送({send_x},{send_y})", "INFO"))

            if self.paused:
                return False

            pyautogui.moveTo(input_x, input_y, duration=0.1)
            time.sleep(0.1)
            if self.paused:
                return False

            self.root.after(0, lambda: self.add_log("  激活输入框 (点击3次)...", "INFO"))
            for _ in range(3):
                if self.paused:
                    return False
                pyautogui.click(input_x, input_y)
                time.sleep(0.08)
            time.sleep(0.2)
            if self.paused:
                return False

            pyautogui.click(input_x + 15, input_y + 8)
            time.sleep(0.1)
            if self.paused:
                return False
            pyautogui.click(input_x, input_y)
            time.sleep(0.3)
            if self.paused:
                return False

            self.root.after(0, lambda: self.add_log("  清空输入框...", "INFO"))
            with kb.pressed(keyboard.Key.ctrl if not IS_MAC else keyboard.Key.cmd):
                kb.press('a')
                kb.release('a')
            time.sleep(0.1)
            if self.paused:
                return False
            kb.press(keyboard.Key.delete)
            kb.release(keyboard.Key.delete)
            time.sleep(0.2)
            if self.paused:
                return False

            pyautogui.click(input_x, input_y)
            time.sleep(0.2)
            if self.paused:
                return False

            self.root.after(0, lambda: self.add_log("  写入剪贴板...", "INFO"))
            pyperclip.copy(text)
            time.sleep(0.1)
            if self.paused:
                return False
            if pyperclip.paste() != text:
                self.root.after(0, lambda: self.add_log("  剪贴板验证失败，重试...", "WARN"))
                pyperclip.copy(text)
                time.sleep(0.1)
                if self.paused:
                    return False

            self.root.after(0, lambda: self.add_log("  执行粘贴 (pynput)...", "INFO"))
            with kb.pressed(keyboard.Key.ctrl if not IS_MAC else keyboard.Key.cmd):
                kb.press('v')
                kb.release('v')
            time.sleep(0.6)
            if self.paused:
                return False

            if use_enter:
                self.root.after(0, lambda: self.add_log("  按下回车键发送...", "INFO"))
                kb.press(keyboard.Key.enter)
                kb.release(keyboard.Key.enter)
                time.sleep(0.3)
            else:
                self.root.after(0, lambda: self.add_log("  点击发送按钮...", "INFO"))
                pyautogui.click(send_x, send_y)
                time.sleep(0.3)
            if self.paused:
                return False

            return True

        except pyautogui.FailSafeException:
            self.root.after(0, lambda: self.add_log("🛑 触发 FAILSAFE，任务已中断", "ERROR"))
            self.root.after(0, self.stop_automation)
            return False
        except Exception as e:
            self.root.after(0, lambda err=e: self.add_log(f"执行异常: {err}", "ERROR"))
            return False

    def stop_automation(self):
        self.is_running = False
        self.paused = False
        self._stop_progress_updater()
        self.start_btn.config(state="normal")
        self.pause_btn.config(state="disabled", text="⏸  暂停")
        self.stop_btn.config(state="disabled")
        self.jump_btn.config(state="disabled")
        self.progress_value.set(0.0)
        total_time = self._get_total_time()
        self.progress_time_label.config(text="00:00:00 / " + self._format_time(total_time))
        self.progress_count_label.config(text="已发送: 0 | 剩余: 0")
        self.add_log("⏹ 自动化任务已停止", "WARN")

    def on_close(self):
        self.is_running = False
        self._stop_progress_updater()
        self.save_config()
        if self.log_file:
            self.log_file.write(f"\n{'='*60}\n结束时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            self.log_file.close()
        self.root.destroy()


def main():
    root = tk.Tk()
    app = AutoInteractionTool(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()


if __name__ == "__main__":
    main()