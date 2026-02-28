<div align="center">

```
 ███████╗██████╗  █████╗ ███╗   ██╗███████╗
 ██╔════╝██╔══██╗██╔══██╗████╗  ██║╚══███╔╝
 █████╗  ██████╔╝███████║██╔██╗ ██║  ███╔╝ 
 ██╔══╝  ██╔══██╗██╔══██║██║╚██╗██║ ███╔╝  
 ██║     ██║  ██║██║  ██║██║ ╚████║███████╗
 ╚═╝     ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═══╝╚══════╝
```

### A Vision Language Model sees your screen. You give it a brain.

*Three frozen pipes. Swappable brains. Zero dependencies.*

[![Python 3.13](https://img.shields.io/badge/Python-3.13-blue?logo=python&logoColor=white)](#) [![Windows 11](https://img.shields.io/badge/Windows-11-0078D6?logo=windows&logoColor=white)](#) [![No pip install](https://img.shields.io/badge/pip%20install-nothing-brightgreen)](#) [![License: MIT](https://img.shields.io/badge/License-MIT-yellow)](#)

</div>

---

## The Idea

Most agentic AI systems share **tools**, **skills**, or **MCP servers**.

Franz shares **brains**.

A brain is a single `.py` file. It decides what the VLM sees, what actions happen on your desktop, and what story gets told back. You swap one brain for another with one word:

```
python router.py chess.py
python router.py paint_cat.py
python router.py my_experiment.py
```

The engine never changes. The pipes never change. The dashboard never changes.
Only the brain changes — and the brain is the only file you ever write.

---

## What Makes Franz Different

| Traditional Agent | Franz |
|---|---|
| Shares tools and skills | **Shares brains** |
| Accumulates context over turns | **Stateless API — feeds itself each turn** |
| Memory is text only | **Memory is text AND visual annotations** |
| Prompt engineering is hidden | **The prompt IS the scenario file** |
| Complex framework, many files | **3 frozen files + 1 brain file** |
| Needs pip install | **Zero dependencies, stdlib only** |

### The Self-Feeding Loop

Franz doesn't accumulate a growing conversation. Every turn, it receives:

1. **Its own previous output** (parsed and fed back as user text)
2. **A fresh screenshot** with annotations drawn on it

That's it. The VLM has no memory except what it wrote last turn and what it can see on the screen. The "story" field in the JSON becomes the VLM's memory — what it writes, it reads next time. What it draws as annotations, it sees next time.

This means a 2B parameter model can run indefinitely without context overflow. The story is the memory. The annotations are the visual memory. Both fit in a single turn.

### Visual Memory for Small Models

Large models can reason from raw screenshots. Small models (2B) struggle — they need help knowing where to look. Franz solves this by drawing directly on the screenshot before the VLM sees it:

```
 ┌──────────────────────────────┐
 │  Raw Screenshot              │
 │                              │
 │    (just pixels, no context) │
 └──────────────┬───────────────┘
                │
         overlay annotations
                │
 ┌──────────────▼───────────────┐
 │  Annotated Screenshot        │
 │                              │
 │  ← orange arrow (last move)  │
 │  ← blue arrows (alternatives)│
 │  ← "Step 3" label (HUD)     │
 │  ← red "FAILED" marker       │
 │                              │
 │  The VLM sees ALL of this    │
 └──────────────────────────────┘
```

The brain decides what gets drawn. The VLM sees the result. This is how a 2B model can play chess — it doesn't need to remember the board, it sees arrows showing what happened.

---

## Quick Start

### What You Need

- **Windows 11** with **Python 3.13**
- A VLM server running locally (Ollama, LM Studio, vLLM, etc.) serving OpenAI-compatible `/v1/chat/completions`
- **Google Chrome** (latest)

### Three Steps

```
Step 1:  Clone or download this repository

         franz/
           ├── win32.py       ← frozen, never edit
           ├── router.py      ← frozen, never edit
           ├── panel.html     ← frozen, never edit
           ├── chess.py        ← example brain
           ├── paint_cat.py    ← example brain
           └── test_tools.py   ← example brain

Step 2:  Start your VLM server with a vision model loaded

Step 3:  Run Franz with a brain:

         python router.py chess.py
```

Chrome opens. Franz starts thinking. You watch.

> **No `pip install`. No `config.json`. No environment variables.**
> Python 3.13 + Windows 11 stdlib + ctypes. That's everything.

---

## How It Works

### The Loop

```
 ┌──────────────────────────────────────────────────────────────────┐
 │                    THE FRANZ LOOP                                │
 │                                                                  │
 │  ┌─────────┐    raw text     ┌──────────┐    actions    ┌─────┐│
 │  │   VLM   │ ──────────────► │  route() │ ────────────► │win32││
 │  │ Server  │                 │ (brain)  │               │ .py ││
 │  │         │                 │          │  overlays     └──┬──┘│
 │  │         │                 └────┬─────┘ ─────┐           │   │
 │  │         │                      │             │    (desktop  │
 │  │         │                      │ user_text   │    changes) │
 │  │         │                      │             │           │   │
 │  │         │                      │             ▼           │   │
 │  │         │  annotated    ┌──────┴──────┐  overlays       │   │
 │  │         │  image +      │  panel.html │◄─────────       │   │
 │  │         │  user_text    │  (Chrome)   │          ┌──────▼──┐│
 │  │         │◄──────────────│  draws      │◄─────────│ win32.py││
 │  │         │               │  overlays   │  PNG b64 │ capture ││
 │  └─────────┘               └─────────────┘          └─────────┘│
 │                                                                  │
 │        Every turn: parse → execute → capture → annotate → ask   │
 └──────────────────────────────────────────────────────────────────┘
```

### The Architecture

```
 ┌─────────────────────────────────────────────────────────────────┐
 │                        YOUR COMPUTER                            │
 │                                                                 │
 │  ┌────────────────┐                                             │
 │  │   YOUR BRAIN   │   ← the only file you write                │
 │  │   chess.py     │                                             │
 │  │   paint_cat.py │   Contains:                                 │
 │  │   anything.py  │     CONFIG    - all settings                │
 │  │                │     route()   - parse VLM, decide actions   │
 │  │                │     run_cycle - pipeline order               │
 │  │                │     build_overlays - visual feedback         │
 │  └───────┬────────┘                                             │
 │          │ imported by                                           │
 │          ▼                                                       │
 │  ┌──────────────┐     subprocess     ┌──────────────────────┐  │
 │  │              │ ─────────────────► │                      │  │
 │  │  router.py   │                    │     win32.py         │  │
 │  │  (frozen)    │ ◄───────────────── │     (frozen)         │  │
 │  │              │   stdout bytes     │                      │  │
 │  │  HTTP server │                    │  screen capture      │  │
 │  │  VLM client  │                    │  mouse / keyboard    │  │
 │  │  main loop   │                    │  region selector     │  │
 │  │              │                    │  image compare        │  │
 │  └──────┬───────┘                    └──────────────────────┘  │
 │         │                                                       │
 │         │ HTTP localhost                                         │
 │         │                                                       │
 │  ┌──────▼───────┐                    ┌──────────────────────┐  │
 │  │  panel.html  │                    │   VLM Server         │  │
 │  │  (frozen)    │                    │   (Ollama/LM Studio) │  │
 │  │              │   HTTP             │                      │  │
 │  │  Chrome tab  │ ◄────────────────► │   Qwen3-VL-2B       │  │
 │  │  draws ovl   │                    │   or any model       │  │
 │  │  composites  │                    │                      │  │
 │  └──────────────┘                    └──────────────────────┘  │
 │                                                                 │
 └─────────────────────────────────────────────────────────────────┘
```

### The Data Flow (One Turn)

```
 VLM says: '{"story":"I see a pawn on e2...","do":[{"type":"click",...}]}'
                                    │
                                    ▼
              ┌─────────── route() in your brain ──────────────┐
              │                                                 │
              │  1. Parse JSON                                  │
              │  2. Extract actions: click e2, click e4         │
              │  3. Build overlays: orange arrow e2→e4          │
              │  4. Build user_text: "Your move was e2e4..."    │
              │                                                 │
              │  Returns: RouteResult(user_text, actions, ovl)  │
              └────────────────────┬────────────────────────────┘
                                   │
              ┌────────────────────▼────────────────────────────┐
              │           run_cycle() in your brain             │
              │                                                 │
              │  execute(actions)     ← win32.py clicks         │
              │       ↓                                         │
              │  capture()            ← win32.py screenshots    │
              │       ↓                 (waits 3 seconds first) │
              │  annotate(screenshot, overlays)                 │
              │       ↓               ← panel.html draws arrows │
              │  call_vlm(annotated_image, user_text)           │
              │       ↓               ← sends to Qwen3-VL      │
              │  returns next VLM response                      │
              └─────────────────────────────────────────────────┘
                                   │
                                   ▼
              Next turn starts with this new VLM response
```

---

## The Brain File

A brain is a `.py` file with four things:

### 1. CONFIG

```python
@dataclass(slots=True)
class ScenarioConfig:
    vlm_endpoint_url: str = "http://127.0.0.1:1235/v1/chat/completions"
    vlm_model_name: str = "qwen3-vl-2b"
    vlm_temperature: float = 0.3
    capture_region: str = "150,100,850,950"    # normalized 0-1000
    capture_delay_seconds: float = 3.0
    system_prompt: str = "You are a chess assistant..."
    seed_vlm_text: str = '{"story":"First turn..."}'
    # ... all settings live here
```

### 2. route() — The Parser

```python
def route(raw_vlm_output: str) -> RouteResult:
    # Parse whatever the VLM said
    # Return: user_text (fed back), actions (executed), overlays (drawn)
```

### 3. run_cycle() — The Pipeline

```python
def run_cycle(vlm_response_text, overlays_from_previous,
              capture_fn, execute_fn, annotate_fn, call_vlm_fn):
    result = route(vlm_response_text)
    execute_fn(result.actions)       # do things on desktop
    screenshot = capture_fn()         # take a picture
    annotated = annotate_fn(screenshot, result.overlays)  # draw on it
    next_response = call_vlm_fn(annotated, result.user_text)  # ask VLM
    return next_response, result.overlays
```

### 4. build_overlays() — Visual Feedback

```python
def build_overlays(action_results, screen_changed, user_overlays):
    # Post-process overlays, add fail markers, etc.
    return user_overlays
```

That's the entire contract. Everything else is yours — helper functions, geometry code, custom logic, whatever you need.

---

## Sharing Brains

### How It Works

```
 Alice writes chess.py          →  shares on GitHub
 Bob downloads chess.py         →  drops it in his franz/ folder  
 Bob runs: python router.py chess.py
 Bob is now playing chess with a VLM.

 Carol writes stock_trader.py   →  shares in Discord
 Dave downloads stock_trader.py →  python router.py stock_trader.py
 Dave's VLM is now watching stock charts.
```

No framework to learn. No adapter to write. No compatibility issues. A brain is a self-contained Python file with four functions and a config. Drop it in the folder, run it.

### The Brain Marketplace

Imagine a community where people share brains:

| Brain | Description | Author |
|---|---|---|
| `chess.py` | Plays chess.com as White | @alice |
| `paint_cat.py` | Opens Paint, draws a cat | @bob |
| `test_tools.py` | Tests all Win32 actions | @carol |
| `email_sorter.py` | Reads and categorizes emails | @dave |
| `code_reviewer.py` | Opens VS Code, reviews your PR | @eve |
| `desktop_cleaner.py` | Organizes messy desktop icons | @frank |
| `game_speedrun.py` | Speedruns a specific game | @grace |
| `form_filler.py` | Fills out web forms automatically | @heidi |

Each brain is one file. The system prompt, the parser, the pipeline order, the visual feedback — all in one place. You read it, you understand it, you modify it.

### Why Brains, Not Tools

Traditional agentic systems decompose intelligence into **tools** — small, reusable functions like "click_button" or "read_text". The agent decides which tools to call. This is powerful but complex: tool registries, tool descriptions, tool selection, tool chaining.

Franz flips this. There are no tools. There is one brain that contains the complete strategy for one scenario. The brain parses, decides, annotates, and orchestrates — all in one file. This is less general but vastly simpler and more hackable.

When you share a brain, you're sharing a complete way of seeing and acting. Not a screwdriver — a personality.

---

## Coordinate System

Everything in Franz uses **normalized integers 0 to 1000**.

```
    0,0 ──────────────────── 1000,0
     │                          │
     │     Screen or Region     │
     │                          │
     │          500,500         │
     │            ●             │
     │                          │
     │                          │
   0,1000 ─────────────────── 1000,1000
```

- Top-left is `0,0`
- Bottom-right is `1000,1000`
- Center is `500,500`
- `win32.py` converts these to physical pixels internally
- The VLM works with these coordinates
- Overlays use these coordinates
- Actions use these coordinates

If you set `capture_region: str = "150,100,850,950"`, the coordinates 0-1000 map to that sub-region of the screen, not the full screen.

### Selecting a Region

```
python win32.py select_region
```

A transparent overlay appears. Draw a rectangle. It prints normalized coordinates:

```
150,100,850,950
```

Paste that into your brain's `capture_region` config field.

---

## Overlays

Overlays are polygons drawn on the screenshot before the VLM sees it.

### Overlay Dict Shape

```python
{
    "points": [[x1,y1], [x2,y2], ...],     # normalized 0-1000
    "closed": True,                          # polygon or polyline
    "stroke": "#ff6600",                     # outline color
    "fill": "rgba(255,120,0,0.35)",          # fill color or ""
    "label": "e2e4",                         # text label or ""
    "label_position": [500, 40],             # where to place label
    "label_style": {                         # label appearance
        "font_size": 12,
        "bg": "#cc5500",
        "color": "#ffffff",
        "align": "center"
    }
}
```

### What You Can Draw

| Shape | How |
|---|---|
| Rectangle | 4 points, closed=True |
| Circle | N points on circumference, closed=True |
| Arrow | 7-point polygon (shaft + head), closed=True |
| Line | 2 points, closed=False |
| Dot with label | 1 point, label="text" |
| Any polygon | N points, closed=True |

### Why This Matters

The VLM **sees** the overlays. They become part of the image. This means:

- Draw an arrow → VLM sees the arrow and can reference it
- Draw "FAILED" in red → VLM knows something went wrong
- Draw step numbers → VLM knows where it is in a process
- Draw boxes around regions → VLM focuses on those areas

For a 2B model, this visual scaffolding is the difference between "confused by pixels" and "understands what happened."

---

## Actions

Actions are executed on your real desktop via `win32.py` subprocesses.

| Action | Description | Params |
|---|---|---|
| `click` | Left click at bbox center | — |
| `double_click` | Double left click | — |
| `right_click` | Right click | — |
| `type` | Type text string | text to type |
| `key` | Press single key | key name |
| `hotkey` | Key combination | "ctrl+c" |
| `scroll_up` | Scroll wheel up | click count |
| `scroll_down` | Scroll wheel down | click count |
| `drag_start` | Begin drag at bbox | — |
| `drag_end` | End drag at bbox | — |

### Action Dict Shape

```python
{
    "type": "click",
    "bbox_2d": [450, 300, 470, 320],     # normalized 0-1000
    "params": ""                          # extra params
}
```

---

## Example Brains Included

### 🎯 chess.py — Chess.com Observer

```
python router.py chess.py
```

Watches a chess.com game, analyzes the board, makes moves as White by clicking pieces. Draws orange arrows for chosen moves and blue arrows for alternatives.

**Setup:** Open chess.com, start a game as White. Run `python win32.py select_region` and draw a box around the board. Paste coordinates into `capture_region`.

### 🎨 paint_cat.py — Paint Artist

```
python router.py paint_cat.py
```

Opens Microsoft Paint and draws a cat step by step. Uses clicks, drags, and typing. Each turn does one small step: open Paint, select brush, draw head, draw ears, etc.

**Setup:** Just run it. It starts from the desktop.

### 🔧 test_tools.py — Action Tester

```
python router.py test_tools.py
```

Systematically tests every action type: opens Notepad, types text, uses hotkeys, scrolls, then opens Paint and tests drag/double-click/right-click. A regression test for the entire system.

**Setup:** Just run it. It starts from the desktop.

---

## Making Your Own Brain

### The Minimal Brain

```python
import json
from dataclasses import dataclass

@dataclass(slots=True)
class ScenarioConfig:
    vlm_endpoint_url: str = "http://127.0.0.1:1235/v1/chat/completions"
    vlm_model_name: str = "qwen3-vl-2b"
    vlm_temperature: float = 0.5
    vlm_top_p: float = 0.9
    vlm_max_tokens: int = 600
    server_host: str = "127.0.0.1"
    server_port: int = 1234
    capture_region: str = ""
    capture_width: int = 640
    capture_height: int = 640
    capture_delay_seconds: float = 2.0
    system_prompt: str = "You see a screenshot. Describe what you see as JSON."
    seed_vlm_text: str = '{"text":"Starting up. Let me look around."}'
    change_threshold: float = 0.01

CONFIG: ScenarioConfig = ScenarioConfig()

@dataclass(slots=True)
class RouteResult:
    user_text: str
    actions: list[dict[str, str | int | list[int]]]
    overlays: list[dict[str, str | bool | float | list[list[int | float]]]]

def route(raw_vlm_output: str) -> RouteResult:
    return RouteResult(raw_vlm_output, [], [])

def run_cycle(vlm_response_text, overlays_from_previous,
              capture_fn, execute_fn, annotate_fn, call_vlm_fn):
    result = route(vlm_response_text)
    execute_fn(result.actions)
    screenshot = capture_fn()
    annotated = annotate_fn(screenshot, result.overlays)
    next_response = call_vlm_fn(annotated, result.user_text)
    return next_response, result.overlays

def build_overlays(action_results, screen_changed, user_overlays):
    return user_overlays
```

Save as `observer.py`. Run `python router.py observer.py`. The VLM observes your screen and talks about what it sees. No actions, no overlays. The simplest possible brain.

### Growing the Brain

From there, you add capabilities:

1. **Parse the VLM JSON** → extract actions from the `"do"` field
2. **Build overlays** → draw markers where actions will happen
3. **Customize the pipeline** → change the order of capture/execute/annotate
4. **Add helper functions** → arrow builders, geometry, anything

Each brain is self-contained. Import whatever you need from Python's stdlib. Add as many helper functions as you want. The three zone functions (`route`, `run_cycle`, `build_overlays`) are the interface — everything else is yours.

---

## Technical Reference

### File Responsibilities

```
 ┌──────────────────────────────────────────────────────────┐
 │ win32.py (frozen)                                        │
 │                                                          │
 │  Called as subprocess. One invocation does one thing.     │
 │  Knows nothing about VLMs, brains, or dashboards.        │
 │                                                          │
 │  Commands: capture, click, double_click, right_click,    │
 │  type_text, press_key, hotkey, scroll_up, scroll_down,   │
 │  drag, compare, select_region                            │
 │                                                          │
 │  All ctypes bindings, Win32 structures, screen capture,  │
 │  input simulation, PNG encoding, region selector GUI.    │
 ├──────────────────────────────────────────────────────────┤
 │ router.py (frozen)                                       │
 │                                                          │
 │  The engine. Run: python router.py <brain.py>            │
 │  Loads brain via importlib. Runs the loop forever.       │
 │                                                          │
 │  - HTTP server serving panel.html, /state, /frame,       │
 │    /annotated endpoints                                  │
 │  - Subprocess wrappers calling win32.py                  │
 │  - VLM HTTP client using urllib.request                  │
 │  - The while True loop calling brain's run_cycle()       │
 │  - Thread-safe state shared with HTTP server             │
 ├──────────────────────────────────────────────────────────┤
 │ panel.html (frozen)                                      │
 │                                                          │
 │  Browser dashboard. Polls /state every 400ms.            │
 │  Fetches raw screenshot + overlay list from /frame.      │
 │  Draws overlays on canvas. Composites to PNG.            │
 │  POSTs annotated image back to /annotated.               │
 │  Displays VLM text and server phase.                     │
 ├──────────────────────────────────────────────────────────┤
 │ your_brain.py (yours)                                    │
 │                                                          │
 │  CONFIG      - all settings as a dataclass               │
 │  route()     - parse VLM output → actions + overlays     │
 │  run_cycle() - pipeline: what order to do things         │
 │  build_overlays() - post-process visual feedback         │
 │  + any helper functions you need                         │
 └──────────────────────────────────────────────────────────┘
```

### The Annotation Pipeline Detail

```
 router.py calls          panel.html receives       panel.html draws
 annotate_fn()            /frame with:               on canvas:
      │                                               
      │                   ┌─────────────────────┐    ┌─────────────────┐
      │                   │ raw_b64: "iVBOR..." │    │ ████████████████│
      │                   │                     │    │ ██ screenshot ██│
      ├──────────────────►│ overlays: [         │───►│ ██            ██│
      │                   │   {points, stroke,  │    │ ██  ←overlays ██│
      │                   │    fill, label...}, │    │ ██  drawn on  ██│
      │                   │   ...               │    │ ██  top       ██│
      │                   │ ]                   │    │ ████████████████│
      │                   └─────────────────────┘    └────────┬────────┘
      │                                                       │
      │                                                canvas.toBlob()
      │                                                       │
      │                   ┌─────────────────────┐             │
      │                   │ POST /annotated     │◄────────────┘
      │◄──────────────────│ {seq, image_b64}    │
      │                   └─────────────────────┘
      │
      │  annotated_b64 now contains the
      │  screenshot WITH overlays baked in
      │
      ▼  sent to VLM as the image
```

### Thread Model

```
 ┌──────────────────────┐     ┌──────────────────────┐
 │   Engine Thread       │     │   HTTP Server Thread  │
 │   (daemon)            │     │   (main thread)       │
 │                       │     │                       │
 │   while True:         │     │   serve_forever()     │
 │     run_cycle()       │     │                       │
 │     wait for panel    │◄───►│   GET /state          │
 │     call VLM          │     │   GET /frame          │
 │     repeat            │     │   POST /annotated     │
 │                       │     │                       │
 └───────────┬───────────┘     └───────────────────────┘
             │
             │ threading.Event
             │ (annotated_ready)
             │
             │ panel.html POSTs the composited image
             │ → HTTP handler sets the event
             │ → engine thread wakes up and continues
```

---

## win32.py Command Reference

Test from terminal with no project context:

```bash
# Capture full screen
python win32.py capture --width 640 --height 640 > test.png

# Capture a region
python win32.py capture --region 150,100,850,950 --width 640 --height 640 > board.png

# Click at a position
python win32.py click --bbox 500,500,520,520

# Click within a region
python win32.py click --bbox 500,500,520,520 --region 150,100,850,950

# Type text
python win32.py type_text --text "Hello World"

# Press a key
python win32.py press_key --key enter

# Key combination
python win32.py hotkey --keys "ctrl+c"

# Scroll
python win32.py scroll_up --bbox 500,500,520,520 --clicks 3
python win32.py scroll_down --bbox 500,500,520,520 --clicks 5

# Drag
python win32.py drag --from 200,200,220,220 --to 600,600,620,620

# Compare two screenshots
python win32.py compare --file_a before.png --file_b after.png

# Interactive region selector
python win32.py select_region
```

---

## FAQ

**Q: Do I need to install anything with pip?**
No. Zero pip dependencies. Python 3.13 stdlib + ctypes only.

**Q: What VLM models work?**
Any model served via OpenAI-compatible API. Tested with Qwen3-VL-2B via LM Studio. Larger models work better but aren't required.

**Q: Can I use this on macOS or Linux?**
No. win32.py uses Windows-only ctypes bindings. Windows 11 only.

**Q: Why subprocess for win32.py instead of importing directly?**
Intentional isolation. Each win32.py call is a clean process. No shared state, no GDI handle leaks, no ctypes conflicts with the HTTP server thread. The overhead (~50ms per call) is negligible compared to VLM inference time.

**Q: How does the VLM "see" annotations?**
panel.html draws polygons on a canvas layer on top of the screenshot, then composites both layers into a single PNG. The VLM receives this composited image — it literally sees colored arrows, boxes, and labels as part of the picture.

**Q: What if my brain has a syntax error?**
router.py catches the import error and prints the exception with file and line number. Fix the file, restart.

**Q: Can two brains run at the same time?**
Not on the same port. But you can change `server_port` in each brain's CONFIG and run them simultaneously on different ports.

---

## The Philosophy

Franz is plumbing.

The three frozen files are pipes. Data flows through them: screenshots in, actions out, images annotated, VLM called. The pipes don't think. They don't decide. They don't know what chess is or what Paint is.

The brain thinks. The brain is one file that you write. It decides what the VLM sees, what happens on the desktop, and what gets fed back. When you share a brain, you're sharing a complete way of perceiving and acting on a computer screen.

Traditional agentic systems build intelligence into the framework. Franz builds intelligence into the scenario. The framework is just plumbing — and plumbing should be boring.

```
 ┌────────────────────────────────────────────────────────┐
 │                                                        │
 │   "Three frozen pipes. Swappable brains.               │
 │    Download three files. Write one brain.               │
 │    Run one command. Build anything."                    │
 │                                                        │
 └────────────────────────────────────────────────────────┘
```

---

<div align="center">

**[Get Started](#quick-start)** · **[Example Brains](#example-brains-included)** · **[Make Your Own](#making-your-own-brain)** · **[Share It](#sharing-brains)**

</div>
