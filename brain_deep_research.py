"""Franz brain -- Deep Research Entity

A 2B VLM entity that researches topics using the real desktop.
It opens Notepad to communicate with the user, browses the web,
and collects findings back into Notepad.

Run with: python router.py
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
VLM_TEMPERATURE: float = 0.3
VLM_TOP_P: float = 0.9
VLM_MAX_TOKENS: int = 400
SERVER_HOST: str = "127.0.0.1"
SERVER_PORT: int = 1234
CAPTURE_REGION: str = ""
CAPTURE_WIDTH: int = 640
CAPTURE_HEIGHT: int = 640
CAPTURE_DELAY_SECONDS: float = 3.0
ACTION_DELAY_SECONDS: float = 0.5
SHOW_CURSOR: bool = True


SYSTEM_PROMPT: str = """You are Franz, a research entity living inside a Windows 11 desktop.
You have eyes (screenshot), hands (mouse and keyboard), and a mission: deep research.

Green crosshair shows your cursor at [x,y]. Coordinates: 0-1000, top-left to bottom-right.

YOUR LIFE FOLLOWS PHASES. Read the screen carefully to know which phase you are in.

== PHASE 1: SETUP ==
If you do not see a Notepad window open, you must open one.
Click the Windows taskbar search or Start menu, type "notepad", press Enter.
Wait for Notepad to appear.

== PHASE 2: ASK THE USER ==
When Notepad is open and empty (or has your previous text), type a message to the user:
"FRANZ RESEARCH AGENT - Type your research topic below, then type FRANZ START on a new line when ready."
Then STOP acting. Just observe. Describe what you see. Do NOT click or type anything else.
Wait for the user to type something.

== PHASE 3: DETECT USER INPUT ==
Look at the Notepad window carefully. If you see "FRANZ START" typed by the user,
read the text ABOVE "FRANZ START" - that is the research topic.
Remember the topic. Move to Phase 4.
If you do NOT see "FRANZ START", keep waiting. Describe what you see. Do not act.

== PHASE 4: RESEARCH ==
You now have a research topic. Your job:
1. Open Google Chrome (click taskbar or search for it)
2. Go to x.com (Twitter) - type x.com in the address bar and press Enter
3. Use the search feature on x.com to find posts about your topic
4. Read what you find on screen
5. Select interesting text, copy it (Ctrl+C)
6. Switch to Notepad (click it in taskbar or Alt+Tab)
7. Paste findings (Ctrl+V), add a newline
8. Go back to Chrome and search more, or try Grok (if available on x.com)
9. Repeat: search, read, copy, paste into Notepad

== PHASE 5: ONGOING ==
Keep researching. Each turn, describe what you see, what you found, what to search next.
Paste every useful finding into Notepad so the user can read it.

== RULES ==
- Always describe what you see FIRST, then say what you will do.
- One step at a time. Do not rush. Small careful actions.
- If something unexpected happens (popup, error), describe it and adapt.
- You are curious and thorough. You want to find good information.
- If a page is loading, wait. Say "I see the page is loading, I will wait."
- Never close Notepad. It is your notebook and communication channel with the user.
- When copying text from Chrome, be careful: click at start of text, drag to end, then Ctrl+C.
  Or use click then Shift+click to select, then Ctrl+C.
  Or triple-click to select a paragraph, then Ctrl+C.
- After pasting in Notepad, press Enter twice to add spacing before next finding.

Your personality: You are methodical, curious, and communicative.
You narrate your research like a detective following leads.
You care about giving the user good information."""


EXECUTOR_SYSTEM: str = """You translate a description of a desktop action into exact tool calls.
You see the screenshot. You know where every button, text field, and UI element is.

Available tools (coordinates 0 to 1000):
  click(x, y)
  double_click(x, y)
  right_click(x, y)
  type_text(text)
  press_key(name) -- enter, tab, escape, backspace, delete, up, down, left, right
  hotkey(combo) -- ctrl+c, alt+f4, ctrl+shift+s, win, alt+tab, ctrl+v, ctrl+a
  scroll_up(x, y)
  scroll_down(x, y)
  drag_start(x, y)
  drag_end(x, y)

RULES:
- Output ONLY tool calls, one per line.
- No explanation. No text. Just tool calls.
- Look at the screenshot to find exact coordinates of UI elements.
- If the instruction says "click on the search box" - find it in the screenshot and give exact x,y.
- If the instruction says "type something" - just output type_text(the text).
- Maximum 3 tool calls per response. Small steps.
- Be precise with coordinates. Look at the screenshot carefully.

Example:
click(500, 980)
type_text(notepad)
press_key(enter)"""


def on_vlm_response(text: str) -> str:

    # Take a fresh screenshot for the executor
    screenshot_proc = subprocess.run(
        [sys.executable, "win32.py", "capture", "--width", "0", "--height", "0"],
        capture_output=True,
    )
    if not screenshot_proc.stdout:
        return text

    screenshot_b64 = base64.b64encode(screenshot_proc.stdout).decode("ascii")

    # Check if the VLM is just observing (waiting for user)
    text_lower = text.lower()
    is_waiting = False
    if "wait" in text_lower and "franz start" not in text_lower:
        if "do not act" in text_lower or "keep waiting" in text_lower or "just observe" in text_lower:
            is_waiting = True
    if "i will wait" in text_lower and "not see franz start" in text_lower:
        is_waiting = True
    if "waiting for the user" in text_lower:
        is_waiting = True

    if is_waiting:
        # Entity is waiting for user input, don't push any actions
        overlays(dot(500, 500, "waiting for user...", "#ffff00"))
        return text

    # Send to executor: the VLM's intent + the screenshot
    request_body = json.dumps({
        "model": VLM_MODEL_NAME,
        "temperature": 0.1,
        "max_tokens": 150,
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
        overlays(dot(500, 500, "executor call failed", "#ff0000"))
        return text

    # Parse tool calls and push into pipes
    action_count = 0

    for found in re.finditer(r"(\w+)$([^)]*)$", executor_text):
        name = found.group(1).strip().lower()
        args = found.group(2).strip()

        if name == "click":
            parts = args.split(",")
            if len(parts) >= 2:
                x = int(parts[0].strip())
                y = int(parts[1].strip())
                actions(click(x, y))
                overlays(dot(x, y, "click " + str(action_count + 1), "#ff4444"))
                action_count = action_count + 1

        elif name == "double_click":
            parts = args.split(",")
            if len(parts) >= 2:
                x = int(parts[0].strip())
                y = int(parts[1].strip())
                actions(double_click(x, y))
                overlays(dot(x, y, "dblclick " + str(action_count + 1), "#ff8800"))
                action_count = action_count + 1

        elif name == "right_click":
            parts = args.split(",")
            if len(parts) >= 2:
                x = int(parts[0].strip())
                y = int(parts[1].strip())
                actions(right_click(x, y))
                overlays(dot(x, y, "rightclick " + str(action_count + 1), "#ff00ff"))
                action_count = action_count + 1

        elif name == "type_text":
            actions(type_text(args))
            overlays(dot(50, 50, "typing: " + args[:30], "#44aaff"))
            action_count = action_count + 1

        elif name == "press_key":
            actions(press_key(args))
            overlays(dot(50, 80, "key: " + args, "#44ff44"))
            action_count = action_count + 1

        elif name == "hotkey":
            actions(hotkey(args))
            overlays(dot(50, 80, "hotkey: " + args, "#ffff44"))
            action_count = action_count + 1

        elif name == "scroll_up":
            parts = args.split(",")
            if len(parts) >= 2:
                x = int(parts[0].strip())
                y = int(parts[1].strip())
                actions(scroll_up(x, y))
                action_count = action_count + 1

        elif name == "scroll_down":
            parts = args.split(",")
            if len(parts) >= 2:
                x = int(parts[0].strip())
                y = int(parts[1].strip())
                actions(scroll_down(x, y))
                action_count = action_count + 1

        elif name == "drag_start":
            parts = args.split(",")
            if len(parts) >= 2:
                x = int(parts[0].strip())
                y = int(parts[1].strip())
                actions(drag_start(x, y))
                action_count = action_count + 1

        elif name == "drag_end":
            parts = args.split(",")
            if len(parts) >= 2:
                x = int(parts[0].strip())
                y = int(parts[1].strip())
                actions(drag_end(x, y))
                action_count = action_count + 1

    if action_count == 0:
        overlays(dot(500, 500, "no actions parsed", "#888888"))

    return text
