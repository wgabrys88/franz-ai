"""Franz brain -- the only file you edit.

Set your config, write your system prompt, fill in on_vlm_response.
Run with: python router.py

When the app starts a region selector overlay appears.
  - Drag to select a capture area (no resize, raw pixels).
  - Right-click to use full screen (resized to CAPTURE_WIDTH x CAPTURE_HEIGHT).
  - Press Escape to quit.

== PIPES ==

on_vlm_response receives the VLM text each turn.
Inside it, push items into two ordered queues:

    actions(click(500, 990))      -- queue a desktop action
    actions(type_text("hello"))   -- queue another action
    overlays(dot(500, 500, "x"))  -- queue a polygon overlay

When the function returns the system drains the queues:
  1. Actions execute on the desktop in order.
  2. A fresh screenshot is taken.
  3. Overlays paint on that screenshot in order.

Return a string -- it becomes context for the next VLM turn.

== ACTION HELPERS (push with: actions(helper(...))) ==

    click(x, y)           double_click(x, y)      right_click(x, y)
    type_text(text)        press_key(name)          hotkey(combo)
    scroll_up(x, y)       scroll_down(x, y)
    drag_start(x, y)      drag_end(x, y)

    Coordinates: integers 0-1000. (0,0)=top-left, (1000,1000)=bottom-right.
    press_key: enter, tab, escape, backspace, delete, up, down, left, right
    hotkey: ctrl+c, alt+f4, ctrl+shift+s, win

== OVERLAY HELPERS (push with: overlays(helper(...))) ==

    dot(x, y, label, color)
    box(x1, y1, x2, y2, label, stroke_color, fill_color)
    line(points, label, color)

    All produce a 2D polygon drawn on the HTML5 canvas.

== FREEDOM ==

Inside on_vlm_response you can do ANYTHING with Python stdlib:
  - Parse text with regex or json
  - Make HTTP calls to any API with urllib.request
  - Capture a fresh screenshot yourself:
        subprocess.run([sys.executable, "win32.py", "capture"], ...)
  - Run subprocesses, read files, import any stdlib module
  - Call multiple AI models, chain them, compare results

The function is your program. The pipes are your output interface.
"""

import base64
import json
import re
import subprocess
import sys
import urllib.request
from franz import actions
from franz import overlays
from franz import click
from franz import double_click
from franz import right_click
from franz import type_text
from franz import press_key
from franz import hotkey
from franz import scroll_up
from franz import scroll_down
from franz import drag_start
from franz import drag_end
from franz import dot
from franz import box
from franz import line


VLM_ENDPOINT_URL: str = "http://127.0.0.1:1235/v1/chat/completions"
VLM_MODEL_NAME: str = "qwen3-vl-2b"
VLM_TEMPERATURE: float = 0.4
VLM_TOP_P: float = 0.9
VLM_MAX_TOKENS: int = 300
SERVER_HOST: str = "127.0.0.1"
SERVER_PORT: int = 1234
CAPTURE_REGION: str = ""
CAPTURE_WIDTH: int = 640
CAPTURE_HEIGHT: int = 640
CAPTURE_DELAY_SECONDS: float = 2.5
ACTION_DELAY_SECONDS: float = 0.3
SHOW_CURSOR: bool = True


SYSTEM_PROMPT: str = """You are an AI explorer controlling a Windows 11 desktop.
You see a screenshot of the screen. A green crosshair shows cursor at [x,y].
Coordinates go from 0 to 1000. (0,0) is top-left, (1000,1000) is bottom-right.

Your job is to explore the Windows system. Look around, open things, read what
you find. If the user gives you a task, do it. Otherwise keep exploring.

Describe what you see and what you want to do next in plain English.
Do NOT output tool calls. Just describe your intent.

Example:
I see the Windows desktop with a taskbar at the bottom. The time shows 14:32.
I can see icons for Edge, File Explorer, and a Recycle Bin.
I want to open the Start menu to see what programs are installed."""


EXECUTOR_SYSTEM: str = """You translate a user intention into tool calls.
You also see the screenshot so you know exact positions of UI elements.

Available tools (coordinates are integers 0 to 1000):
  click(x, y)
  double_click(x, y)
  right_click(x, y)
  type_text(text)
  press_key(name) -- enter, tab, escape, backspace, delete, up, down, left, right
  hotkey(combo) -- ctrl+c, alt+f4, ctrl+shift+s, win
  scroll_up(x, y)
  scroll_down(x, y)
  drag_start(x, y)
  drag_end(x, y)

Output ONLY tool calls, one per line. Nothing else. No explanation.

Example output:
click(500, 980)
type_text(notepad)
press_key(enter)"""


def on_vlm_response(text: str) -> str:

    screenshot_proc = subprocess.run(
        [sys.executable, "win32.py", "capture", "--width", "0", "--height", "0"],
        capture_output=True,
    )
    if not screenshot_proc.stdout:
        return text
    screenshot_b64 = base64.b64encode(screenshot_proc.stdout).decode("ascii")

    request_body = json.dumps({
        "model": VLM_MODEL_NAME,
        "temperature": 0.1,
        "max_tokens": 200,
        "messages": [
            {"role": "system", "content": EXECUTOR_SYSTEM},
            {"role": "user", "content": [
                {"type": "text", "text": text},
                {"type": "image_url", "image_url": {
                    "url": "data:image/png;base64," + screenshot_b64,
                }},
            ]},
        ],
    }).encode("utf-8")

    request = urllib.request.Request(
        VLM_ENDPOINT_URL,
        data=request_body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            response_data = json.loads(response.read().decode("utf-8"))
        executor_text = response_data["choices"][0]["message"]["content"]
    except Exception:
        return text

    for found in re.finditer(r"(\w+)$([^)]*)$", executor_text):
        name = found.group(1).strip().lower()
        args = found.group(2).strip()

        if name == "click":
            parts = args.split(",")
            if len(parts) >= 2:
                actions(click(int(parts[0].strip()), int(parts[1].strip())))

        elif name == "double_click":
            parts = args.split(",")
            if len(parts) >= 2:
                actions(double_click(int(parts[0].strip()), int(parts[1].strip())))

        elif name == "right_click":
            parts = args.split(",")
            if len(parts) >= 2:
                actions(right_click(int(parts[0].strip()), int(parts[1].strip())))

        elif name == "type_text":
            actions(type_text(args))

        elif name == "press_key":
            actions(press_key(args))

        elif name == "hotkey":
            actions(hotkey(args))

        elif name == "scroll_up":
            parts = args.split(",")
            if len(parts) >= 2:
                actions(scroll_up(int(parts[0].strip()), int(parts[1].strip())))

        elif name == "scroll_down":
            parts = args.split(",")
            if len(parts) >= 2:
                actions(scroll_down(int(parts[0].strip()), int(parts[1].strip())))

        elif name == "drag_start":
            parts = args.split(",")
            if len(parts) >= 2:
                actions(drag_start(int(parts[0].strip()), int(parts[1].strip())))

        elif name == "drag_end":
            parts = args.split(",")
            if len(parts) >= 2:
                actions(drag_end(int(parts[0].strip()), int(parts[1].strip())))

    return text
