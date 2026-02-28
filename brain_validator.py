"""Franz brain -- coordinate and overlay validation benchmark.

Generates random clicks and matching overlay rectangles.
Ignores VLM output. Use to verify that coordinates, overlays,
and cursor position are all aligned correctly.

Run with: python router.py
"""

import random
from franz import actions
from franz import overlays
from franz import click
from franz import box


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
ACTION_DELAY_SECONDS: float = 0.5
SHOW_CURSOR: bool = True


SYSTEM_PROMPT: str = """You are a test dummy. Say anything. It does not matter."""


def on_vlm_response(text: str) -> str:

    amount = random.randint(1, 6)

    for step in range(amount):

        x = random.randint(50, 950)
        y = random.randint(50, 950)

        red = random.randint(0, 255)
        green = random.randint(0, 255)
        blue = random.randint(0, 255)
        color = "#" + format(red, "02x") + format(green, "02x") + format(blue, "02x")

        half = 15
        label = str(step + 1) + ": [" + str(x) + "," + str(y) + "]"

        actions(click(x, y))

        overlays(box(x - half, y - half, x + half, y + half, label, color, ""))

    return "benchmark turn done, " + str(amount) + " random clicks"
