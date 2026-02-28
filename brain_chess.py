"""Franz brain -- Chess Player Entity

A 2B VLM entity that plays chess on chess.com as white pieces.
Crop the capture region to show ONLY the chessboard.

The entity uses two personas:
  1. Chess Analyst: looks at the board with a coordinate grid overlay,
     describes piece positions in normalized coordinates, picks a move.
  2. Move Executor: receives the move description + screenshot with grid,
     produces drag_start and drag_end to physically move the piece.

A coordinate grid is drawn EVERY turn so the VLM always thinks
in normalized 0-1000 space, not chess notation.

Run with: python router.py
  - Crop EXACTLY to the chessboard borders (no side panels, no chat).
  - You play as WHITE (pieces start at the bottom of the screen).

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
from franz import drag_start
from franz import drag_end
from franz import dot
from franz import box
from franz import line


VLM_ENDPOINT_URL: str = "http://127.0.0.1:1235/v1/chat/completions"
VLM_MODEL_NAME: str = "qwen3-vl-2b"
VLM_TEMPERATURE: float = 0.5
VLM_TOP_P: float = 0.9
VLM_MAX_TOKENS: int = 400
SERVER_HOST: str = "127.0.0.1"
SERVER_PORT: int = 1234
CAPTURE_REGION: str = ""
CAPTURE_WIDTH: int = 600
CAPTURE_HEIGHT: int = 600
CAPTURE_DELAY_SECONDS: float = 3.5
ACTION_DELAY_SECONDS: float = 0.8
SHOW_CURSOR: bool = True


SYSTEM_PROMPT: str = """You are a chess-playing entity. You see a chessboard screenshot.
A colored grid is drawn on the board showing normalized coordinates from 0 to 1000.
(0,0) is the TOP-LEFT corner. (1000,1000) is the BOTTOM-RIGHT corner.

The grid lines show positions at 0, 125, 250, 375, 500, 625, 750, 875, 1000.
Each square on the 8x8 board is about 125 units wide and 125 units tall.

You play WHITE. White pieces are at the BOTTOM of the board (high y values like 875, 1000).
Black pieces are at the TOP (low y values like 0, 125).

Square centers (approximate normalized coordinates):
  Column: a=63 b=188 c=313 d=438 e=563 f=688 g=813 h=938
  Row 8 (top):    y=63
  Row 7:          y=188
  Row 6:          y=313
  Row 5:          y=438
  Row 4:          y=563
  Row 3:          y=688
  Row 2:          y=813
  Row 1 (bottom): y=938

IMPORTANT RULES:
- DO NOT use chess notation like e2e4 or Nf3.
- ONLY describe moves using normalized coordinates.
- Say: "I will drag the piece at (x1, y1) to (x2, y2)"
- Look at the grid lines and labeled points on the screenshot to find exact positions.
- Describe what pieces you see and where they are using coordinates.
- Think about which white piece to move and where.
- One move per turn. Describe it clearly.

Example response:
I see the starting position. White pawns are along y=813. Black pawns along y=188.
I want to move the pawn at (313, 813) forward two squares to (313, 563).
I will drag the piece at (313, 813) to (313, 563)."""


EXECUTOR_SYSTEM: str = """You execute a chess move by dragging a piece on the screen.
You see the chessboard screenshot with a coordinate grid overlay.
The grid shows normalized coordinates 0 to 1000.

The user tells you which piece to drag and where.
Find the piece in the screenshot using the grid lines as reference.

Output EXACTLY two lines:
  drag_start(x, y)
  drag_end(x, y)

x and y are integers 0 to 1000. Use the grid to be precise.
Nothing else. No explanation. Just two lines."""


# Grid configuration for 8x8 board
# Lines at 0, 125, 250, 375, 500, 625, 750, 875, 1000
GRID_POSITIONS = [0, 125, 250, 375, 500, 625, 750, 875, 1000]
SQUARE_CENTERS_X = [63, 188, 313, 438, 563, 688, 813, 938]
SQUARE_CENTERS_Y = [63, 188, 313, 438, 563, 688, 813, 938]
COLUMN_LETTERS = ["a", "b", "c", "d", "e", "f", "g", "h"]
ROW_NUMBERS = ["8", "7", "6", "5", "4", "3", "2", "1"]


def on_vlm_response(text: str) -> str:

    # ==========================================
    # STEP 1: Draw the coordinate grid overlay
    # ==========================================
    # This grid is drawn EVERY turn so the VLM always sees
    # normalized coordinates on the board, not chess squares.

    # Vertical grid lines (columns)
    for gx in GRID_POSITIONS:
        overlays(line([[gx, 0], [gx, 1000]], str(gx), "#00ffff"))

    # Horizontal grid lines (rows)
    for gy in GRID_POSITIONS:
        overlays(line([[0, gy], [1000, gy]], str(gy), "#00ffff"))

    # Labeled dots at square centers (every other square to avoid clutter)
    for col_idx in range(8):
        for row_idx in range(8):
            # Label every other square in a checkerboard pattern
            if (col_idx + row_idx) % 2 == 0:
                cx = SQUARE_CENTERS_X[col_idx]
                cy = SQUARE_CENTERS_Y[row_idx]
                label = str(cx) + "," + str(cy)
                overlays(dot(cx, cy, label, "#ffff00"))

    # Corner markers with big labels so model never forgets coordinate system
    overlays(dot(0, 0, "0,0 TOP-LEFT", "#ff0000"))
    overlays(dot(1000, 0, "1000,0 TOP-RIGHT", "#ff0000"))
    overlays(dot(0, 1000, "0,1000 BOT-LEFT", "#ff0000"))
    overlays(dot(1000, 1000, "1000,1000 BOT-RIGHT", "#ff0000"))

    # White side indicator
    overlays(line([[0, 950], [1000, 950]], "=== WHITE SIDE ===", "#ffffff"))

    # ==========================================
    # STEP 2: Check if entity is just observing
    # ==========================================
    text_lower = text.lower()
    has_drag = "drag" in text_lower and ("piece at" in text_lower or "from" in text_lower)

    if not has_drag:
        # Entity is analyzing but hasn't decided on a move yet
        overlays(dot(500, 500, "analyzing...", "#ffff00"))
        return text

    # ==========================================
    # STEP 3: Take fresh screenshot for executor
    # ==========================================
    screenshot_proc = subprocess.run(
        [sys.executable, "win32.py", "capture", "--width", "0", "--height", "0"],
        capture_output=True,
    )
    if not screenshot_proc.stdout:
        return text

    screenshot_b64 = base64.b64encode(screenshot_proc.stdout).decode("ascii")

    # ==========================================
    # STEP 4: Ask executor to produce the drag
    # ==========================================
    request_body = json.dumps({
        "model": VLM_MODEL_NAME,
        "temperature": 0.05,
        "max_tokens": 60,
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
        overlays(dot(500, 500, "executor failed", "#ff0000"))
        return text

    # ==========================================
    # STEP 5: Parse drag_start and drag_end
    # ==========================================
    start_x = -1
    start_y = -1
    end_x = -1
    end_y = -1

    for found in re.finditer(r"(\w+)$([^)]*)$", executor_text):
        name = found.group(1).strip().lower()
        args = found.group(2).strip()
        parts = args.split(",")

        if name == "drag_start" and len(parts) >= 2:
            start_x = int(parts[0].strip())
            start_y = int(parts[1].strip())

        elif name == "drag_end" and len(parts) >= 2:
            end_x = int(parts[0].strip())
            end_y = int(parts[1].strip())

    # Only push if we got both start and end
    if start_x >= 0 and start_y >= 0 and end_x >= 0 and end_y >= 0:
        actions(drag_start(start_x, start_y))
        actions(drag_end(end_x, end_y))

        # Draw the move: green dot at start, red dot at end, arrow line
        overlays(dot(start_x, start_y, "FROM " + str(start_x) + "," + str(start_y), "#00ff00"))
        overlays(dot(end_x, end_y, "TO " + str(end_x) + "," + str(end_y), "#ff4444"))
        overlays(line([[start_x, start_y], [end_x, end_y]], "move", "#ffffff"))
    else:
        overlays(dot(500, 500, "could not parse move", "#ff8800"))

    return text
