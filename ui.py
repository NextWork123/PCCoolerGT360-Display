#!/usr/bin/env python3
"""PCCooler GT360 — PyWebview UI."""

import os
import sys

# Qt WebEngine flags before any Qt/webview import (Linux) to avoid crashes/blank window
if sys.platform == "linux":
    os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--no-sandbox")
    # Force pywebview to use PyQt6 (PyQt5 may be missing QtWebChannel on some systems)
    os.environ.setdefault("QT_API", "pyqt6")

import json
import subprocess
import threading
import webview
from example import main as example_main

# Global stop event for keep-alive and loops
stop_event = threading.Event()
worker_thread = None
# Current privileged helper process (Unix); stop() terminates it
_helper_process = None

def _run_privileged_helper(kwargs_serializable, stop_event):
    """Run example_main in a privileged subprocess (Unix). Returns (success, message)."""
    global _helper_process
    project_dir = os.path.dirname(os.path.abspath(__file__))
    helper_path = os.path.join(project_dir, "privileged_helper.py")
    sudo_cmd = os.environ.get("PCCOOLER_SUDO", "sudo")
    cmd = [sudo_cmd, sys.executable, helper_path]
    try:
        _helper_process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=project_dir,
        )
        _helper_process.stdin.write(json.dumps(kwargs_serializable).encode("utf-8"))
        _helper_process.stdin.close()
        while True:
            if _helper_process.poll() is not None:
                returncode = _helper_process.returncode
                break
            if stop_event.is_set():
                _helper_process.terminate()
                try:
                    _helper_process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    _helper_process.kill()
                return True, "Stopped"
            stop_event.wait(timeout=0.5)
        out = _helper_process.stdout.read() if _helper_process.stdout else b""
        err = _helper_process.stderr.read() if _helper_process.stderr else b""
    except Exception as e:
        return False, str(e)
    finally:
        _helper_process = None
    err_text = err.decode("utf-8", errors="replace").strip() if err else ""
    if returncode != 0:
        return False, err_text or f"Exit code {returncode}"
    return True, "Done"

class Api:
    def __init__(self):
        self._window = None

    def set_window(self, window):
        self._window = window

    def run(self, options):
        global stop_event, worker_thread
        
        # Stop any existing worker
        stop_event.set()
        if worker_thread and worker_thread.is_alive():
            worker_thread.join(timeout=2.0)
        
        stop_event = threading.Event()
        
        # Map JS options to Python kwargs
        kwargs = {
            "image": options.get("image"),
            "pattern": options.get("pattern"),
            "system": options.get("system", False),
            "screensaver": options.get("screensaver") or None,
            "screensaver_quality": int(options.get("screensaver_quality", 60)),
            "screensaver_scale": float(options.get("screensaver_scale", 1.0)),
            "wakeup": options.get("wakeup", False),
            "sleep": options.get("sleep", False),
            "recovery": options.get("recovery", False),
            "init": options.get("init", False),
            "reset": options.get("reset", False),
            "resolution": options.get("resolution", "640x480"),
            "format": options.get("format", "png"),
            "loop": options.get("loop", False),
            "chunk_delay": float(options.get("chunk_delay", 0.001)),
            "max_retries": int(options.get("max_retries", 10)),
            "verbose": False,
            "stop_event": stop_event,
            "brightness": options.get("brightness"),
            "orientation": options.get("orientation"),
        }
        
        # Auto-convert format to MP4 for animated GIFs
        image_path = kwargs.get("image", "")
        if image_path and image_path.lower().endswith(".gif"):
            kwargs["format"] = "mp4"
        
        timeout = options.get("timeout")
        if timeout is not None and str(timeout).strip() != "":
            kwargs["timeout"] = int(timeout)
        else:
            kwargs["timeout"] = None

        def worker():
            use_helper = hasattr(os, "geteuid") and sys.platform != "win32"
            if use_helper:
                # Run USB operations in a privileged subprocess (sudo)
                kwargs_serializable = {k: v for k, v in kwargs.items() if k != "stop_event"}
                try:
                    ok, msg = _run_privileged_helper(kwargs_serializable, stop_event)
                    if self._window:
                        # Escape for JS double-quoted string: \ " and newlines
                        safe_msg = msg.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")
                        self._window.evaluate_js(f'window.__runComplete({"true" if ok else "false"}, "{safe_msg}")')
                except Exception as e:
                    print(f"Error in worker: {e}")
                    if self._window:
                        msg = str(e).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")
                        self._window.evaluate_js(f'window.__runComplete(false, "{msg}")')
            else:
                try:
                    example_main(**kwargs)
                    if self._window:
                        self._window.evaluate_js('window.__runComplete(true, "Done")')
                except Exception as e:
                    print(f"Error in worker: {e}")
                    if self._window:
                        msg = str(e).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")
                        self._window.evaluate_js(f'window.__runComplete(false, "{msg}")')

        worker_thread = threading.Thread(target=worker, daemon=True)
        worker_thread.start()

    def choose_file(self):
        if not self._window:
            return None
        
        file_types = ('Image or video (*.png;*.jpg;*.jpeg;*.gif;*.bmp;*.mp4)', 'All files (*.*)')
        result = self._window.create_file_dialog(webview.OPEN_DIALOG, file_types=file_types)
        
        if result and len(result) > 0:
            return result[0]
        return None

    def stop(self):
        global stop_event
        stop_event.set()
        if self._window:
            self._window.evaluate_js('window.__runComplete(true, "Stopped")')

HTML = '''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>PCCooler GT360</title>
  <style>
    /* ========================================
       Windows 11 Fluent Design System
       PCCooler GT360 UI - Fixed Version
       ======================================== */
    
    :root {
      --surface: #f3f3f3;
      --card: #ffffff;
      --card-elevated: #fafafa;
      --border: #e5e5e5;
      --border-strong: #d1d1d1;
      --text-primary: #1a1a1a;
      --text-secondary: #5f5f5f;
      --text-disabled: #a0a0a0;
      --accent: #0078d4;
      --accent-hover: #006cbe;
      --accent-active: #005ba1;
      --accent-light: #e5f2ff;
      --success: #0f7b0f;
      --warning: #9c5b00;
      --error: #c50f1f;
      --info: #0078d4;
      --font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
      --radius-sm: 4px;
      --radius-md: 6px;
      --radius-lg: 8px;
      --shadow-1: 0 1px 2px rgba(0,0,0,0.1);
      --shadow-2: 0 2px 4px rgba(0,0,0,0.1);
    }
    
    [data-theme="dark"] {
      --surface: #202020;
      --card: #2c2c2c;
      --card-elevated: #333333;
      --border: #3d3d3d;
      --border-strong: #4d4d4d;
      --text-primary: #ffffff;
      --text-secondary: #a0a0a0;
      --text-disabled: #6e6e6e;
      --accent: #4cc2ff;
      --accent-hover: #3db8f7;
      --accent-active: #2faeea;
      --accent-light: rgba(76, 194, 255, 0.15);
      --success: #54b054;
      --error: #e05e6a;
    }
    
    @media (prefers-color-scheme: dark) {
      :root:not([data-theme="light"]) {
        --surface: #202020;
        --card: #2c2c2c;
        --border: #3d3d3d;
        --text-primary: #ffffff;
        --text-secondary: #a0a0a0;
        --accent: #4cc2ff;
      }
    }
    
    * { box-sizing: border-box; margin: 0; padding: 0; }
    
    body {
      font-family: var(--font-family);
      font-size: 14px;
      line-height: 1.5;
      background: var(--surface);
      color: var(--text-primary);
      min-height: 100vh;
      padding: 16px;
      padding-bottom: 60px;
    }
    
    /* Scrollbar */
    ::-webkit-scrollbar { width: 8px; }
    ::-webkit-scrollbar-track { background: var(--surface); }
    ::-webkit-scrollbar-thumb { background: var(--border-strong); border-radius: 4px; }
    ::-webkit-scrollbar-thumb:hover { background: var(--text-secondary); }
    
    .app-container { max-width: 680px; margin: 0 auto; }
    
    /* Section Cards */
    .section {
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: var(--radius-lg);
      padding: 16px;
      margin-bottom: 16px;
    }
    
    .section-title {
      font-size: 16px;
      font-weight: 600;
      margin-bottom: 16px;
      display: flex;
      align-items: center;
      gap: 8px;
    }
    
    /* InfoBar */
    .infobar {
      display: none;
      align-items: center;
      gap: 12px;
      padding: 12px 16px;
      border-radius: var(--radius-md);
      margin-bottom: 16px;
      animation: slideIn 0.2s ease;
    }
    
    .infobar.show { display: flex; }
    .infobar.info { background: var(--accent-light); border: 1px solid var(--accent); }
    .infobar.success { background: rgba(15, 123, 15, 0.1); border: 1px solid var(--success); }
    .infobar.error { background: rgba(197, 15, 31, 0.1); border: 1px solid var(--error); }
    .infobar.running { background: rgba(0, 120, 212, 0.1); border: 1px solid var(--accent); }
    
    @keyframes slideIn {
      from { opacity: 0; transform: translateY(-10px); }
      to { opacity: 1; transform: translateY(0); }
    }
    
    /* Source Tabs */
    .source-tabs {
      display: flex;
      gap: 4px;
      background: var(--surface);
      padding: 4px;
      border-radius: var(--radius-md);
      margin-bottom: 16px;
    }
    
    .source-tab {
      flex: 1;
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 4px;
      padding: 10px;
      border: none;
      border-radius: var(--radius-sm);
      background: transparent;
      color: var(--text-secondary);
      font-size: 12px;
      cursor: pointer;
      transition: all 0.15s ease;
    }
    
    .source-tab:hover { background: var(--card-elevated); color: var(--text-primary); }
    .source-tab.active { background: var(--accent); color: white; }
    .source-tab .icon { font-size: 20px; }
    
    /* Content Areas */
    .content-area { 
      display: none; 
      opacity: 0;
      transition: opacity 0.2s ease;
    }
    .content-area.active { 
      display: block; 
      opacity: 1;
    }
    
    @keyframes fadeIn {
      from { opacity: 0; }
      to { opacity: 1; }
    }
    
    /* File Input with Drag & Drop */
    .file-drop-zone {
      border: 2px dashed var(--border-strong);
      border-radius: var(--radius-md);
      padding: 24px;
      text-align: center;
      background: var(--surface);
      transition: all 0.2s ease;
      cursor: pointer;
    }
    
    .file-drop-zone:hover,
    .file-drop-zone.dragover {
      border-color: var(--accent);
      background: var(--accent-light);
    }
    
    .file-drop-zone .icon { font-size: 32px; margin-bottom: 8px; }
    .file-drop-zone .text { color: var(--text-secondary); font-size: 13px; }
    .file-drop-zone .filename {
      margin-top: 8px;
      font-weight: 500;
      color: var(--text-primary);
      word-break: break-all;
    }
    
    .file-input-row {
      display: flex;
      gap: 8px;
      margin-top: 12px;
    }
    
    .file-input {
      flex: 1;
      padding: 10px 12px;
      border: 1px solid var(--border);
      border-radius: var(--radius-md);
      background: var(--card);
      color: var(--text-primary);
      font-size: 14px;
    }
    
    .file-input:focus {
      outline: none;
      border-color: var(--accent);
      box-shadow: 0 0 0 2px var(--accent-light);
    }
    
    /* Buttons */
    .btn {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 6px;
      padding: 10px 16px;
      border: 1px solid var(--border);
      border-radius: var(--radius-md);
      background: var(--card);
      color: var(--text-primary);
      font-size: 14px;
      cursor: pointer;
      transition: all 0.15s ease;
    }
    
    .btn:hover { background: var(--card-elevated); border-color: var(--border-strong); }
    .btn:active { transform: scale(0.98); }
    .btn:disabled { opacity: 0.5; cursor: not-allowed; }
    
    .btn-primary {
      background: var(--accent);
      color: white;
      border-color: var(--accent);
      font-weight: 600;
    }
    .btn-primary:hover { background: var(--accent-hover); }
    
    .btn-danger { color: var(--error); border-color: var(--error); }
    .btn-danger:hover { background: rgba(197, 15, 31, 0.1); }
    
    /* Pattern Grid */
    .pattern-grid {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 12px;
      user-select: none;
    }
    
    .pattern-item {
      position: relative;
      aspect-ratio: 1;
      border-radius: var(--radius-md);
      border: 2px solid var(--border);
      cursor: pointer;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      gap: 6px;
      background: var(--surface);
      transition: all 0.15s ease;
      pointer-events: auto;
    }
    
    .pattern-item:hover { 
      transform: translateY(-2px); 
      box-shadow: var(--shadow-2); 
      border-color: var(--border-strong);
    }
    
    .pattern-item.selected { 
      border-color: var(--accent); 
      background: var(--accent-light);
    }
    
    .pattern-item.selected::after {
      content: "✓";
      position: absolute;
      top: -8px;
      right: -8px;
      width: 20px;
      height: 20px;
      background: var(--accent);
      color: white;
      border-radius: 50%;
      font-size: 12px;
      line-height: 20px;
      text-align: center;
      border: 2px solid var(--card);
    }
    
    .pattern-preview {
      width: 40px;
      height: 40px;
      border-radius: var(--radius-sm);
      border: 1px solid var(--border);
      pointer-events: none;
    }
    
    .pattern-label { 
      font-size: 11px; 
      color: var(--text-secondary);
      pointer-events: none;
    }
    
    .pattern-item.selected .pattern-label { 
      color: var(--accent); 
      font-weight: 600; 
    }
    
    /* Settings */
    .setting-row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 12px 0;
      border-bottom: 1px solid var(--border);
      gap: 16px;
    }
    .setting-row:last-child { border-bottom: none; }
    
    .setting-info { flex: 1; }
    .setting-label { font-weight: 600; font-size: 14px; }
    .setting-desc { font-size: 12px; color: var(--text-secondary); margin-top: 2px; }
    
    /* Toggle */
    .toggle {
      appearance: none;
      width: 44px;
      height: 22px;
      background: var(--border-strong);
      border-radius: 11px;
      position: relative;
      cursor: pointer;
      transition: background 0.2s;
      flex-shrink: 0;
    }
    
    .toggle::after {
      content: "";
      position: absolute;
      top: 2px;
      left: 2px;
      width: 18px;
      height: 18px;
      background: white;
      border-radius: 50%;
      transition: transform 0.2s;
      box-shadow: var(--shadow-1);
    }
    
    .toggle:checked { background: var(--accent); }
    .toggle:checked::after { transform: translateX(22px); }
    
    /* Select */
    .select {
      padding: 8px 32px 8px 12px;
      border: 1px solid var(--border);
      border-radius: var(--radius-md);
      background: var(--card);
      color: var(--text-primary);
      font-size: 14px;
      cursor: pointer;
      appearance: none;
      background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12'%3E%3Cpath fill='%23666' d='M2 4l4 4 4-4'/%3E%3C/svg%3E");
      background-repeat: no-repeat;
      background-position: right 10px center;
      min-width: 120px;
    }
    
    .select:focus { outline: none; border-color: var(--accent); }
    
    /* Slider */
    .slider-wrap {
      display: flex;
      align-items: center;
      gap: 12px;
      min-width: 150px;
    }
    
    .slider {
      flex: 1;
      height: 4px;
      appearance: none;
      background: var(--border);
      border-radius: 2px;
    }
    
    .slider::-webkit-slider-thumb {
      appearance: none;
      width: 16px;
      height: 16px;
      background: var(--accent);
      border-radius: 50%;
      cursor: pointer;
      border: 2px solid white;
    }
    
    .slider-val {
      min-width: 36px;
      text-align: right;
      font-weight: 600;
      font-size: 13px;
    }
    
    /* Number Input */
    .num-input {
      width: 70px;
      padding: 8px 10px;
      border: 1px solid var(--border);
      border-radius: var(--radius-md);
      background: var(--card);
      color: var(--text-primary);
      font-size: 14px;
      text-align: right;
    }
    
    .num-input:focus { outline: none; border-color: var(--accent); }
    
    /* Action Grid */
    .action-grid {
      display: grid;
      grid-template-columns: repeat(5, 1fr);
      gap: 8px;
    }
    
    .action-btn {
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 4px;
      padding: 12px 8px;
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: var(--radius-md);
      color: var(--text-primary);
      font-size: 11px;
      cursor: pointer;
      transition: all 0.15s ease;
    }
    
    .action-btn:hover {
      background: var(--card-elevated);
      border-color: var(--border-strong);
      transform: translateY(-1px);
    }
    
    .action-btn:active { transform: scale(0.98); }
    .action-btn:disabled { opacity: 0.5; cursor: not-allowed; }
    .action-btn .icon { font-size: 20px; }
    .action-btn .label { color: var(--text-secondary); }
    
    /* Action Area */
    .action-area {
      display: flex;
      gap: 12px;
    }
    
    .action-area .btn { flex: 1; height: 44px; font-size: 15px; }
    
    /* Status Bar */
    .status-bar {
      position: fixed;
      bottom: 0;
      left: 0;
      right: 0;
      height: 44px;
      background: var(--card);
      border-top: 1px solid var(--border);
      display: flex;
      align-items: center;
      padding: 0 16px;
      gap: 16px;
      font-size: 12px;
    }
    
    .status-dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: var(--success);
    }
    
    .status-dot.working {
      background: var(--accent);
      animation: pulse 1.5s infinite;
    }
    
    @keyframes pulse {
      0%, 100% { opacity: 1; }
      50% { opacity: 0.4; }
    }
    
    /* Theme Toggle */
    .theme-toggle {
      position: fixed;
      top: 16px;
      right: 16px;
      width: 36px;
      height: 36px;
      border-radius: var(--radius-md);
      border: 1px solid var(--border);
      background: var(--card);
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 18px;
      z-index: 100;
    }
    
    /* Responsive */
    @media (max-width: 600px) {
      .pattern-grid { grid-template-columns: repeat(2, 1fr); }
      .action-grid { grid-template-columns: repeat(3, 1fr); }
      body { padding: 12px; }
    }
  </style>
</head>
<body>
  <button class="theme-toggle" id="theme-toggle" title="Toggle theme">🌙</button>
  
  <div class="app-container">
    <!-- InfoBar -->
    <div id="infobar" class="infobar">
      <span id="infobar-icon">ℹ️</span>
      <span id="infobar-message"></span>
    </div>
    
    <!-- Source Selection -->
    <div class="section">
      <div class="section-title">📁 Source</div>
      
      <div class="source-tabs">
        <button class="source-tab active" data-source="image">
          <span class="icon">🖼️</span>
          <span>Image</span>
        </button>
        <button class="source-tab" data-source="pattern">
          <span class="icon">🎨</span>
          <span>Pattern</span>
        </button>
        <button class="source-tab" data-source="system">
          <span class="icon">🖥️</span>
          <span>System</span>
        </button>
        <button class="source-tab" data-source="screensaver">
          <span class="icon">✨</span>
          <span>Screensaver</span>
        </button>
      </div>
      
      <!-- Image Content -->
      <div class="content-area active" id="content-image">
        <div class="file-drop-zone" id="drop-zone">
          <div class="icon">📂</div>
          <div class="text">Drag & drop an image here, or click to browse</div>
          <div class="filename" id="selected-file"></div>
        </div>
        <div class="file-input-row">
          <input type="text" class="file-input" id="file-path" placeholder="Or enter file path...">
          <button class="btn" id="btn-browse">Browse</button>
        </div>
      </div>
      
      <!-- Pattern Content -->
      <div class="content-area" id="content-pattern">
        <div class="pattern-grid" id="pattern-grid">
          <div class="pattern-item selected" data-pattern="blue" style="position: relative;">
            <div class="pattern-preview" style="background: linear-gradient(135deg, #0078d4, #005a9e);"></div>
            <span class="pattern-label">Blue</span>
          </div>
          <div class="pattern-item" data-pattern="red" style="position: relative;">
            <div class="pattern-preview" style="background: linear-gradient(135deg, #e81123, #a80000);"></div>
            <span class="pattern-label">Red</span>
          </div>
          <div class="pattern-item" data-pattern="green" style="position: relative;">
            <div class="pattern-preview" style="background: linear-gradient(135deg, #107c10, #0b5c0b);"></div>
            <span class="pattern-label">Green</span>
          </div>
          <div class="pattern-item" data-pattern="white" style="position: relative;">
            <div class="pattern-preview" style="background: #ffffff; border: 1px solid var(--border);"></div>
            <span class="pattern-label">White</span>
          </div>
          <div class="pattern-item" data-pattern="black" style="position: relative;">
            <div class="pattern-preview" style="background: #1a1a1a;"></div>
            <span class="pattern-label">Black</span>
          </div>
          <div class="pattern-item" data-pattern="gradient" style="position: relative;">
            <div class="pattern-preview" style="background: linear-gradient(135deg, #ff0066, #6600ff);"></div>
            <span class="pattern-label">Gradient</span>
          </div>
          <div class="pattern-item" data-pattern="grid" style="position: relative;">
            <div class="pattern-preview" style="background: linear-gradient(#0078d4 1px, transparent 1px), linear-gradient(90deg, #0078d4 1px, transparent 1px); background-size: 8px 8px;"></div>
            <span class="pattern-label">Grid</span>
          </div>
          <div class="pattern-item" data-pattern="colors" style="position: relative;">
            <div class="pattern-preview" style="background: conic-gradient(from 0deg, #ff0000, #ffff00, #00ff00, #00ffff, #0000ff, #ff00ff, #ff0000);"></div>
            <span class="pattern-label">Colors</span>
          </div>
        </div>
      </div>
      
      <!-- System Content -->
      <div class="content-area" id="content-system">
        <div style="padding: 20px; text-align: center; color: var(--text-secondary);">
          <div style="font-size: 32px; margin-bottom: 8px;">🖥️</div>
          <div>Display real-time system information</div>
          <div style="font-size: 12px; margin-top: 4px;">CPU, GPU, and memory stats</div>
        </div>
      </div>
      
      <!-- Screensaver Content -->
      <div class="content-area" id="content-screensaver">
        <div class="setting-row" style="padding-top: 0;">
          <div class="setting-info">
            <div class="setting-label">Animation Type</div>
          </div>
          <select class="select" id="screensaver-type">
            <option value="bounce">Bounce (cat)</option>
            <option value="mystify">Mystify</option>
            <option value="starfield">Starfield</option>
            <option value="pipes">Pipes 3D</option>
            <option value="catpipes">Cat + Pipes</option>
          </select>
        </div>
        <div class="setting-row">
          <div class="setting-info">
            <div class="setting-label">JPEG Quality</div>
            <div class="setting-desc">Lower = smaller frames, more FPS</div>
          </div>
          <div class="slider-wrap">
            <input type="range" class="slider" id="screensaver-quality" min="20" max="95" value="60">
            <span class="slider-val" id="screensaver-quality-val">60</span>
          </div>
        </div>
        <div class="setting-row">
          <div class="setting-info">
            <div class="setting-label">Scale</div>
            <div class="setting-desc">Frame size multiplier</div>
          </div>
          <div class="slider-wrap">
            <input type="range" class="slider" id="screensaver-scale" min="0.25" max="1" step="0.25" value="1">
            <span class="slider-val" id="screensaver-scale-val">1</span>
          </div>
        </div>
        <div class="setting-row" style="border-bottom: none;">
          <div class="setting-info">
            <div class="setting-label">Max FPS</div>
            <div class="setting-desc">Limit frame rate (10-60)</div>
          </div>
          <div class="slider-wrap">
            <input type="range" class="slider" id="screensaver-fps" min="10" max="60" step="5" value="30">
            <span class="slider-val" id="screensaver-fps-val">30</span>
          </div>
        </div>
      </div>
    </div>
    
    <!-- Display Settings (Transfer Options) -->
    <div class="section">
      <div class="section-title">📺 Display Settings</div>
      
      <div class="setting-row">
        <div class="setting-info">
          <div class="setting-label">Resolution</div>
          <div class="setting-desc">Display output size</div>
        </div>
        <select class="select" id="resolution">
          <option value="640x480">640×480</option>
          <option value="480x320">480×320</option>
        </select>
      </div>
      
      <div class="setting-row">
        <div class="setting-info">
          <div class="setting-label">Format</div>
          <div class="setting-desc">Image encoding format</div>
        </div>
        <select class="select" id="format">
          <option value="png">PNG</option>
          <option value="jpeg">JPEG</option>
          <option value="bmp">BMP</option>
          <option value="gif">GIF</option>
          <option value="mp4">MP4</option>
        </select>
      </div>
      
      <div class="setting-row">
        <div class="setting-info">
          <div class="setting-label">Loop</div>
          <div class="setting-desc">Continuously send images</div>
        </div>
        <input type="checkbox" class="toggle" id="loop">
      </div>
      
      <div class="setting-row">
        <div class="setting-info">
          <div class="setting-label">Chunk Delay</div>
          <div class="setting-desc">Delay between chunks (seconds)</div>
        </div>
        <div class="slider-wrap">
          <input type="range" class="slider" id="chunk-delay" min="0" max="50" value="1">
          <span class="slider-val" id="chunk-delay-val">0.001</span>
        </div>
      </div>
      
      <div class="setting-row">
        <div class="setting-info">
          <div class="setting-label">Max Retries</div>
          <div class="setting-desc">Connection retry attempts</div>
        </div>
        <input type="number" class="num-input" id="max-retries" value="10" min="1" max="50">
      </div>
      
      <div class="setting-row" style="border-bottom: none;">
        <div class="setting-info">
          <div class="setting-label">Timeout</div>
          <div class="setting-desc">Display timeout (seconds)</div>
        </div>
        <input type="number" class="num-input" id="timeout" placeholder="∞" min="0">
      </div>
    </div>
    
    <!-- Hardware Settings (Device Control) -->
    <div class="section">
      <div class="section-title">🎚️ Hardware Settings</div>
      
      <!-- Brightness Control -->
      <div class="setting-row">
        <div class="setting-info">
          <div class="setting-label">Brightness</div>
          <div class="setting-desc">Screen backlight level</div>
        </div>
        <div class="slider-wrap">
          <input type="range" class="slider" id="brightness" min="0" max="100" value="100">
          <span class="slider-val" id="brightness-val">100</span>
          <button class="btn btn-primary" id="btn-brightness" style="margin-left: 8px; padding: 6px 12px; font-size: 12px;">Apply</button>
        </div>
      </div>
      
      <!-- Orientation Control -->
      <div class="setting-row" style="border-bottom: none;">
        <div class="setting-info">
          <div class="setting-label">Orientation</div>
          <div class="setting-desc">Screen rotation angle</div>
        </div>
        <div style="display: flex; align-items: center; gap: 8px;">
          <select class="select" id="orientation">
            <option value="0">0° (Normal)</option>
            <option value="90">90°</option>
            <option value="180">180°</option>
            <option value="270">270°</option>
          </select>
          <button class="btn btn-primary" id="btn-orientation" style="padding: 6px 12px; font-size: 12px;">Apply</button>
        </div>
      </div>
    </div>
    
    <!-- Quick Actions -->
    <div class="section">
      <div class="section-title">⚡ Quick Actions</div>
      <div class="action-grid">
        <button class="action-btn ctrl-btn" data-action="wakeup">
          <span class="icon">☀️</span>
          <span class="label">Wakeup</span>
        </button>
        <button class="action-btn ctrl-btn" data-action="sleep">
          <span class="icon">🌙</span>
          <span class="label">Sleep</span>
        </button>
        <button class="action-btn ctrl-btn" data-action="recovery">
          <span class="icon">🔧</span>
          <span class="label">Recovery</span>
        </button>
        <button class="action-btn ctrl-btn" data-action="init">
          <span class="icon">🚀</span>
          <span class="label">Init</span>
        </button>
        <button class="action-btn ctrl-btn" data-action="reset">
          <span class="icon">🔄</span>
          <span class="label">Reset</span>
        </button>
      </div>
    </div>
    
    <!-- Main Actions -->
    <div class="section">
      <div class="action-area">
        <button class="btn btn-primary" id="btn-run" style="flex: 2;">
          ▶ Send to Display
        </button>
        <button class="btn btn-danger" id="btn-stop">
          ⏹ Stop
        </button>
      </div>
    </div>
  </div>
  
  <!-- Status Bar -->
  <div class="status-bar">
    <span class="status-dot" id="status-dot"></span>
    <span id="status-text">Ready</span>
    <span style="margin-left: auto;">PCCooler GT360</span>
  </div>

  <script>
    // State
    var selectedPattern = 'blue';
    var currentSource = 'image';
    var isBusy = false;
    
    // Elements
    var infobar = document.getElementById('infobar');
    var infobarIcon = document.getElementById('infobar-icon');
    var infobarMessage = document.getElementById('infobar-message');
    var statusDot = document.getElementById('status-dot');
    var statusText = document.getElementById('status-text');
    var filePathInput = document.getElementById('file-path');
    var selectedFileDisplay = document.getElementById('selected-file');
    var dropZone = document.getElementById('drop-zone');
    
    // Theme Toggle
    var themeToggle = document.getElementById('theme-toggle');
    function updateThemeIcon() {
      var isDark = document.documentElement.getAttribute('data-theme') === 'dark' ||
        (!document.documentElement.getAttribute('data-theme') && window.matchMedia('(prefers-color-scheme: dark)').matches);
      themeToggle.textContent = isDark ? '☀️' : '🌙';
    }
    
    // Theme toggle (no persistence due to data: URL restrictions)
    themeToggle.addEventListener('click', function() {
      var current = document.documentElement.getAttribute('data-theme');
      var newTheme = current === 'dark' ? 'light' : 'dark';
      document.documentElement.setAttribute('data-theme', newTheme);
      updateThemeIcon();
    });
    
    // Initialize theme based on system preference
    updateThemeIcon();
    
    // Source Tab Switching
    var sourceTabs = document.querySelectorAll('.source-tab');
    var contentAreas = document.querySelectorAll('.content-area');
    
    sourceTabs.forEach(function(tab) {
      tab.addEventListener('click', function(e) {
        e.preventDefault();
        e.stopPropagation();
        
        var source = this.getAttribute('data-source');
        if (!source) return;
        
        currentSource = source;
        
        // Update tabs
        sourceTabs.forEach(function(t) { t.classList.remove('active'); });
        this.classList.add('active');
        
        // Update content areas
        contentAreas.forEach(function(area) { 
          area.classList.remove('active'); 
          area.style.display = 'none';
        });
        
        var targetContent = document.getElementById('content-' + source);
        if (targetContent) {
          targetContent.style.display = 'block';
          // Small delay to trigger animation
          setTimeout(function() {
            targetContent.classList.add('active');
          }, 10);
        }
      });
    });
    
    // Pattern Selection
    var patternItems = document.querySelectorAll('.pattern-item');
    
    patternItems.forEach(function(item) {
      item.addEventListener('click', function(e) {
        e.preventDefault();
        e.stopPropagation();
        
        if (isBusy) return;
        
        var pattern = this.getAttribute('data-pattern');
        if (!pattern) return;
        
        selectedPattern = pattern;
        
        // Remove selected from all
        patternItems.forEach(function(p) { 
          p.classList.remove('selected'); 
        });
        
        // Add selected to clicked
        this.classList.add('selected');
      });
    });
    
    // Slider Updates
    var ssQuality = document.getElementById('screensaver-quality');
    var ssScale = document.getElementById('screensaver-scale');
    var ssFps = document.getElementById('screensaver-fps');
    var chunkDelaySlider = document.getElementById('chunk-delay');
    var brightnessSlider = document.getElementById('brightness');
    
    if (ssQuality) {
      ssQuality.addEventListener('input', function() {
        var val = document.getElementById('screensaver-quality-val');
        if (val) val.textContent = this.value;
      });
    }
    
    if (ssScale) {
      ssScale.addEventListener('input', function() {
        var val = document.getElementById('screensaver-scale-val');
        if (val) val.textContent = this.value;
      });
    }
    
    if (ssFps) {
      ssFps.addEventListener('input', function() {
        var val = document.getElementById('screensaver-fps-val');
        if (val) val.textContent = this.value;
      });
    }
    
    if (chunkDelaySlider) {
      chunkDelaySlider.addEventListener('input', function() {
        var val = parseInt(this.value);
        var actual = val === 0 ? 0 : val / 1000;
        var display = document.getElementById('chunk-delay-val');
        if (display) display.textContent = actual.toFixed(3);
      });
    }
    
    // Brightness slider update
    if (brightnessSlider) {
      brightnessSlider.addEventListener('input', function() {
        var val = document.getElementById('brightness-val');
        if (val) val.textContent = this.value;
      });
    }
    
    // File Handling
    function handleFile(path) {
      if (!path) return;
      
      filePathInput.value = path;
      
      if (selectedFileDisplay) {
        var filename = path.split(/[\\/]/).pop();
        selectedFileDisplay.textContent = filename;
      }
      
      // Auto-set format from extension
      var ext = (path.split('.').pop() || '').toLowerCase();
      var map = { png: 'png', jpg: 'jpeg', jpeg: 'jpeg', gif: 'mp4', bmp: 'bmp', mp4: 'mp4' };
      var formatSelect = document.getElementById('format');
      if (map[ext] && formatSelect) {
        formatSelect.value = map[ext];
      }
    }
    
    // Drag and Drop - Fixed
    if (dropZone) {
      // Prevent default drag behaviors on document
      ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(function(eventName) {
        document.body.addEventListener(eventName, function(e) {
          e.preventDefault();
          e.stopPropagation();
        }, false);
      });
      
      // Drop zone specific handlers
      dropZone.addEventListener('dragenter', function(e) {
        e.preventDefault();
        e.stopPropagation();
        this.classList.add('dragover');
      }, false);
      
      dropZone.addEventListener('dragover', function(e) {
        e.preventDefault();
        e.stopPropagation();
        this.classList.add('dragover');
      }, false);
      
      dropZone.addEventListener('dragleave', function(e) {
        e.preventDefault();
        e.stopPropagation();
        this.classList.remove('dragover');
      }, false);
      
      dropZone.addEventListener('drop', function(e) {
        e.preventDefault();
        e.stopPropagation();
        this.classList.remove('dragover');
        
        var files = e.dataTransfer.files;
        if (files && files.length > 0) {
          var file = files[0];
          
          // Try to get path, fallback to name
          var path = file.path || file.name;
          if (path) {
            handleFile(path);
            showInfoBar('File selected: ' + file.name, 'info');
          }
        } else {
          // Try to get from dataTransfer data
          var path = e.dataTransfer.getData('text/plain');
          if (path) {
            handleFile(path);
          }
        }
      }, false);
      
      // Click to browse
      dropZone.addEventListener('click', function(e) {
        e.preventDefault();
        e.stopPropagation();
        
        if (window.pywebview && window.pywebview.api) {
          window.pywebview.api.choose_file().then(function(path) {
            if (path) {
              handleFile(path);
            }
          }).catch(function(err) {
            showInfoBar('Error opening file dialog', 'error');
          });
        } else {
          // Fallback - create a hidden file input
          var input = document.createElement('input');
          input.type = 'file';
          input.accept = '.png,.jpg,.jpeg,.gif,.bmp,.mp4';
          input.onchange = function(e) {
            if (e.target.files && e.target.files[0]) {
              handleFile(e.target.files[0].name);
            }
          };
          input.click();
        }
      });
    }
    
    // Browse Button
    var browseBtn = document.getElementById('btn-browse');
    if (browseBtn) {
      browseBtn.addEventListener('click', function(e) {
        e.preventDefault();
        e.stopPropagation();
        
        if (window.pywebview && window.pywebview.api) {
          window.pywebview.api.choose_file().then(function(path) {
            if (path) {
              handleFile(path);
            }
          }).catch(function(err) {
            showInfoBar('Error: ' + err, 'error');
          });
        } else {
          showInfoBar('File dialog not available', 'error');
        }
      });
    }
    
    // Manual file path input
    if (filePathInput) {
      filePathInput.addEventListener('change', function() {
        if (this.value) handleFile(this.value);
      });
      
      filePathInput.addEventListener('blur', function() {
        if (this.value) handleFile(this.value);
      });
    }
    
    // Status Functions
    function showInfoBar(message, type) {
      if (!infobar || !infobarMessage || !infobarIcon) return;
      
      infobar.className = 'infobar show ' + (type || 'info');
      infobarMessage.textContent = message;
      
      var icons = { info: 'ℹ️', success: '✅', error: '❌', running: '⏳' };
      infobarIcon.textContent = icons[type] || icons.info;
      
      if (type === 'success') {
        setTimeout(function() { 
          infobar.classList.remove('show'); 
        }, 5000);
      }
    }
    
    function setBusy(busy) {
      isBusy = busy;
      var buttons = document.querySelectorAll('.action-btn, #btn-run, #btn-browse');
      
      buttons.forEach(function(btn) {
        if (btn.id !== 'btn-stop') {
          btn.disabled = busy;
        }
      });
      
      if (statusDot && statusText) {
        if (busy) {
          statusDot.classList.add('working');
          statusText.textContent = 'Working...';
          showInfoBar('Operation in progress...', 'running');
        } else {
          statusDot.classList.remove('working');
          statusText.textContent = 'Ready';
        }
      }
    }
    
    window.__runComplete = function(ok, message) {
      setBusy(false);
      showInfoBar(message, ok ? 'success' : 'error');
    };
    
    // Get Options
    window.getOptions = function(extra) {
      var chunkDelay = chunkDelaySlider ? parseInt(chunkDelaySlider.value) : 1;
      
      var opts = {
        image: currentSource === 'image' ? (filePathInput ? filePathInput.value : '') : null,
        pattern: currentSource === 'pattern' ? selectedPattern : null,
        system: currentSource === 'system',
        screensaver: currentSource === 'screensaver' ? (document.getElementById('screensaver-type') ? document.getElementById('screensaver-type').value : 'bounce') : null,
        screensaver_quality: currentSource === 'screensaver' ? (ssQuality ? parseInt(ssQuality.value) : 60) : 60,
        screensaver_scale: currentSource === 'screensaver' ? (ssScale ? parseFloat(ssScale.value) : 1) : 1,
        screensaver_fps: currentSource === 'screensaver' ? (ssFps ? parseFloat(ssFps.value) : 30) : 30,
        resolution: document.getElementById('resolution') ? document.getElementById('resolution').value : '640x480',
        format: document.getElementById('format') ? document.getElementById('format').value : 'png',
        loop: document.getElementById('loop') ? document.getElementById('loop').checked : false,
        chunk_delay: chunkDelay === 0 ? 0 : chunkDelay / 1000,
        max_retries: document.getElementById('max-retries') ? document.getElementById('max-retries').value : 10,
        timeout: document.getElementById('timeout') ? (document.getElementById('timeout').value || null) : null,
        brightness: document.getElementById('brightness') ? parseInt(document.getElementById('brightness').value) : null,
        orientation: document.getElementById('orientation') ? parseInt(document.getElementById('orientation').value) : null
      };
      
      if (extra) {
        for (var key in extra) opts[key] = extra[key];
      }
      
      return opts;
    };
    
    // Run Button
    var runBtn = document.getElementById('btn-run');
    if (runBtn) {
      runBtn.addEventListener('click', function(e) {
        e.preventDefault();
        setBusy(true);
        if (window.pywebview && window.pywebview.api) {
          window.pywebview.api.run(window.getOptions());
        } else {
          showInfoBar('API not available', 'error');
          setBusy(false);
        }
      });
    }
    
    // Stop Button
    var stopBtn = document.getElementById('btn-stop');
    if (stopBtn) {
      stopBtn.addEventListener('click', function(e) {
        e.preventDefault();
        if (window.pywebview && window.pywebview.api) {
          window.pywebview.api.stop();
        }
        setBusy(false);
        if (statusText) statusText.textContent = 'Stopped';
      });
    }
    
    // Control Buttons
    document.querySelectorAll('.ctrl-btn').forEach(function(btn) {
      btn.addEventListener('click', function(e) {
        e.preventDefault();
        
        var action = this.getAttribute('data-action');
        if (!action) return;
        
        var extra = {};
        extra[action] = true;
        setBusy(true);
        
        if (window.pywebview && window.pywebview.api) {
          window.pywebview.api.run(window.getOptions(extra));
        }
      });
    });
    
    // Brightness Apply Button
    var brightnessBtn = document.getElementById('btn-brightness');
    if (brightnessBtn) {
      brightnessBtn.addEventListener('click', function(e) {
        e.preventDefault();
        setBusy(true);
        if (window.pywebview && window.pywebview.api) {
          window.pywebview.api.run({brightness: parseInt(document.getElementById('brightness').value)});
        }
      });
    }
    
    // Orientation Apply Button
    var orientationBtn = document.getElementById('btn-orientation');
    if (orientationBtn) {
      orientationBtn.addEventListener('click', function(e) {
        e.preventDefault();
        setBusy(true);
        if (window.pywebview && window.pywebview.api) {
          window.pywebview.api.run({orientation: parseInt(document.getElementById('orientation').value)});
        }
      });
    }
    
    // Keyboard Shortcuts
    document.addEventListener('keydown', function(e) {
      if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
        e.preventDefault();
        if (runBtn) runBtn.click();
      }
      if ((e.ctrlKey || e.metaKey) && e.key === '.') {
        e.preventDefault();
        if (stopBtn) stopBtn.click();
      }
    });
  </script>
</body>
</html>
'''

def main():
    # USB library needs root, but the UI must not run as root (e.g. pywebview/Qt on Linux)
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        print("Do not run the UI as root. Run as a normal user; USB operations use a privileged helper.", file=sys.stderr)
        sys.exit(1)
    try:
        api = Api()
        window = webview.create_window("PCCooler GT360", html=HTML, width=720, height=900, js_api=api)
        api.set_window(window)
        if sys.platform == "linux":
            webview.start(gui="qt")
        else:
            webview.start()
    except Exception as e:
        err = str(e).lower()
        if "qt" in err or "gtk" in err or "gui" in err or "backend" in err or "extension" in err:
            if os.path.exists("/etc/arch-release"):
                print("On Arch with KDE install: sudo pacman -S python-pywebview python-pyqt5 python-pyqt5-webengine", file=sys.stderr)
            else:
                print("On Linux you need a pywebview backend. For KDE/Qt: pip install 'pywebview[qt]'", file=sys.stderr)
                print("Alternative: pip install 'pywebview[gtk]'", file=sys.stderr)
            sys.exit(1)
        raise

if __name__ == "__main__":
    main()
