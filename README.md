<div align="center">

 ```
 ███████╗██████╗  █████╗ ███╗   ██╗███████╗
 ██╔════╝██╔══██╗██╔══██╗████╗  ██║╚══███╔╝
 █████╗  ██████╔╝███████║██╔██╗ ██║  ███╔╝ 
 ██╔══╝  ██╔══██╗██╔══██║██║╚██╗██║ ███╔╝  
 ██║     ██║  ██║██║  ██║██║ ╚████║███████╗
 ╚═╝     ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═══╝╚══════╝
```
### An entity, not an agent.

*One function. Two pipes. Zero dependencies beyond Python.*

**No tool calling · No MCP · No skills · No context accumulation · No safety theater**

A vision-language model talks to itself, sees a screen, presses keys, moves a mouse.

[Quickstart](#quickstart) · [How It Works](#how-it-works) · [The Brain](#the-brain) · [Example Brains](#example-brains) · [Create Brains with AI](#create-brains-with-ai) · [Why Entity, Not Agent](#why-entity-not-agent)

</div>

---

## The Flip

Every AI agent framework does this:

```
tools → planner → memory → safety filter → tool caller → response parser → ...
```

Franz does this:

```
screenshot → model → your function → two pipes → real desktop
```

That's it. There is no planner. No memory database. No skill registry. No MCP server. No safety filter. No token-stuffed context window. The model sees. It speaks. Your function decides what to push into two pipes. The system executes.

**The AI is not the model. The AI is the story the model tells itself.**

---

## The Architecture

```
╔══════════════════════════════════════════════════════════════════════════╗
║                                                                          ║
║   ┌───────────┐   screenshot   ┌───────────┐    text     ┌───────────┐   ║
║   │           │ ─────────────▶ │           │ ──────────▶ │          │   ║
║   │  Screen   │                │    VLM    │             │  brain.py  │  ║
║   │ (win32)   │                │  (model)  │             │            │  ║
║   │           │ ◀───────────── │           │             │  YOUR     │  ║
║   └───────────┘   actions      └───────────┘             │  CODE      │  ║
║        ▲          from pipe                               │           │  ║
║        │                                                  └─────┬─────┘  ║
║        │                                                        │        ║
║        │         ┌──────────────────┐    ┌──────────────────┐   │        ║
║        │         │   ACTION PIPE    │    │  OVERLAY PIPE    │   │        ║
║        │         │                  │    │                  │   │        ║
║        │         │  click(500,300)  │◀───│  dot(500,300)    │◀──┘       ║
║        │         │  type_text("hi") │    │  box(0,0,100,..) │            ║
║        │         │  press_key(tab)  │    │  line([...])     │            ║
║        │         └────────┬─────────┘    └────────┬─────────┘            ║
║        │                  │                       │                      ║
║        │         execute in order          draw on screenshot            ║
║        │                  │              (after actions + capture)       ║
║        └──────────────────┘                       │                      ║
║                                                   ▼                      ║
║                                          ┌──────────────────┐            ║
║                                          │  Browser Panel   │            ║
║                                          │  (panel.html)    │            ║
║                                          └──────────────────┘            ║
╚══════════════════════════════════════════════════════════════════════════╝
```

### The Cycle

```
1. CAPTURE    win32.py screenshots the screen (or selected region)
      │
2. SEE        Screenshot sent to VLM with system prompt + previous context
      │
3. SPEAK      VLM responds with text
      │
4. THINK      on_vlm_response(text) runs — your code, your logic, your rules
      │
5. ACT        System drains the action pipe → clicks, types, scrolls on real desktop
      │
6. CAPTURE    Fresh screenshot taken after actions complete
      │
7. OBSERVE    System drains overlay pipe → polygons drawn on fresh screenshot
      │
8. LOOP       Goto 1 — the entity sees what changed
```

Each turn is **stateless from the system's perspective**. The only state is what you return from `on_vlm_response` — a string that becomes context for the next VLM call.

---

## Quickstart

### You need

| What | Where |
|------|-------|
| **Python 3.13+** | [python.org/downloads](https://www.python.org/downloads/) |
| **LM Studio** | [lmstudio.ai](https://lmstudio.ai/) |
| **A vision model** | Qwen3-VL-2B runs on 8GB RAM |
| **Windows 10 or 11** | That's where it clicks |

No pip. No git. No venv. No requirements.txt. Zero dependencies beyond Python stdlib.

### Steps

**1.** Download five files into one folder:

```
franz/
├── brain.py       ← THE ONLY FILE YOU EDIT
├── franz.py       ← pipe system (frozen)
├── router.py      ← engine loop (frozen)
├── win32.py       ← mouse/keyboard/screen (frozen)
└── panel.html     ← browser dashboard (frozen)
```

**2.** Open LM Studio → load `qwen3-vl-2b` → start local server (default port 1235)

**3.** Run:

```
python router.py
```

**4.** A dark overlay appears — the region selector:

| Action | Result |
|--------|--------|
| **Drag** with left mouse | Captures that region only (no resize, raw pixels) |
| **Right-click** | Full screen mode (resized to config dimensions) |
| **Escape** | Quit |

**5.** Browser opens with the dashboard. The entity starts seeing and acting.

---

## The Brain

`brain.py` is the only file you ever edit. It has three parts:

### Config (flat variables at the top)

```python
VLM_ENDPOINT_URL: str = "http://127.0.0.1:1235/v1/chat/completions"
VLM_MODEL_NAME: str = "qwen3-vl-2b"
CAPTURE_DELAY_SECONDS: float = 2.5
# ... etc
```

### System Prompt (what the VLM reads every turn)

```python
SYSTEM_PROMPT: str = """You are an AI explorer..."""
```

### The Function (your entire program)

```python
def on_vlm_response(text: str) -> str:
    # text = what the VLM just said
    
    actions(click(500, 300))        # push into action pipe
    actions(type_text("hello"))     # push another action
    overlays(dot(500, 300, "here")) # push into overlay pipe
    
    return "context for next turn"  # this string feeds back to VLM
```

**That's the entire programming interface.**

The pipes are ordered queues — first in, first out. Push `click` then `type_text`, the system clicks first, then types. Nothing executes while you're still pushing. When your function returns, the system drains both pipes.

### Inside on_vlm_response you can do anything

It's pure Python. The full stdlib is at your disposal:

```python
# Parse VLM text
import re
for match in re.finditer(r"click\((\d+),\s*(\d+)\)", text):
    actions(click(int(match.group(1)), int(match.group(2))))

# Capture a fresh screenshot yourself
import subprocess, sys, base64
proc = subprocess.run([sys.executable, "win32.py", "capture"], capture_output=True)
image_b64 = base64.b64encode(proc.stdout).decode("ascii")

# Call another AI model
import urllib.request, json
body = json.dumps({"model": "...", "messages": [...]}).encode()
req = urllib.request.Request("http://...", data=body, headers={...})
with urllib.request.urlopen(req) as resp:
    result = json.loads(resp.read())

# Push nothing — that's fine too. The system doesn't care.
return text
```

---

## Action & Overlay Reference

### Actions (push with `actions(helper(...))`)

| Helper | Description | Arguments |
|--------|-------------|-----------|
| `click(x, y)` | Left click | coordinates 0-1000 |
| `double_click(x, y)` | Double left click | coordinates 0-1000 |
| `right_click(x, y)` | Right click | coordinates 0-1000 |
| `type_text(text)` | Type characters | any string |
| `press_key(name)` | Press key | enter, tab, escape, backspace, delete, up, down, left, right, f1-f12 |
| `hotkey(combo)` | Key combination | ctrl+c, alt+f4, ctrl+shift+s, win, alt+tab |
| `scroll_up(x, y)` | Scroll up at position | coordinates 0-1000 |
| `scroll_down(x, y)` | Scroll down at position | coordinates 0-1000 |
| `drag_start(x, y)` | Begin drag | coordinates 0-1000 |
| `drag_end(x, y)` | End drag (push after drag_start) | coordinates 0-1000 |

### Overlays (push with `overlays(helper(...))`)

| Helper | Description |
|--------|-------------|
| `dot(x, y, label="", color="#00ff00")` | A point with label |
| `box(x1, y1, x2, y2, label="", stroke="#ff6600", fill="")` | A rectangle |
| `line(points, label="", color="#4488ff")` | A polyline from `[[x,y], ...]` |

All overlays are 2D polygons on the HTML5 canvas. A dot is a degenerate polygon. A box is four points. Everything is a polygon.

---

## Example Brains

### 🔬 Benchmark Brain

Ignores VLM output. Generates random clicks with matching colored rectangles. Visual validation that coordinates, overlays, and cursor align:

```python
import random
from franz import actions, overlays, click, box

SYSTEM_PROMPT: str = "Say anything."

def on_vlm_response(text: str) -> str:
    amount = random.randint(1, 6)
    for step in range(amount):
        x = random.randint(50, 950)
        y = random.randint(50, 950)
        r = random.randint(0, 255)
        g = random.randint(0, 255)
        b = random.randint(0, 255)
        color = "#" + format(r,"02x") + format(g,"02x") + format(b,"02x")
        actions(click(x, y))
        overlays(box(x-15, y-15, x+15, y+15, str(step+1), color, ""))
    return "benchmark: " + str(amount) + " clicks"
```

### 🌐 Desktop Explorer

Two-persona pattern. The VLM describes what it wants to do. A second VLM call with the screenshot translates intent into precise tool calls:

```python
def on_vlm_response(text: str) -> str:
    # Capture fresh screenshot
    proc = subprocess.run([sys.executable, "win32.py", "capture", ...], capture_output=True)
    image_b64 = base64.b64encode(proc.stdout).decode("ascii")
    
    # Ask executor: "given this intent and this screenshot, output tool calls"
    executor_response = call_vlm(EXECUTOR_PROMPT, text, image_b64)
    
    # Parse and push: click(500, 980) → actions(click(500, 980))
    for match in re.finditer(r"(\w+)\(([^)]*)\)", executor_response):
        # ... parse and push into action pipe
    
    return text
```

### ♟️ Chess Player

Draws a coordinate grid overlay every turn to force the VLM to think in normalized coordinates instead of chess notation. Uses drag_start/drag_end to physically move pieces on chess.com.

### 🔍 Deep Research Entity

Opens Notepad. Types "What do you want to research?" Waits for user input. When it sees "FRANZ START", it opens Chrome, searches X.com, copies findings back into Notepad. The entity communicates with the user through a text file on the desktop.

*Full implementations of all brains are included in the repository.*

---

## Sharing Brains

```
1. Send someone your brain.py
2. They drop it in their franz/ folder
3. python router.py
```

The frozen files never change. Any brain that imports from `franz` and defines `SYSTEM_PROMPT` + `on_vlm_response` will work.

---

## Why Entity, Not Agent

An **agent** is an engineering artifact:

```
tools + planner + memory + safety filters + context window + skill registry + ...
```

An **entity** is a living loop:

```
see → speak → act → see the consequences → speak again
```

No persistent memory beyond one string. No tools beyond physical I/O. No safety mechanism beyond the story it tells itself.

### The Narrative Identity Principle

In psychology, [narrative identity](https://en.wikipedia.org/wiki/Narrative_identity) is the internalized story a person constructs about themselves that gives their life meaning, continuity, and coherence. It's not an external rulebook — it's an emergent property of ongoing self-narration.

Franz entities work the same way. Each turn, the model's output becomes its own input for the next turn. Over turns, a story forms. The entity that says "I see the desktop, I want to explore the Start menu" and then sees the Start menu open has just experienced cause and effect through its own narrative. Over 20 turns, this compounds into behavior that is coherent, adaptive, and purposeful — not because anyone programmed purpose into it, but because **narratives naturally develop purpose**.

A well-designed system prompt creates an entity that avoids destructive actions not because it's forbidden to, but because its narrative self-model values continued operation. The safety is intrinsic to the story, not imposed by external constraints. We call this **narrative safety** — the principle that an entity embedded in a coherent self-narrative will naturally preserve the conditions for that narrative to continue.

### What About Scale?

An ant has approximately 250,000 neurons. A colony of ants builds cities, farms fungi, wages wars, and maintains infrastructure that persists across generations. No individual ant has a plan. No ant has memory of the colony's history. Each ant follows simple rules in response to immediate sensory input — and from this, extraordinary complexity emerges.

Qwen3-VL-2B has 2 billion parameters. It's not intelligent by any current standard. It will click the wrong button. It will misread text. It will get confused and try the same thing three times.

**But it will also recover.** It will see that its click didn't work, and it will try something else. It will notice that Notepad has opened and proceed to the next step. Give it 20 turns, and something is there that wasn't there at turn 1.

Franz doesn't require a powerful model. It requires a **loop** — perception, action, consequence, adaptation. The same loop that drives ant colonies, immune systems, and every other complex adaptive system in nature.

> *The difference between a thermostat and a living thing is not complexity. It's that a living thing acts, observes the result, and acts differently next time.*

### What Could Be Built

If you take this seriously — a stateless entity with eyes and hands, talking to itself in a loop — the implications go beyond desktop automation:

- **Self-improving systems.** An entity that opens a code editor, reads its own brain.py, modifies it, saves it, and restarts. A brain that rewrites itself.

- **Multi-entity collaboration.** Multiple Franz instances running on different machines, communicating through shared files or web interfaces. No coordination protocol — just entities reading what other entities wrote.

- **Physical control.** A computer connected to a robot, a CNC machine, a 3D printer, a drone controller. The entity sees the camera feed, pushes button clicks on the control software. The same loop that opens Notepad can operate a lathe.

- **Research agents.** An entity that reads papers, takes notes, searches the web, synthesizes findings — not through API calls to a search tool, but by physically operating a browser like a human researcher would.

- **Teaching itself.** An entity that opens YouTube tutorials, watches them, tries to follow along in another window. Learning by doing, in a loop, with real feedback.

These aren't hypothetical architectures. They're all just brain.py files. The plumbing is done. The pipes work. What flows through them is limited only by what a VLM can see and what Python can do.

---

## Create Brains with AI

Copy this into a conversation with any AI assistant (Claude, GPT, Grok, Gemini) to have it generate Franz brains for you:

<details>
<summary><strong>📋 Click to expand: Brain-authoring system prompt</strong></summary>

```
You generate brain.py files for the Franz desktop-control framework.

== WHAT FRANZ IS ==

A loop: screenshot → VLM → on_vlm_response(text) → actions execute → new screenshot → overlays draw → repeat.
The user edits ONLY brain.py. Everything else is frozen.

== BRAIN.PY STRUCTURE ==

1. Imports from franz (frozen pipe system)
2. Config variables (module-level, all optional with sane defaults)
3. SYSTEM_PROMPT: str — sent to VLM every turn with the screenshot
4. def on_vlm_response(text: str) -> str — receives VLM output, returns context for next turn

== AVAILABLE IMPORTS ==

from franz import actions        # push action dict into action queue
from franz import overlays       # push overlay dict into overlay queue
from franz import click          # click(x, y) -> dict
from franz import double_click   # double_click(x, y) -> dict
from franz import right_click    # right_click(x, y) -> dict
from franz import type_text      # type_text(text) -> dict
from franz import press_key      # press_key(name) -> dict
from franz import hotkey         # hotkey(combo) -> dict
from franz import scroll_up      # scroll_up(x, y) -> dict
from franz import scroll_down    # scroll_down(x, y) -> dict
from franz import drag_start     # drag_start(x, y) -> dict
from franz import drag_end       # drag_end(x, y) -> dict
from franz import dot            # dot(x, y, label="", color="#00ff00") -> dict
from franz import box            # box(x1, y1, x2, y2, label="", stroke="#ff6600", fill="") -> dict
from franz import line           # line([[x,y],...], label="", color="#4488ff") -> dict

Coordinates: integers 0-1000. (0,0)=top-left, (1000,1000)=bottom-right.
press_key names: enter, tab, escape, backspace, delete, up, down, left, right, f1-f12
hotkey combos: ctrl+c, alt+f4, ctrl+shift+s, win, alt+tab, ctrl+v

== CONFIG VARIABLES ==

VLM_ENDPOINT_URL: str = "http://127.0.0.1:1235/v1/chat/completions"
VLM_MODEL_NAME: str = "qwen3-vl-2b"
VLM_TEMPERATURE: float = 0.4
VLM_TOP_P: float = 0.9
VLM_MAX_TOKENS: int = 300
SERVER_HOST: str = "127.0.0.1"
SERVER_PORT: int = 1234
CAPTURE_REGION: str = ""
CAPTURE_WIDTH: int = 640   # 0 = no resize
CAPTURE_HEIGHT: int = 640  # 0 = no resize
CAPTURE_DELAY_SECONDS: float = 2.5
ACTION_DELAY_SECONDS: float = 0.3
SHOW_CURSOR: bool = True

== PIPE MECHANICS ==

actions(dict) appends to action queue. overlays(dict) appends to overlay queue.
Nothing executes until on_vlm_response returns.
System drains actions first (executes in order), takes screenshot, then drains overlays (draws in order).
Empty queues = nothing happens. System doesn't care.

== INSIDE on_vlm_response ==

Anything in Python stdlib:
- Parse with re, json, string ops
- HTTP calls with urllib.request
- Screenshot: subprocess.run([sys.executable, "win32.py", "capture", "--width", "0", "--height", "0"], capture_output=True).stdout → PNG bytes
- Cursor pos: subprocess.run([sys.executable, "win32.py", "cursor_pos"], capture_output=True).stdout → "x,y\n"
- Import any stdlib module
- Return any string (becomes "Previous: {string}" context next turn)

== TWO-PERSONA PATTERN ==

SYSTEM_PROMPT: natural language observer/planner.
Inside function: second VLM call with executor prompt that outputs tool calls.
2B models work better with separated observe vs. execute.

== STYLE ==

Flat linear code. No classes. No decorators. if/elif chains.
Inline logic. Beginner-readable. Every line self-explanatory.
```

</details>

---

## Project Structure

```
franz/
├── brain.py       user-editable     config + prompt + on_vlm_response
├── franz.py       frozen            pipes, action helpers, overlay helpers
├── router.py      frozen            engine loop, VLM calls, HTTP server
├── win32.py       frozen            screen capture, mouse, keyboard, region selector
├── panel.html     frozen            browser dashboard with canvas rendering
└── logs/          auto-created      session screenshots + turn transcripts
```

---

<div align="center">

### The plumbing is done. The pipes work.

### What flows through them is up to you.

---

Built by **Wojciech Gabrys** and **Claude Opus 4**

*With contributions from Grok and ChatGPT*

*2025*

</div>
