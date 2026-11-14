# PLEASE READ THE FOLLOWING TEXT UNDER THIS!!!

# INSTRUCTIONS, PLEASE READ!!!: PYTHON REQUIREMENTS: INSTALL THEM USING "python -m pip install numpy psutil pygame moderngl windows-capture pywin32"
# CONFIGURATION: hold Windows key and then while holding the windows key press I, or search up settings... AFTER THAT, once your in settings, go to Display -> Graphics -> Advanced graphics settings and DISABLE the following "Hardware-accelerated GPU scheduling" After doing this, restart your computer
# go to https://github.com/blurbusters/crt-beam-simulator/blob/main/crt-simulator.glsl and click the download button, then rename the downloaded crt-simulator.glsl file to "shader.glsl" and put it in the same folder that you are running this python script (BFI.py) from
# Then set splitscreen is set to 0, EXAMPLE: set #define SPLITSCREEN     0 
# END OF EXAMPLE
# Then make sure motion_speed is set to 0.0 EXAMPLE: #define MOTION_SPEED    0.0
# END OF EXAMPLE
# Finally, you can now configure the GLSL shader however you like!

# -*- coding: utf-8 -*-
"""
Ultimate Rolling Scan & Global BFI Motion Clarity Engine (File-Backed Sanitizer Edition)
======================================================================================
"""
import os
import sys
import math
import time
import json
import ctypes
import threading
import subprocess
from ctypes import wintypes

if sys.platform != "win32":
    sys.exit("This tool is Windows-only.")

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

import numpy as np
import psutil
import pygame
import moderngl
import tkinter as tk
from tkinter import ttk
from windows_capture import WindowsCapture, Frame, InternalCaptureControl

tk.Variable.__del__ = lambda self: None

user32 = ctypes.windll.user32
user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.GetWindowLongW.restype = ctypes.c_long
user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
user32.SetWindowLongW.restype = ctypes.c_long
user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                ctypes.c_int, ctypes.c_int, wintypes.UINT]
user32.SetLayeredWindowAttributes.argtypes = [wintypes.HWND, ctypes.c_ulong, ctypes.c_ubyte, ctypes.c_ulong]
user32.SetWindowDisplayAffinity.argtypes = [wintypes.HWND, ctypes.c_ulong]
user32.SetWindowDisplayAffinity.restype = ctypes.c_bool
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
user32.GetAsyncKeyState.restype = ctypes.c_short

gdi32 = ctypes.windll.gdi32
user32.GetDC.argtypes = [wintypes.HWND]
user32.GetDC.restype = wintypes.HDC
user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
gdi32.GetDeviceCaps.argtypes = [wintypes.HDC, ctypes.c_int]

shell32 = ctypes.windll.shell32
shell32.ShellExecuteW.argtypes = [wintypes.HWND, ctypes.c_wchar_p, ctypes.c_wchar_p,
                                 ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_int]
shell32.ShellExecuteW.restype = ctypes.c_void_p

dwmapi = ctypes.windll.dwmapi
dwmapi.DwmFlush.restype = ctypes.c_long

def get_config_path():
    base_dir = os.environ.get("APPDATA", os.path.expanduser("~"))
    app_dir = os.path.join(base_dir, "UltimateRollingBFI_WGC")
    try:
        os.makedirs(app_dir, exist_ok=True)
    except Exception:
        pass
    return os.path.join(app_dir, "config.json")

def load_persistent_config():
    path = get_config_path()
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_persistent_config(state_dict):
    path = get_config_path()
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(state_dict, f, indent=4)
    except Exception:
        pass

def is_admin():
    try:
        return bool(shell32.IsUserAnAdmin())
    except Exception:
        return False

def set_swap_interval(n):
    try:
        gl = ctypes.windll.opengl32
        gl.wglGetProcAddress.restype = ctypes.c_void_p
        gl.wglGetProcAddress.argtypes = [wintypes.c_char_p]
        addr = gl.wglGetProcAddress(b"wglSwapIntervalEXT")
        if addr:
            fn = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_int)(addr)
            return bool(fn(int(n)))
    except Exception:
        pass
    return False

_THREAD_PRIORITY = {"Normal": 0, "Above Normal": 1, "High": 2, "Time Critical": 15}
_PROCESS_PRIORITY = {
    "Normal": psutil.NORMAL_PRIORITY_CLASS,
    "Above Normal": psutil.ABOVE_NORMAL_PRIORITY_CLASS,
    "High": psutil.HIGH_PRIORITY_CLASS,
    "Realtime": psutil.REALTIME_PRIORITY_CLASS,
}

def _set_thread_priority(level_name):
    try:
        k32 = ctypes.windll.kernel32
        h = k32.GetCurrentThread()
        return bool(k32.SetThreadPriority(h, _THREAD_PRIORITY.get(level_name, 0)))
    except Exception:
        return False

def _set_process_priority(level_name):
    try:
        psutil.Process().nice(_PROCESS_PRIORITY[level_name])
        return True
    except Exception:
        return False

def _set_gpu_priority(level):
    try:
        gdi = ctypes.windll.gdi32
        gdi.D3DKMTSetProcessSchedulingPriorityClass.argtypes = [wintypes.HANDLE, ctypes.c_uint]
        gdi.D3DKMTSetProcessSchedulingPriorityClass.restype = ctypes.c_long
        import win32api
        h = win32api.OpenProcess(0x1F0FFF, False, os.getpid())
        r = gdi.D3DKMTSetProcessSchedulingPriorityClass(int(h), int(level))
        win32api.CloseHandle(h)
        return r == 0
    except Exception:
        return False

def apply_cpu_affinity(thread_obj, core_selection_str):
    if not core_selection_str or core_selection_str == "All Cores (Default)":
        return
    try:
        cpu_count = psutil.cpu_count(logical=True) or 1
        if "Core" in core_selection_str:
            import re
            m = re.findall(r'\d+', core_selection_str)
            if m:
                core_id = int(m[0]) % cpu_count
                mask = [core_id]
            else:
                return
        elif core_selection_str == "Even Cores Only":
            mask = [i for i in range(cpu_count) if i % 2 == 0]
        elif core_selection_str == "Odd Cores Only":
            mask = [i for i in range(cpu_count) if i % 2 != 0]
        else:
            return

        import win32process
        import win32api
        if thread_obj == threading.current_thread():
            h_thread = win32api.GetCurrentThread()
        else:
            return
        
        affinity_mask = sum(1 << c for c in mask)
        win32process.SetThreadAffinityMask(h_thread, affinity_mask)
    except Exception:
        pass

GWL_EXSTYLE = -20
WS_EX_TOPMOST = 0x00000008
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_LAYERED = 0x00080000
WS_EX_NOACTIVATE = 0x08000000
HWND_TOPMOST = wintypes.HWND(-1)
SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE, SWP_FRAMECHANGED = 0x1, 0x2, 0x10, 0x20
WDA_EXCLUDEFROMCAPTURE = 0x11
VK_HOME = 0x24

def keep_topmost(hwnd):
    if hwnd:
        user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)

def exclude_from_capture(hwnd):
    try:
        if hwnd:
            return bool(user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE))
    except Exception:
        pass
    return False

def make_click_through_overlay(hwnd):
    if not hwnd:
        return
    try:
        ex = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        ex |= WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE | WS_EX_TOPMOST
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex)
        user32.SetLayeredWindowAttributes(hwnd, 0, 255, 2)
        exclude_from_capture(hwnd)
        user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0,
                            SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_FRAMECHANGED)
    except Exception:
        pass

CAPTURES = ["windows-capture (WGC)"]
FPS_MODES = ["VSync (match display refresh)", "Uncapped"]
CPU_AFFINITY_OPTIONS = ["All Cores (Default)", "Core 0", "Core 1", "Even Cores Only", "Odd Cores Only"]
GPU_DEVICE_OPTIONS = ["Default GPU (Primary)"]

class State:
    def __init__(self):
        self.active = True
        self.quit = False
        self.fps = 0.0
        self.capture_kind = "windows-capture"
        self.fps_mode = FPS_MODES[0]
        self.fps_cap = 60
        self.admin = is_admin()
        
        if self.admin:
            self.proc_priority = "Realtime"
            self.render_thread_priority = "Time Critical"
            self.capture_thread_priority = "Time Critical"
            self.gpu_priority = 3
        else:
            self.proc_priority = "High"
            self.render_thread_priority = "Time Critical"
            self.capture_thread_priority = "High"
            self.gpu_priority = 2

        self.apply_priorities_flag = True
        self.bfi_status = False
        self.capture_cpu_affinity = "All Cores (Default)"
        self.render_cpu_affinity = "All Cores (Default)"
        self.gpu_device_preference = "Default GPU (Primary)"

        self.load_settings()

    def save_settings(self):
        data = {
            "active": self.active,
            "fps_mode": self.fps_mode,
            "fps_cap": self.fps_cap,
            "proc_priority": self.proc_priority,
            "render_thread_priority": self.render_thread_priority,
            "capture_thread_priority": self.capture_thread_priority,
            "gpu_priority": self.gpu_priority,
            "bfi_status": self.bfi_status,
            "capture_cpu_affinity": self.capture_cpu_affinity,
            "render_cpu_affinity": self.render_cpu_affinity,
            "gpu_device_preference": self.gpu_device_preference,
        }
        save_persistent_config(data)

    def load_settings(self):
        data = load_persistent_config()
        if not data:
            return
        for key, val in data.items():
            if hasattr(self, key):
                setattr(self, key, val)

VERT = """
#version 330
in vec2 in_pos;
out vec2 v_uv;
void main(){
    v_uv = vec2(in_pos.x * 0.5 + 0.5, 0.5 - in_pos.y * 0.5);
    gl_Position = vec4(in_pos, 0.0, 1.0);
}
"""

FRAG_SHADER_WRAPPER = """
uniform int bfiStatus;
in vec2 v_uv;
out vec4 outc;

void mainImage(out vec4 fragColor, in vec2 fragCoord);

void main() {
    vec2 fragCoord = v_uv * iResolution.xy;
    vec4 col = vec4(0.0);
    mainImage(col, fragCoord);
    
    if (bfiStatus == 1 && fragCoord.x < 24.0 && fragCoord.y < 24.0) {
        col.rgb = vec3(0.1, 1.0, 0.2);
    }
    outc = vec4(clamp(col.rgb, 0.0, 1.0), 1.0);
}
"""

def sanitize_shader(code_str):
    # Automatically convert smart quotes to standard quotes and strip hidden artifacts
    cleaned = code_str.replace('“', '"').replace('”', '"').replace('‘', "'").replace('’', "'")
    cleaned = cleaned.replace('\u00A0', ' ')
    cleaned = cleaned.replace('\u200b', '')
    cleaned = cleaned.replace('\ufeff', '')
    return "".join(ch if (ord(ch) < 128 or ch in '\n\r\t ') else ' ' for ch in cleaned)

# Load verbatim shader code dynamically from external file and inject NOT_SHADERTOY
shader_file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shader.glsl")
if os.path.exists(shader_file_path):
    with open(shader_file_path, "r", encoding="utf-8", errors="ignore") as f:
        raw_shader_code = f.read()
else:
    sys.exit("Error: 'shader.glsl' not found in script directory! Please place your verbatim shader code inside shader.glsl.")

# Prepend #define NOT_SHADERTOY automatically and sanitize the rest
VERBATIM_FRAGMENT_SHADER = (
    "#version 330 core\n"
    "#define NOT_SHADERTOY\n"
    + sanitize_shader(raw_shader_code) 
    + "\n" 
    + sanitize_shader(FRAG_SHADER_WRAPPER)
)

class WgcBackend:
    kind = "windows-capture"
    def __init__(self):
        self.latest = None
        self.width = user32.GetSystemMetrics(0)
        self.height = user32.GetSystemMetrics(1)
        self.lock = threading.Lock()
        
        self.capturer = WindowsCapture(
            cursor_capture=False,
            draw_border=False,
            monitor_index=1
        )
        
        @self.capturer.event
        def on_frame_arrived(frame: Frame, capture_control: InternalCaptureControl):
            try:
                buffer = frame.frame_buffer
                w = frame.width
                h = frame.height
                if buffer is not None:
                    with self.lock:
                        self.latest = (buffer, w, h)
            except Exception:
                pass

        @self.capturer.event
        def on_closed():
            pass

        self._thread = threading.Thread(target=self.capturer.start, daemon=True)
        self._thread.start()

    def grab(self):
        with self.lock:
            return self.latest

    def close(self):
        try:
            self.capturer.stop()
        except Exception:
            pass

class Grabber:
    def __init__(self, mode="Auto", S=None):
        self.kind = "windows-capture"
        self.paused = False
        self.backend = WgcBackend()

    def set_mode(self, mode):
        pass

    def grab(self):
        if self.paused:
            return None
        return self.backend.grab()

class MenuThread(threading.Thread):
    def __init__(self, S):
        super().__init__(daemon=True)
        self.S = S

    def run(self):
        S = self.S
        root = tk.Tk()
        root.title("Shadertoy Verbatim WGC Panel")
        root.geometry("+40+40")
        root.resizable(False, False)
        root.attributes("-topmost", True)
        pad = dict(padx=8, pady=2)

        outer = ttk.Frame(root, padding=8)
        outer.grid(sticky="nsew")
        nb = ttk.Notebook(outer)
        nb.grid(row=0, column=0, sticky="nsew")
        tab_bfi = ttk.Frame(nb, padding=4)
        tab_pri = ttk.Frame(nb, padding=4)
        nb.add(tab_bfi, text="Shader Controls")
        nb.add(tab_pri, text="Priority & Affinity")

        PROC_LEVELS = ["Normal", "Above Normal", "High", "Realtime"]
        THREAD_LEVELS = ["Normal", "Above Normal", "High", "Time Critical"]
        GPU_LEVELS = ["Normal (0)", "Above Normal (1)", "High (2)", "Realtime (3)"]

        def _pri_combo(parent, row, label, values, attr, transform=None):
            ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", **pad)
            cur = getattr(S, attr)
            display_cur = transform(cur) if transform else cur
            var = tk.StringVar(root, value=display_cur)
            cb = ttk.Combobox(parent, textvariable=var, values=values, state="readonly", width=24)
            cb.grid(row=row, column=1, sticky="we", **pad)
            def on_pick(v, a=attr, tr=transform):
                if tr:
                    import re
                    m = re.search(r"\((\d+)\)", v)
                    setattr(S, a, int(m.group(1)) if m else 0)
                else:
                    setattr(S, a, v)
                S.apply_priorities_flag = True
                S.save_settings()
            cb.bind("<<ComboboxSelected>>", lambda e, op=on_pick, v=var: op(v.get()))

        _pri_combo(tab_pri, 1, "Process Priority Class", PROC_LEVELS, "proc_priority")
        _pri_combo(tab_pri, 2, "Render Thread Priority", THREAD_LEVELS, "render_thread_priority")
        _pri_combo(tab_pri, 3, "GPU Scheduling Priority", GPU_LEVELS, "gpu_priority",
                    transform=lambda v: GPU_LEVELS[min(int(v), 3)])

        _pri_combo(tab_pri, 4, "Capture Thread CPU Core", CPU_AFFINITY_OPTIONS, "capture_cpu_affinity")
        _pri_combo(tab_pri, 5, "Render Thread CPU Core", CPU_AFFINITY_OPTIONS, "render_cpu_affinity")
        _pri_combo(tab_pri, 6, "GPU Device Preference", GPU_DEVICE_OPTIONS, "gpu_device_preference")

        def add_check(parent, row, label, attr):
            var = tk.BooleanVar(root, value=bool(getattr(S, attr)))
            def on_toggle():
                setattr(S, attr, bool(var.get()))
                S.save_settings()
            ttk.Checkbutton(parent, text=label, variable=var,
                            command=on_toggle
                            ).grid(row=row, column=0, columnspan=3, sticky="w", **pad)

        add_check(tab_bfi, 0, "Show Status Indicator (Green Square in Corner)", "bfi_status")

        bottom = ttk.Frame(outer)
        bottom.grid(row=1, column=0, sticky="we", pady=(6, 0))
        
        toggle_btn = ttk.Button(bottom)
        def refresh_toggle_btn():
            toggle_btn.config(text="Deactivate Shader" if S.active else "Activate Shader")
        refresh_toggle_btn()

        def toggle_active():
            S.active = not S.active
            refresh_toggle_btn()
            S.save_settings()

        toggle_btn.config(command=toggle_active)
        toggle_btn.grid(row=0, column=0, sticky="we", **pad)
        ttk.Button(bottom, text="Quit", command=lambda: setattr(S, "quit", True)).grid(row=0, column=1, sticky="we", **pad)

        status = ttk.Label(bottom, text="", foreground="#555", wraplength=400, justify="left")
        status.grid(row=1, column=0, columnspan=2, sticky="w", **pad)

        down = False
        def poll():
            nonlocal down
            if S.quit:
                try: root.destroy()
                except: pass
                return
            try:
                k = bool(user32.GetAsyncKeyState(VK_HOME) & 0x8000)
                if k and not down:
                    if root.winfo_viewable(): root.withdraw()
                    else: root.deiconify()
                down = k
                if root.winfo_viewable():
                    status.config(text="FPS: %.1f | windows-capture Active" % S.fps)
                    refresh_toggle_btn()
            except Exception:
                pass
            root.after(40, poll)

        root.after(40, poll)
        root.mainloop()
        S.quit = True

def main():
    W = user32.GetSystemMetrics(0)
    H = user32.GetSystemMetrics(1)
    S = State()

    try:
        ctypes.windll.winmm.timeBeginPeriod(1)
    except Exception:
        pass

    MenuThread(S).start()
    grab = Grabber(S=S)

    pygame.init()
    pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MAJOR_VERSION, 3)
    pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MINOR_VERSION, 3)
    pygame.display.gl_set_attribute(pygame.GL_CONTEXT_PROFILE_MASK, pygame.GL_CONTEXT_PROFILE_CORE)
    flags = pygame.OPENGL | pygame.DOUBLEBUF | pygame.NOFRAME
    
    pygame.display.set_mode((W, H), flags, vsync=1)
    pygame.display.set_caption("Shadertoy Verbatim windows-capture BFI Engine")
    
    hwnd = None
    try:
        wm_info = pygame.display.get_wm_info()
        hwnd = wm_info.get("window", None)
    except Exception:
        pass

    if hwnd:
        make_click_through_overlay(hwnd)
        user32.ShowWindow(hwnd, 0)

    ctx = moderngl.create_context()
    prog_bfi = ctx.program(vertex_shader=VERT, fragment_shader=VERBATIM_FRAGMENT_SHADER)
    vbo = ctx.buffer(np.array([-1, -1, 1, -1, -1, 1, 1, 1], dtype="f4").tobytes())
    vao_bfi = ctx.vertex_array(prog_bfi, [(vbo, "2f", "in_pos")])

    def setu(prog, name, val):
        if name in prog:
            prog[name].value = val

    screen_tex = None
    clock = pygame.time.Clock()
    frame = 0
    shown = False
    shader_t0 = time.perf_counter()

    while not S.quit:
        if S.apply_priorities_flag:
            S.apply_priorities_flag = False
            _set_process_priority(S.proc_priority)
            _set_thread_priority(S.render_thread_priority)
            _set_gpu_priority(S.gpu_priority)
            apply_cpu_affinity(threading.current_thread(), S.render_cpu_affinity)

        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                S.quit = True

        want = S.active
        grab.paused = not want

        if not want:
            if shown and hwnd:
                user32.ShowWindow(hwnd, 0)
                shown = False
            clock.tick(20)
            continue

        set_swap_interval(1)
        clock.tick(0)
        S.fps = clock.get_fps()

        r = grab.grab()
        if r is not None:
            data, fw, fh = r
            if screen_tex is None or screen_tex.size != (fw, fh):
                screen_tex = ctx.texture((fw, fh), 4, dtype="f1")
                screen_tex.swizzle = "BGRA"
                screen_tex.filter = (moderngl.LINEAR, moderngl.LINEAR)
            if data is not None:
                screen_tex.write(data, alignment=1)

        if screen_tex is None:
            continue

        if not shown and hwnd:
            user32.ShowWindow(hwnd, 4)
            keep_topmost(hwnd)
            shown = True

        frame += 1
        time_sec = float(time.perf_counter() - shader_t0)

        ctx.screen.use()
        ctx.viewport = (0, 0, W, H)
        screen_tex.use(0)

        setu(prog_bfi, "iChannel0", 0)
        setu(prog_bfi, "iResolution", (float(W), float(H), 1.0))
        setu(prog_bfi, "iTime", time_sec)
        setu(prog_bfi, "iFrame", frame)
        setu(prog_bfi, "bfiStatus", int(S.bfi_status))

        vao_bfi.render(moderngl.TRIANGLE_STRIP)

        pygame.display.flip()
        
        try:
            dwmapi.DwmFlush()
        except Exception:
            pass

        ctx.finish()

    grab.backend.close()
    S.quit = True
    pygame.quit()

if __name__ == "__main__":
    main()