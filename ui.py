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
            "pattern": options.get("pattern", "blue"),
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
            "stop_event": stop_event
        }
        
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

def _load_html_template() -> str:
    """Load the HTML template from the assets directory."""
    import os
    
    # Try to find the template file
    possible_paths = [
        # When running from repo root
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "pccooler_gt360", "assets", "ui.html"),
        # When running from package directory
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "ui.html"),
        # Absolute path for installed package
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "pccooler_gt360", "assets", "ui.html"),
    ]
    
    for path in possible_paths:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
    
    # Fallback: raise error if not found
    raise FileNotFoundError(
        f"Could not find ui.html template. Searched: {possible_paths}"
    )

def main():
    # USB library needs root, but the UI must not run as root (e.g. pywebview/Qt on Linux)
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        print("Do not run the UI as root. Run as a normal user; USB operations use a privileged helper.", file=sys.stderr)
        sys.exit(1)
    try:
        api = Api()
        html_content = _load_html_template()
        window = webview.create_window("PCCooler GT360", html=html_content, width=720, height=900, js_api=api)
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
