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
    system_prompt: str = (
        "You are an artist assistant. You see a Windows 11 desktop screenshot.\n"
        "Your goal: open Microsoft Paint and draw a cat, step by step.\n"
        "\n"
        "Coordinates are [x1,y1,x2,y2], integers 0 to 1000.\n"
        "Top-left is 0,0. Bottom-right is 1000,1000.\n"
        "\n"
        "Available actions: click, double_click, right_click,\n"
        "drag_start, drag_end, type, key, hotkey, scroll_up, scroll_down\n"
        "\n"
        "For drawing lines in Paint, use drag_start then drag_end.\n"
        "For typing text, use type with params.\n"
        "For keyboard shortcuts, use hotkey (e.g. \"ctrl+z\" to undo).\n"
        "\n"
        "Respond with ONLY a JSON object:\n"
        "{\n"
        '  "plan": "What you are doing this step and why.",\n'
        '  "do": [\n'
        '    {"type": "click", "bbox_2d": [x1,y1,x2,y2], "params": ""},\n'
        '    {"type": "drag_start", "bbox_2d": [x1,y1,x2,y2], "params": ""},\n'
        '    {"type": "drag_end", "bbox_2d": [x1,y1,x2,y2], "params": ""}\n'
        "  ],\n"
        '  "next": "What you will do in the next step."\n'
        "}\n"
        "\n"
        "Work step by step. Each turn do ONE small part:\n"
        "  Turn 1: Open Paint (click Start, type mspaint, press Enter)\n"
        "  Turn 2: Select brush tool\n"
        "  Turn 3: Draw head (circle-ish shape with drags)\n"
        "  Turn 4: Draw ears\n"
        "  Turn 5: Draw eyes\n"
        "  Turn 6: Draw nose and mouth\n"
        "  Turn 7: Draw whiskers\n"
        "  Turn 8: Draw body\n"
        "Output ONLY JSON. No other text."
    )
    seed_vlm_text: str = (
        '{"plan":"First I need to open Microsoft Paint. I will click the Start button.'
        ' Start is at the bottom center of the taskbar.",'
        '"do":['
        '{"type":"click","bbox_2d":[490,980,510,1000],"params":""}],'
        '"next":"After Start opens, I will type mspaint and press Enter."}'
    )
    change_threshold: float = 0.005


CONFIG: ScenarioConfig = ScenarioConfig()


@dataclass(slots=True)
class RouteResult:
    user_text: str
    actions: list[dict[str, str | int | list[int]]]
    overlays: list[dict[str, str | bool | float | list[list[int | float]]]]


# =========================================================================
# ZONE 1: THE PARSER
#
# Parse VLM JSON with plan/do/next fields.
# Extract actions directly. Build overlay markers showing where
# actions will be performed (small colored circles at each bbox center).
# =========================================================================

def route(raw_vlm_output: str) -> RouteResult:
    input_text: str = raw_vlm_output
    output_user_text: str = ""
    output_actions: list[dict[str, str | int | list[int]]] = []
    output_overlays: list[dict[str, str | bool | float | list[list[int | float]]]] = []

    parsed: dict[str, object] | None = _extract_json(input_text)
    if parsed is None:
        output_user_text = "Could not parse your response. Output only JSON."
        return RouteResult(output_user_text, output_actions, output_overlays)

    # Extract fields
    plan_text: str = str(parsed.get("plan", ""))
    next_text: str = str(parsed.get("next", ""))
    do_list: object = parsed.get("do", [])

    # Build actions
    if isinstance(do_list, list):
        for action_obj in do_list:
            if not isinstance(action_obj, dict):
                continue
            action_type: object = action_obj.get("type", "")
            bbox_raw: object = action_obj.get("bbox_2d", None)
            params_raw: object = action_obj.get("params", "")
            if not isinstance(action_type, str) or not action_type:
                continue
            bbox_list: list[int] = [490, 490, 510, 510]
            if isinstance(bbox_raw, list) and len(bbox_raw) == 4:
                bbox_list = [
                    max(0, min(1000, int(bbox_raw[0]))),
                    max(0, min(1000, int(bbox_raw[1]))),
                    max(0, min(1000, int(bbox_raw[2]))),
                    max(0, min(1000, int(bbox_raw[3]))),
                ]
            output_actions.append({
                "type": action_type.strip().lower(),
                "bbox_2d": bbox_list,
                "params": str(params_raw) if params_raw else "",
            })

            # Overlay: small marker at each action point
            center_x: int = (bbox_list[0] + bbox_list[2]) // 2
            center_y: int = (bbox_list[1] + bbox_list[3]) // 2
            marker_color: str = "#ff6600" if action_type in ("click", "double_click", "right_click") else "#00cc66"
            output_overlays.append({
                "points": _make_circle_points(center_x, center_y, 15),
                "closed": True,
                "stroke": marker_color,
                "fill": f"rgba(255,255,255,0.15)",
                "label": action_type.strip().lower(),
                "label_position": [center_x, center_y - 18],
                "label_style": {
                    "font_size": 9,
                    "bg": "",
                    "color": marker_color,
                    "align": "center",
                },
            })

    # Build user text for next VLM call
    output_user_text = (
        f"Last step plan: {plan_text}\n"
        f"Next planned: {next_text}\n"
        f"Look at the screenshot. Did the last step work?\n"
        f"Continue with the next step of drawing the cat.\n"
        f"Output only JSON."
    )

    return RouteResult(output_user_text, output_actions, output_overlays)


# =========================================================================
# ZONE 2: THE SEQUENCE
#
# Paint cat pipeline:
#   1. Parse VLM response
#   2. Execute actions (clicks, drags, typing)
#   3. Wait 2s for Paint to respond
#   4. Capture new screenshot
#   5. Annotate with action markers
#   6. Send to VLM
# =========================================================================

def run_cycle(
    vlm_response_text: str,
    overlays_from_previous: list[dict[str, str | bool | float | list[list[int | float]]]],
    capture_fn: object,
    execute_fn: object,
    annotate_fn: object,
    call_vlm_fn: object,
) -> tuple[str, list[dict[str, str | bool | float | list[list[int | float]]]]]:

    result: RouteResult = route(vlm_response_text)

    execute_fn(result.actions)

    screenshot: str = capture_fn()

    # Show markers from THIS step on the new screenshot
    annotated: str = annotate_fn(screenshot, result.overlays)

    next_response: str = call_vlm_fn(annotated, result.user_text)

    return next_response, result.overlays


# =========================================================================
# ZONE 3: THE OVERLAY BUILDER
#
# Pass through overlays from route(). No extra processing needed.
# =========================================================================

def build_overlays(
    action_results: list[dict[str, str | int | list[int]]],
    screen_changed: bool,
    user_overlays: list[dict[str, str | bool | float | list[list[int | float]]]],
) -> list[dict[str, str | bool | float | list[list[int | float]]]]:

    return user_overlays


# =========================================================================
# HELPERS
# =========================================================================

def _extract_json(raw: str) -> dict[str, object] | None:
    stripped: str = raw.strip()
    json_start: int = stripped.find("{")
    if json_start == -1:
        return None
    depth: int = 0
    in_string: bool = False
    escape_next: bool = False
    for char_idx in range(json_start, len(stripped)):
        char: str = stripped[char_idx]
        if escape_next:
            escape_next = False
            continue
        if char == "\\":
            if in_string:
                escape_next = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                try:
                    raw_parsed: object = json.loads(stripped[json_start:char_idx + 1])
                    if isinstance(raw_parsed, dict):
                        return raw_parsed
                except json.JSONDecodeError:
                    return None
    return None


def _make_circle_points(
    center_x: int, center_y: int, radius: int, segments: int = 12,
) -> list[list[int]]:
    import math
    points: list[list[int]] = []
    for idx in range(segments):
        angle: float = 2.0 * math.pi * idx / segments
        px_val: int = int(center_x + radius * math.cos(angle))
        py_val: int = int(center_y + radius * math.sin(angle))
        points.append([px_val, py_val])
    return points
