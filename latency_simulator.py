"""
Network Latency Simulator
Made by Yuvraj Singh Rangi
PCTE Group of Institutes, Ludhiana, Punjab
© 2026
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading
import socket
import time
import random
import os
import csv
import json
import datetime
import struct
import queue
import sys

# Optional: system tray
try:
    import pystray
    from PIL import Image, ImageDraw
    TRAY_AVAILABLE = True
except ImportError:
    TRAY_AVAILABLE = False

# Optional: matplotlib graph
try:
    import matplotlib
    matplotlib.use("TkAgg")
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    GRAPH_AVAILABLE = True
except ImportError:
    GRAPH_AVAILABLE = False


# ─── Constants ────────────────────────────────────────────────────────────────
APP_NAME    = "Network Latency Simulator"
APP_VERSION = "1.0.0"
AUTHOR      = "Yuvraj Singh Rangi"
COLLEGE     = "PCTE Group of Institutes"
CITY        = "Ludhiana, Punjab"
YEAR        = "2026"

MAX_LOG_ROWS  = 500
GRAPH_POINTS  = 60          # seconds of history
PING_TIMEOUT  = 2.0

COLORS = {
    "bg":         "#1e1e2e",
    "sidebar":    "#181825",
    "topbar":     "#181825",
    "card":       "#252537",
    "border":     "#313145",
    "accent":     "#378ADD",
    "success":    "#4CAF50",
    "warning":    "#EF9F27",
    "danger":     "#E24B4A",
    "info":       "#378ADD",
    "text":       "#cdd6f4",
    "text2":      "#a6adc8",
    "text3":      "#6c7086",
    "tag_ok":     "#1e3a2e",
    "tag_ok_fg":  "#4CAF50",
    "tag_dl":     "#3a2e1e",
    "tag_dl_fg":  "#EF9F27",
    "tag_dr":     "#3a1e1e",
    "tag_dr_fg":  "#E24B4A",
    "tag_in":     "#1e2e3a",
    "tag_in_fg":  "#378ADD",
    "tag_sv":     "#252537",
    "tag_sv_fg":  "#a6adc8",
}

PRESETS = {
    "LAN":       {"delay": 2,    "jitter": 1,   "loss": 0,  "bw": 1000},
    "3G":        {"delay": 150,  "jitter": 40,  "loss": 2,  "bw": 2},
    "4G":        {"delay": 40,   "jitter": 15,  "loss": 1,  "bw": 20},
    "Satellite": {"delay": 600,  "jitter": 100, "loss": 3,  "bw": 5},
    "Custom":    {"delay": 80,   "jitter": 20,  "loss": 2,  "bw": 10},
}

TARGET_COLORS = ["#378ADD", "#EF9F27", "#4CAF50", "#E24B4A", "#a855f7", "#ec4899"]


# ─── Helper: ICMP Ping ────────────────────────────────────────────────────────
def checksum(data):
    s = 0
    for i in range(0, len(data), 2):
        if i + 1 < len(data):
            s += (data[i] << 8) + data[i + 1]
        else:
            s += data[i] << 8
    s = (s >> 16) + (s & 0xffff)
    s += (s >> 16)
    return ~s & 0xffff


def icmp_ping(host, timeout=2.0):
    """Returns RTT in ms or None on failure."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_ICMP)
        sock.settimeout(timeout)
        pid = os.getpid() & 0xFFFF
        seq = random.randint(0, 65535)
        header = struct.pack("bbHHh", 8, 0, 0, pid, seq)
        payload = b"latency_sim_payload"
        chk = checksum(header + payload)
        header = struct.pack("bbHHh", 8, 0, chk, pid, seq)
        packet = header + payload
        dest = socket.gethostbyname(host)
        sock.sendto(packet, (dest, 0))
        t_send = time.time()
        sock.recvfrom(1024)
        rtt = (time.time() - t_send) * 1000
        sock.close()
        return rtt
    except Exception:
        return None


def tcp_ping(host, port, timeout=2.0):
    """Returns RTT in ms or None on failure."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        t = time.time()
        s.connect((host, int(port)))
        rtt = (time.time() - t) * 1000
        s.close()
        return rtt
    except Exception:
        return None


# ─── Main Application ─────────────────────────────────────────────────────────
class LatencySimulator(tk.Tk):

    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.geometry("1020x680")
        self.minsize(820, 560)
        self.configure(bg=COLORS["bg"])

        # State
        self.running        = False
        self.log_queue      = queue.Queue()
        self.targets        = []          # list of dict {ip, port, protocol, color, data[]}
        self.worker_threads = []
        self.stats          = {"sent": 0, "dropped": 0, "total_rtt": 0.0, "count": 0}
        self.graph_expanded = False

        # Settings vars (set before build_ui)
        self.var_delay     = tk.IntVar(value=80)
        self.var_jitter    = tk.IntVar(value=20)
        self.var_loss      = tk.IntVar(value=2)
        self.var_bw        = tk.IntVar(value=10)
        self.var_spike_to  = tk.IntVar(value=500)
        self.var_spike_dur = tk.IntVar(value=10)
        self.var_log_en    = tk.BooleanVar(value=True)
        self.var_log_path  = tk.StringVar(value=os.path.join(os.path.expanduser("~"), "LabLogs", "latency"))
        self.var_log_fmt   = tk.StringVar(value="CSV")
        self.var_tray_min  = tk.BooleanVar(value=True)
        self.var_tray_start= tk.BooleanVar(value=False)
        self.var_tray_alert= tk.BooleanVar(value=True)
        self.var_protocol  = tk.StringVar(value="ICMP (ping)")
        self.var_ip        = tk.StringVar(value="192.168.1.1")
        self.var_port      = tk.StringVar(value="80")
        self.var_preset    = tk.StringVar(value="Custom")

        # Spike state
        self.spike_active   = False
        self.spike_end_time = 0

        self.build_ui()
        self.add_default_target()
        self.poll_log_queue()

        self.protocol("WM_DELETE_WINDOW", self.on_close)

    # ── UI Build ──────────────────────────────────────────────────────────────

    def build_ui(self):
        self._style()
        self._topbar()

        # Main paned layout
        body = tk.Frame(self, bg=COLORS["bg"])
        body.pack(fill="both", expand=True)

        self._sidebar(body)
        self._main_panel(body)
        self._bottombar()

    def _style(self):
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure(".", background=COLORS["bg"], foreground=COLORS["text"],
                    fieldbackground=COLORS["card"], bordercolor=COLORS["border"],
                    darkcolor=COLORS["border"], lightcolor=COLORS["border"],
                    troughcolor=COLORS["card"], selectbackground=COLORS["accent"],
                    selectforeground="white", font=("Segoe UI", 10))
        s.configure("TEntry", fieldbackground=COLORS["card"], foreground=COLORS["text"],
                    bordercolor=COLORS["border"], insertcolor=COLORS["text"])
        s.configure("TCombobox", fieldbackground=COLORS["card"], foreground=COLORS["text"],
                    bordercolor=COLORS["border"], arrowcolor=COLORS["text2"])
        s.map("TCombobox", fieldbackground=[("readonly", COLORS["card"])],
              foreground=[("readonly", COLORS["text"])])
        s.configure("TScale", troughcolor=COLORS["border"], background=COLORS["accent"])
        s.configure("TCheckbutton", background=COLORS["sidebar"], foreground=COLORS["text2"],
                    indicatorcolor=COLORS["card"])
        s.map("TCheckbutton", indicatorcolor=[("selected", COLORS["accent"])])
        s.configure("Vertical.TScrollbar", background=COLORS["card"],
                    troughcolor=COLORS["bg"], bordercolor=COLORS["border"],
                    arrowcolor=COLORS["text3"])

    def _topbar(self):
        bar = tk.Frame(self, bg=COLORS["topbar"], height=46)
        bar.pack(fill="x", side="top")
        bar.pack_propagate(False)

        # Icon + title
        left = tk.Frame(bar, bg=COLORS["topbar"])
        left.pack(side="left", padx=14, pady=8)

        icon_canvas = tk.Canvas(left, width=28, height=28, bg=COLORS["topbar"],
                                highlightthickness=0)
        icon_canvas.pack(side="left", padx=(0, 8))
        self._draw_icon(icon_canvas, 14, 14, 13)

        tk.Label(left, text=APP_NAME, bg=COLORS["topbar"], fg=COLORS["text"],
                 font=("Segoe UI", 12, "bold")).pack(side="left")

        # Right pills + about
        right = tk.Frame(bar, bg=COLORS["topbar"])
        right.pack(side="right", padx=14, pady=8)

        tk.Button(right, text="About", bg=COLORS["card"], fg=COLORS["text2"],
                  font=("Segoe UI", 9), relief="flat", bd=0, padx=10, pady=3,
                  cursor="hand2", command=self.show_about).pack(side="left", padx=4)

        self.lbl_tray = tk.Label(right, text="System Tray", bg="#1e2e3a", fg=COLORS["accent"],
                                  font=("Segoe UI", 9), padx=8, pady=3)
        self.lbl_tray.pack(side="left", padx=4)

        self.lbl_status = tk.Label(right, text="Stopped", bg=COLORS["tag_dr"], fg=COLORS["danger"],
                                    font=("Segoe UI", 9, "bold"), padx=8, pady=3)
        self.lbl_status.pack(side="left", padx=4)

    def _draw_icon(self, canvas, cx, cy, r, size=1.0):
        """Draw the clock/radar icon on a canvas."""
        canvas.create_oval(cx-r, cy-r, cx+r, cy+r, fill=COLORS["accent"], outline="")
        # tick marks
        import math
        for angle in range(0, 360, 45):
            rad = math.radians(angle)
            x1 = cx + (r-4)*math.cos(rad)
            y1 = cy + (r-4)*math.sin(rad)
            x2 = cx + (r-1)*math.cos(rad)
            y2 = cy + (r-1)*math.sin(rad)
            canvas.create_line(x1, y1, x2, y2, fill="white", width=1)
        # hands
        canvas.create_line(cx, cy, cx, cy-r+5, fill="white", width=2, capstyle="round")
        canvas.create_line(cx, cy, cx+r-6, cy+3, fill="white", width=2, capstyle="round")
        canvas.create_oval(cx-2, cy-2, cx+2, cy+2, fill="white", outline="")

    def _sidebar(self, parent):
        frame = tk.Frame(parent, bg=COLORS["sidebar"], width=270)
        frame.pack(side="left", fill="y")
        frame.pack_propagate(False)

        canvas = tk.Canvas(frame, bg=COLORS["sidebar"], highlightthickness=0)
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=canvas.yview)
        self.sidebar_inner = tk.Frame(canvas, bg=COLORS["sidebar"])

        self.sidebar_inner.bind("<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.sidebar_inner, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        p = self.sidebar_inner

        self._sec(p, "PRESETS")
        self._presets(p)
        self._divider(p)

        self._sec(p, "TARGET")
        self._target_fields(p)
        self._divider(p)

        self._sec(p, "LATENCY")
        self._slider(p, "Base delay (ms)", self.var_delay, 0, 2000)
        self._slider(p, "Jitter (ms)", self.var_jitter, 0, 500)
        self._divider(p)

        self._sec(p, "PACKET BEHAVIOR")
        self._slider(p, "Packet loss (%)", self.var_loss, 0, 100)
        self._slider(p, "Bandwidth (Mbps)", self.var_bw, 1, 1000)
        self._divider(p)

        self._sec(p, "SCHEDULED SPIKE")
        self._slider(p, "Spike to (ms)", self.var_spike_to, 100, 5000)
        self._slider(p, "Duration (s)", self.var_spike_dur, 1, 120)
        tk.Button(p, text="Fire Spike Now", bg=COLORS["tag_dl"], fg=COLORS["warning"],
                  font=("Segoe UI", 9), relief="flat", bd=0, pady=4,
                  cursor="hand2", command=self.fire_spike).pack(fill="x", padx=12, pady=(4, 0))
        self._divider(p)

        self._sec(p, "AUTO LOGGING")
        self._toggle(p, "Save log to file", self.var_log_en)
        self._field_row(p, "Log folder", self.var_log_path, browse=True)
        self._combo(p, "Format", self.var_log_fmt, ["CSV", "JSON", "TXT"])
        self._divider(p)

        self._sec(p, "SYSTEM TRAY")
        self._toggle(p, "Minimize to tray", self.var_tray_min)
        self._toggle(p, "Start with Windows", self.var_tray_start)
        self._toggle(p, "Alert on packet drop", self.var_tray_alert)

    def _sec(self, parent, text):
        tk.Label(parent, text=text, bg=COLORS["sidebar"], fg=COLORS["text3"],
                 font=("Segoe UI", 8, "bold")).pack(anchor="w", padx=12, pady=(10, 2))

    def _divider(self, parent):
        tk.Frame(parent, bg=COLORS["border"], height=1).pack(fill="x", padx=8, pady=4)

    def _slider(self, parent, label, var, from_, to):
        row = tk.Frame(parent, bg=COLORS["sidebar"])
        row.pack(fill="x", padx=12, pady=2)
        tk.Label(row, text=label, bg=COLORS["sidebar"], fg=COLORS["text2"],
                 font=("Segoe UI", 9)).pack(side="left")
        badge = tk.Label(row, text=str(var.get()), bg=COLORS["tag_in"], fg=COLORS["accent"],
                         font=("Segoe UI", 9, "bold"), padx=6, pady=1)
        badge.pack(side="right")

        def update(v):
            badge.config(text=str(int(float(v))))

        sl = ttk.Scale(parent, from_=from_, to=to, orient="horizontal", variable=var,
                       command=update)
        sl.pack(fill="x", padx=12, pady=(0, 2))

    def _toggle(self, parent, label, var):
        row = tk.Frame(parent, bg=COLORS["sidebar"])
        row.pack(fill="x", padx=12, pady=3)
        tk.Label(row, text=label, bg=COLORS["sidebar"], fg=COLORS["text2"],
                 font=("Segoe UI", 9)).pack(side="left")
        ttk.Checkbutton(row, variable=var).pack(side="right")

    def _field_row(self, parent, label, var, browse=False):
        tk.Label(parent, text=label, bg=COLORS["sidebar"], fg=COLORS["text2"],
                 font=("Segoe UI", 9)).pack(anchor="w", padx=12)
        row = tk.Frame(parent, bg=COLORS["sidebar"])
        row.pack(fill="x", padx=12, pady=(1, 4))
        e = tk.Entry(row, textvariable=var, bg=COLORS["card"], fg=COLORS["text"],
                     insertbackground=COLORS["text"], relief="flat", font=("Segoe UI", 9),
                     bd=1, highlightthickness=1, highlightbackground=COLORS["border"])
        e.pack(side="left", fill="x", expand=True)
        if browse:
            tk.Button(row, text="...", bg=COLORS["card"], fg=COLORS["text2"],
                      font=("Segoe UI", 9), relief="flat", bd=0, padx=6,
                      cursor="hand2",
                      command=lambda: var.set(filedialog.askdirectory() or var.get())
                      ).pack(side="left", padx=(2, 0))

    def _combo(self, parent, label, var, values):
        tk.Label(parent, text=label, bg=COLORS["sidebar"], fg=COLORS["text2"],
                 font=("Segoe UI", 9)).pack(anchor="w", padx=12)
        cb = ttk.Combobox(parent, textvariable=var, values=values, state="readonly",
                          font=("Segoe UI", 9))
        cb.pack(fill="x", padx=12, pady=(1, 4))

    def _presets(self, parent):
        row = tk.Frame(parent, bg=COLORS["sidebar"])
        row.pack(fill="x", padx=12, pady=2)
        self.preset_btns = {}
        for name in PRESETS:
            b = tk.Button(row, text=name, bg=COLORS["card"], fg=COLORS["text2"],
                          font=("Segoe UI", 9), relief="flat", bd=0, padx=8, pady=4,
                          cursor="hand2", command=lambda n=name: self.apply_preset(n))
            b.pack(side="left", padx=2)
            self.preset_btns[name] = b
        self.apply_preset("Custom", silent=True)

    def _target_fields(self, parent):
        self._field_row(parent, "IP / Hostname", self.var_ip)
        self._field_row(parent, "Port", self.var_port)
        self._combo(parent, "Protocol", self.var_protocol,
                    ["ICMP (ping)", "TCP", "UDP"])
        tk.Button(parent, text="+ Add Target", bg=COLORS["tag_in"], fg=COLORS["accent"],
                  font=("Segoe UI", 9), relief="flat", bd=0, pady=4,
                  cursor="hand2", command=self.add_target_from_ui).pack(fill="x", padx=12, pady=4)

    def _main_panel(self, parent):
        frame = tk.Frame(parent, bg=COLORS["bg"])
        frame.pack(side="left", fill="both", expand=True)

        self._stats_bar(frame)
        self._graph_section(frame)
        self._targets_bar(frame)
        self._log_section(frame)

    def _stats_bar(self, parent):
        bar = tk.Frame(parent, bg=COLORS["sidebar"])
        bar.pack(fill="x")
        tk.Frame(bar, bg=COLORS["border"], height=1).pack(fill="x")

        inner = tk.Frame(bar, bg=COLORS["sidebar"])
        inner.pack(fill="x", padx=12, pady=8)

        self.stat_labels = {}
        stats = [
            ("avg_rtt",  "Avg latency",  "-- ms",   COLORS["warning"]),
            ("sent",     "Packets sent", "0",        COLORS["text"]),
            ("dropped",  "Dropped",      "0",        COLORS["danger"]),
            ("success",  "Success rate", "--%",      COLORS["success"]),
        ]
        for key, label, default, color in stats:
            card = tk.Frame(inner, bg=COLORS["card"], padx=10, pady=6)
            card.pack(side="left", padx=4, fill="x", expand=True)
            tk.Label(card, text=label, bg=COLORS["card"], fg=COLORS["text3"],
                     font=("Segoe UI", 8)).pack(anchor="w")
            lbl = tk.Label(card, text=default, bg=COLORS["card"], fg=color,
                           font=("Segoe UI", 15, "bold"))
            lbl.pack(anchor="w")
            self.stat_labels[key] = lbl

        tk.Frame(bar, bg=COLORS["border"], height=1).pack(fill="x")

    def _graph_section(self, parent):
        self.graph_frame = tk.Frame(parent, bg=COLORS["bg"])
        self.graph_frame.pack(fill="x")

        header = tk.Frame(self.graph_frame, bg=COLORS["sidebar"])
        header.pack(fill="x")

        tk.Label(header, text="Live ping graph (60s)", bg=COLORS["sidebar"],
                 fg=COLORS["text2"], font=("Segoe UI", 9, "bold")).pack(side="left", padx=12, pady=6)

        self.btn_expand = tk.Button(header, text="▲ Expand", bg=COLORS["card"],
                                    fg=COLORS["text2"], font=("Segoe UI", 9),
                                    relief="flat", bd=0, padx=8, pady=3,
                                    cursor="hand2", command=self.toggle_graph)
        self.btn_expand.pack(side="right", padx=8, pady=4)

        # Legend
        self.legend_frame = tk.Frame(header, bg=COLORS["sidebar"])
        self.legend_frame.pack(side="right", padx=8)

        tk.Frame(header, bg=COLORS["border"], height=1).pack(fill="x", side="bottom")

        # Graph canvas container
        self.graph_container = tk.Frame(self.graph_frame, bg=COLORS["bg"], height=52)
        self.graph_container.pack(fill="x")
        self.graph_container.pack_propagate(False)

        if GRAPH_AVAILABLE:
            self.fig = Figure(figsize=(6, 1.2), dpi=80, facecolor=COLORS["bg"])
            self.ax  = self.fig.add_subplot(111)
            self._style_ax()
            self.graph_canvas = FigureCanvasTkAgg(self.fig, master=self.graph_container)
            self.graph_canvas.get_tk_widget().pack(fill="both", expand=True)
            self.graph_canvas.draw()
        else:
            tk.Label(self.graph_container, text="Install matplotlib for live graph",
                     bg=COLORS["bg"], fg=COLORS["text3"], font=("Segoe UI", 9)
                     ).pack(expand=True)

        tk.Frame(self.graph_frame, bg=COLORS["border"], height=1).pack(fill="x")

    def _style_ax(self):
        self.ax.clear()
        self.ax.set_facecolor(COLORS["bg"])
        self.ax.tick_params(colors=COLORS["text3"], labelsize=7)
        for spine in self.ax.spines.values():
            spine.set_edgecolor(COLORS["border"])
        self.ax.set_ylim(0, 500)
        self.ax.set_xlim(0, GRAPH_POINTS - 1)
        self.ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(
            lambda x, _: f"{int(x)}ms") if GRAPH_AVAILABLE else None)
        self.fig.tight_layout(pad=0.4)

    def _targets_bar(self, parent):
        bar = tk.Frame(parent, bg=COLORS["sidebar"])
        bar.pack(fill="x")

        header = tk.Frame(bar, bg=COLORS["sidebar"])
        header.pack(fill="x", padx=12, pady=(6, 4))
        tk.Label(header, text="Active targets", bg=COLORS["sidebar"],
                 fg=COLORS["text2"], font=("Segoe UI", 9, "bold")).pack(side="left")

        self.targets_chips_frame = tk.Frame(bar, bg=COLORS["sidebar"])
        self.targets_chips_frame.pack(fill="x", padx=12, pady=(0, 6))
        tk.Frame(bar, bg=COLORS["border"], height=1).pack(fill="x")

    def _log_section(self, parent):
        frame = tk.Frame(parent, bg=COLORS["bg"])
        frame.pack(fill="both", expand=True)

        self.log_text = tk.Text(frame, bg=COLORS["bg"], fg=COLORS["text2"],
                                font=("Consolas", 9), relief="flat", bd=0,
                                state="disabled", wrap="none",
                                selectbackground=COLORS["accent"])
        scroll_y = ttk.Scrollbar(frame, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scroll_y.set)

        scroll_y.pack(side="right", fill="y")
        self.log_text.pack(fill="both", expand=True, padx=4, pady=4)

        # Tag styles
        self.log_text.tag_configure("time",  foreground=COLORS["text3"])
        self.log_text.tag_configure("ok",    foreground=COLORS["success"])
        self.log_text.tag_configure("delay", foreground=COLORS["warning"])
        self.log_text.tag_configure("drop",  foreground=COLORS["danger"])
        self.log_text.tag_configure("info",  foreground=COLORS["accent"])
        self.log_text.tag_configure("saved", foreground=COLORS["text3"])
        self.log_text.tag_configure("tray",  foreground=COLORS["accent"])
        self.log_text.tag_configure("msg",   foreground=COLORS["text2"])
        self.log_text.tag_configure("target",foreground=COLORS["text3"])

    def _bottombar(self):
        bar = tk.Frame(self, bg=COLORS["sidebar"], height=46)
        bar.pack(fill="x", side="bottom")
        bar.pack_propagate(False)
        tk.Frame(bar, bg=COLORS["border"], height=1).pack(fill="x", side="top")

        inner = tk.Frame(bar, bg=COLORS["sidebar"])
        inner.pack(fill="both", expand=True, padx=10, pady=6)

        self.btn_start = tk.Button(inner, text="▶  Start", bg=COLORS["tag_ok"],
                                   fg=COLORS["success"], font=("Segoe UI", 10, "bold"),
                                   relief="flat", bd=0, padx=16, pady=4,
                                   cursor="hand2", command=self.start_simulation)
        self.btn_start.pack(side="left", padx=4)

        self.btn_stop = tk.Button(inner, text="■  Stop", bg=COLORS["tag_dr"],
                                  fg=COLORS["danger"], font=("Segoe UI", 10, "bold"),
                                  relief="flat", bd=0, padx=16, pady=4,
                                  cursor="hand2", command=self.stop_simulation,
                                  state="disabled")
        self.btn_stop.pack(side="left", padx=4)

        tk.Button(inner, text="Clear log", bg=COLORS["card"], fg=COLORS["text2"],
                  font=("Segoe UI", 9), relief="flat", bd=0, padx=10, pady=4,
                  cursor="hand2", command=self.clear_log).pack(side="left", padx=4)

        tk.Button(inner, text="Export CSV", bg=COLORS["card"], fg=COLORS["text2"],
                  font=("Segoe UI", 9), relief="flat", bd=0, padx=10, pady=4,
                  cursor="hand2", command=lambda: self.export_log("CSV")).pack(side="right", padx=4)

        tk.Button(inner, text="Export JSON", bg=COLORS["card"], fg=COLORS["text2"],
                  font=("Segoe UI", 9), relief="flat", bd=0, padx=10, pady=4,
                  cursor="hand2", command=lambda: self.export_log("JSON")).pack(side="right", padx=4)

        self.lbl_logpath = tk.Label(inner, text="Logging disabled", bg=COLORS["sidebar"],
                                    fg=COLORS["text3"], font=("Consolas", 8))
        self.lbl_logpath.pack(side="left", padx=8)

    # ── Logic ─────────────────────────────────────────────────────────────────

    def apply_preset(self, name, silent=False):
        p = PRESETS[name]
        self.var_delay.set(p["delay"])
        self.var_jitter.set(p["jitter"])
        self.var_loss.set(p["loss"])
        self.var_bw.set(p["bw"])
        self.var_preset.set(name)
        for n, b in self.preset_btns.items():
            b.config(bg=COLORS["tag_in"] if n == name else COLORS["card"],
                     fg=COLORS["accent"] if n == name else COLORS["text2"])

    def add_default_target(self):
        self._add_target("192.168.1.1", "80", "ICMP (ping)")

    def add_target_from_ui(self):
        ip   = self.var_ip.get().strip()
        port = self.var_port.get().strip()
        proto= self.var_protocol.get()
        if not ip:
            messagebox.showwarning("Missing IP", "Please enter an IP or hostname.")
            return
        self._add_target(ip, port, proto)

    def _add_target(self, ip, port, proto):
        color = TARGET_COLORS[len(self.targets) % len(TARGET_COLORS)]
        t = {"ip": ip, "port": port, "protocol": proto,
             "color": color, "data": [0] * GRAPH_POINTS,
             "last_ms": "--", "last_status": "idle"}
        self.targets.append(t)
        self._refresh_target_chips()
        self._refresh_legend()
        if self.running:
            self._spawn_worker(t)

    def _refresh_target_chips(self):
        for w in self.targets_chips_frame.winfo_children():
            w.destroy()
        for t in self.targets:
            chip = tk.Frame(self.targets_chips_frame, bg=COLORS["card"],
                            padx=8, pady=3)
            chip.pack(side="left", padx=3, pady=2)
            dot_color = (COLORS["success"] if t["last_status"] == "ok"
                         else COLORS["warning"] if t["last_status"] == "delay"
                         else COLORS["danger"] if t["last_status"] == "drop"
                         else COLORS["text3"])
            tk.Label(chip, text="●", bg=COLORS["card"], fg=dot_color,
                     font=("Segoe UI", 8)).pack(side="left")
            tk.Label(chip, text=f" {t['ip']}", bg=COLORS["card"], fg=COLORS["text"],
                     font=("Segoe UI", 9)).pack(side="left")
            tk.Label(chip, text=f"  {t['last_ms']}", bg=COLORS["card"], fg=COLORS["text3"],
                     font=("Consolas", 8)).pack(side="left")
            # Remove button
            tk.Button(chip, text="✕", bg=COLORS["card"], fg=COLORS["text3"],
                      font=("Segoe UI", 7), relief="flat", bd=0, cursor="hand2",
                      command=lambda tgt=t: self.remove_target(tgt)).pack(side="left", padx=(4, 0))

    def remove_target(self, t):
        if t in self.targets:
            self.targets.remove(t)
            self._refresh_target_chips()
            self._refresh_legend()

    def _refresh_legend(self):
        for w in self.legend_frame.winfo_children():
            w.destroy()
        for t in self.targets:
            f = tk.Frame(self.legend_frame, bg=COLORS["sidebar"])
            f.pack(side="left", padx=6)
            tk.Label(f, text="●", bg=COLORS["sidebar"], fg=t["color"],
                     font=("Segoe UI", 9)).pack(side="left")
            tk.Label(f, text=t["ip"], bg=COLORS["sidebar"], fg=COLORS["text3"],
                     font=("Segoe UI", 8)).pack(side="left")

    def start_simulation(self):
        if not self.targets:
            messagebox.showwarning("No targets", "Add at least one target first.")
            return
        self.running = True
        self.stats   = {"sent": 0, "dropped": 0, "total_rtt": 0.0, "count": 0}
        self.log_entries = []
        self.lbl_status.config(text="Running", bg=COLORS["tag_ok"], fg=COLORS["success"])
        self.btn_start.config(state="disabled")
        self.btn_stop.config(state="normal")

        if self.var_log_en.get():
            os.makedirs(self.var_log_path.get(), exist_ok=True)
            date_str = datetime.date.today().isoformat()
            ext = self.var_log_fmt.get().lower()
            self.log_file_path = os.path.join(self.var_log_path.get(), f"{date_str}.{ext}")
            self.lbl_logpath.config(text=f"Logging → {self.log_file_path}")
        else:
            self.log_file_path = None
            self.lbl_logpath.config(text="Logging disabled")

        for t in self.targets:
            self._spawn_worker(t)

        self.update_graph_loop()

    def _spawn_worker(self, t):
        th = threading.Thread(target=self.worker, args=(t,), daemon=True)
        self.worker_threads.append(th)
        th.start()

    def stop_simulation(self):
        self.running = False
        self.lbl_status.config(text="Stopped", bg=COLORS["tag_dr"], fg=COLORS["danger"])
        self.btn_start.config(state="normal")
        self.btn_stop.config(state="disabled")

    def worker(self, target):
        """Background thread per target."""
        while self.running:
            delay  = self.var_delay.get()
            jitter = self.var_jitter.get()
            loss   = self.var_loss.get()
            proto  = target["protocol"]
            ip     = target["ip"]
            port   = target["port"]

            # Apply spike
            if self.spike_active and time.time() < self.spike_end_time:
                delay = self.var_spike_to.get()
                jitter = 0
            elif self.spike_active and time.time() >= self.spike_end_time:
                self.spike_active = False

            # Packet loss simulation
            if random.random() * 100 < loss:
                status = "drop"
                rtt    = None
                extra  = f"packet dropped (loss rule {loss}%)"
            else:
                # Simulated delay
                sim_delay = delay + random.randint(-jitter, jitter) if jitter > 0 else delay
                sim_delay = max(0, sim_delay)

                # Actual ping
                t_start = time.time()
                if proto == "ICMP (ping)":
                    rtt = icmp_ping(ip, timeout=PING_TIMEOUT)
                elif proto == "TCP":
                    rtt = tcp_ping(ip, port, timeout=PING_TIMEOUT)
                else:
                    rtt = tcp_ping(ip, port, timeout=PING_TIMEOUT)

                # Add simulated delay on top
                time.sleep(sim_delay / 1000.0)

                if rtt is None:
                    # Host unreachable — use simulated value
                    rtt = sim_delay
                    status = "delay" if sim_delay > 100 else "ok"
                    extra  = f"{rtt:.0f}ms (simulated, host unreachable)"
                else:
                    rtt += sim_delay
                    if sim_delay > 100:
                        status = "delay"
                        extra  = f"{rtt:.0f}ms (delay+jitter +{sim_delay}ms)"
                    else:
                        status = "ok"
                        extra  = f"{rtt:.0f}ms"

            # Update target state
            target["last_ms"]     = f"{rtt:.0f}ms" if rtt else "DROP"
            target["last_status"] = status
            target["data"].append(rtt if rtt else 0)
            if len(target["data"]) > GRAPH_POINTS:
                target["data"].pop(0)

            # Queue log entry
            self.log_queue.put({
                "time":   datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3],
                "status": status,
                "target": ip,
                "msg":    f"→ {extra}",
                "rtt":    rtt,
            })

            # Update stats
            self.stats["sent"] += 1
            if status == "drop":
                self.stats["dropped"] += 1
            if rtt:
                self.stats["total_rtt"] += rtt
                self.stats["count"]     += 1

            # File logging
            if self.log_file_path and rtt is not None:
                self._write_log_entry(ip, status, rtt)

            time.sleep(1)

    def fire_spike(self):
        self.spike_active   = True
        self.spike_end_time = time.time() + self.var_spike_dur.get()
        self.log_queue.put({
            "time":   datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3],
            "status": "info",
            "target": "system",
            "msg":    f"→ Spike fired: {self.var_spike_to.get()}ms for {self.var_spike_dur.get()}s",
            "rtt":    None,
        })

    def _write_log_entry(self, ip, status, rtt):
        try:
            fmt = self.var_log_fmt.get()
            ts  = datetime.datetime.now().isoformat()
            if fmt == "CSV":
                write_header = not os.path.exists(self.log_file_path)
                with open(self.log_file_path, "a", newline="") as f:
                    w = csv.writer(f)
                    if write_header:
                        w.writerow(["timestamp", "target", "status", "rtt_ms"])
                    w.writerow([ts, ip, status, f"{rtt:.2f}"])
            elif fmt == "JSON":
                entry = {"timestamp": ts, "target": ip, "status": status, "rtt_ms": round(rtt, 2)}
                with open(self.log_file_path, "a") as f:
                    f.write(json.dumps(entry) + "\n")
            else:
                with open(self.log_file_path, "a") as f:
                    f.write(f"[{ts}] {ip} {status.upper()} {rtt:.0f}ms\n")
        except Exception:
            pass

    # ── Log Queue Consumer ────────────────────────────────────────────────────

    def poll_log_queue(self):
        try:
            while True:
                entry = self.log_queue.get_nowait()
                self._append_log(entry)
                self._update_stats()
                self._refresh_target_chips()
        except queue.Empty:
            pass
        self.after(150, self.poll_log_queue)

    def _append_log(self, e):
        self.log_text.configure(state="normal")

        tag_map = {"ok": "ok", "delay": "delay", "drop": "drop",
                   "info": "info", "saved": "saved", "tray": "tray"}
        tag = tag_map.get(e["status"], "msg")

        label_map = {"ok": " OK   ", "delay": "DELAY", "drop": "DROP ",
                     "info": "INFO ", "saved": "SAVED", "tray": "TRAY "}
        label = label_map.get(e["status"], e["status"].upper()[:5])

        self.log_text.insert("end", f"{e['time']}  ", "time")
        self.log_text.insert("end", f"[{label}]", tag)
        self.log_text.insert("end", f"  {e['target']:<16}", "target")
        self.log_text.insert("end", f"  {e['msg']}\n", "msg")

        # Trim
        lines = int(self.log_text.index("end-1c").split(".")[0])
        if lines > MAX_LOG_ROWS:
            self.log_text.delete("1.0", "2.0")

        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _update_stats(self):
        sent    = self.stats["sent"]
        dropped = self.stats["dropped"]
        count   = self.stats["count"]
        avg_rtt = (self.stats["total_rtt"] / count) if count else 0
        success = ((sent - dropped) / sent * 100) if sent else 0

        self.stat_labels["sent"].config(text=f"{sent:,}")
        self.stat_labels["dropped"].config(text=str(dropped))
        self.stat_labels["avg_rtt"].config(text=f"{avg_rtt:.0f} ms" if count else "-- ms")
        self.stat_labels["success"].config(text=f"{success:.1f}%")

    def clear_log(self):
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    def export_log(self, fmt):
        path = filedialog.asksaveasfilename(
            defaultextension=f".{fmt.lower()}",
            filetypes=[(f"{fmt} files", f"*.{fmt.lower()}"), ("All", "*.*")],
            initialfile=f"latency_export_{datetime.date.today()}.{fmt.lower()}")
        if not path:
            return
        content = self.log_text.get("1.0", "end")
        with open(path, "w") as f:
            f.write(content)
        messagebox.showinfo("Exported", f"Log saved to:\n{path}")

    # ── Graph ─────────────────────────────────────────────────────────────────

    def toggle_graph(self):
        self.graph_expanded = not self.graph_expanded
        if self.graph_expanded:
            self.graph_container.config(height=180)
            self.btn_expand.config(text="▼ Collapse")
        else:
            self.graph_container.config(height=52)
            self.btn_expand.config(text="▲ Expand")
        if GRAPH_AVAILABLE:
            self.after(50, self.graph_canvas.draw)

    def update_graph_loop(self):
        if not self.running:
            return
        if GRAPH_AVAILABLE and self.targets:
            self._style_ax()
            for t in self.targets:
                xs = list(range(len(t["data"])))
                ys = t["data"]
                self.ax.plot(xs, ys, color=t["color"], linewidth=1.2, alpha=0.9)
            self.graph_canvas.draw()
        self.after(1500, self.update_graph_loop)

    # ── About Dialog ──────────────────────────────────────────────────────────

    def show_about(self):
        win = tk.Toplevel(self)
        win.title("About")
        win.geometry("320x380")
        win.resizable(False, False)
        win.configure(bg=COLORS["bg"])
        win.grab_set()

        # Center on parent
        self.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() - 320) // 2
        y = self.winfo_y() + (self.winfo_height() - 380) // 2
        win.geometry(f"+{x}+{y}")

        card = tk.Frame(win, bg=COLORS["card"], padx=30, pady=24)
        card.pack(fill="both", expand=True, padx=20, pady=20)

        # Icon
        ic = tk.Canvas(card, width=64, height=64, bg=COLORS["card"],
                       highlightthickness=0)
        ic.pack(pady=(0, 12))
        # Blue rounded square background
        ic.create_rectangle(4, 4, 60, 60, fill=COLORS["accent"], outline="", width=0)
        self._draw_icon(ic, 32, 32, 24)

        tk.Label(card, text=APP_NAME, bg=COLORS["card"], fg=COLORS["text"],
                 font=("Segoe UI", 13, "bold")).pack()
        tk.Label(card, text="Network testing & simulation tool",
                 bg=COLORS["card"], fg=COLORS["text3"], font=("Segoe UI", 9)).pack(pady=(2, 0))

        tk.Frame(card, bg=COLORS["border"], height=1).pack(fill="x", pady=14)

        tk.Label(card, text=AUTHOR, bg=COLORS["card"], fg=COLORS["text"],
                 font=("Segoe UI", 12, "bold")).pack()
        tk.Label(card, text="Network & Lab Administrator",
                 bg=COLORS["card"], fg=COLORS["text2"], font=("Segoe UI", 9)).pack(pady=2)
        tk.Label(card, text=COLLEGE,
                 bg=COLORS["card"], fg=COLORS["text2"], font=("Segoe UI", 9)).pack()
        tk.Label(card, text=CITY,
                 bg=COLORS["card"], fg=COLORS["text3"], font=("Segoe UI", 9)).pack()

        tk.Frame(card, bg=COLORS["border"], height=1).pack(fill="x", pady=14)

        tk.Label(card, text=f"Version {APP_VERSION}  ·  © {YEAR} {AUTHOR}",
                 bg=COLORS["card"], fg=COLORS["text3"], font=("Segoe UI", 8)).pack()
        tk.Label(card, text="Built with Python & tkinter",
                 bg=COLORS["card"], fg=COLORS["text3"], font=("Segoe UI", 8)).pack(pady=2)

        tk.Button(card, text="Close", bg=COLORS["accent"], fg="white",
                  font=("Segoe UI", 10, "bold"), relief="flat", bd=0,
                  padx=24, pady=6, cursor="hand2",
                  command=win.destroy).pack(pady=(10, 0))

    # ── Window close ─────────────────────────────────────────────────────────

    def on_close(self):
        self.running = False
        self.destroy()


# ─── Entry Point ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = LatencySimulator()
    app.mainloop()
