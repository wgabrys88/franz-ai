import json
import math
from dataclasses import dataclass


@dataclass(slots=True)
class ScenarioConfig:
    vlm_endpoint_url: str = "http://127.0.0.1:1235/v1/chat/completions"
    vlm_model_name: str = "qwen3-vl-2b"
    vlm_temperature: float = 0.3
    vlm_top_p: float = 0.9
    vlm_max_tokens: int = 600
    server_host: str = "127.0.0.1"
    server_port: int = 1234
    capture_region: str = "150,100,850,950"
    capture_width: int = 640
    capture_height: int = 640
    capture_delay_seconds: float = 3.0
    system_prompt: str = (
        "You are a chess assistant. You see a chess.com board screenshot.\n"
        "You play as White. Coordinates are 0-1000 normalized.\n"
        "Top-left of the captured board region is 0,0.\n"
        "Bottom-right is 1000,1000.\n"
        "\n"
        "Respond with ONLY a JSON object:\n"
        "{\n"
        '  "best_move": {"from": [x1,y1,x2,y2], "to": [x1,y1,x2,y2], "label": "e2e4"},\n'
        '  "alternatives": [\n'
        '    {"from": [x1,y1,x2,y2], "to": [x1,y1,x2,y2], "label": "d2d4"},\n'
        '    {"from": [x1,y1,x2,y2], "to": [x1,y1,x2,y2], "label": "Nf3"},\n'
        '    {"from": [x1,y1,x2,y2], "to": [x1,y1,x2,y2], "label": "c2c4"}\n'
        "  ],\n"
        '  "analysis": "Brief explanation of position and chosen move."\n'
        "}\n"
        "\n"
        "bbox [x1,y1,x2,y2] marks a square on the board.\n"
        "Use small boxes around the center of each square, about 40x40 in norm coords.\n"
        "The board has 8 ranks and 8 files. White pieces start at the bottom.\n"
        "Estimate square centers by dividing the 0-1000 range into 8 columns and 8 rows.\n"
        "Column a center ~ 62, b ~ 187, c ~ 312, d ~ 437, e ~ 562, f ~ 687, g ~ 812, h ~ 937\n"
        "Row 1 (White back) center ~ 937, row 2 ~ 812, ... row 8 (Black back) ~ 62\n"
        "Output ONLY the JSON object. No other text."
    )
    seed_vlm_text: str = (
        '{"best_move":{"from":[542,792,582,832],"to":[542,667,582,707],"label":"e2e4"},'
        '"alternatives":['
        '{"from":[417,792,457,832],"to":[417,667,457,707],"label":"d2d4"},'
        '{"from":[792,792,832,832],"to":[667,667,707,707],"label":"Nf3"},'
        '{"from":[292,792,332,832],"to":[292,667,332,707],"label":"c2c4"}],'
        '"analysis":"Opening position. e2e4 controls the center and opens lines for bishop and queen."}'
    )
    change_threshold: float = 0.01


CONFIG: ScenarioConfig = ScenarioConfig()


@dataclass(slots=True)
class RouteResult:
    user_text: str
    actions: list[dict[str, str | int | list[int]]]
    overlays: list[dict[str, str | bool | float | list[list[int | float]]]]


# =========================================================================
# ZONE 1: THE PARSER
#
# Parse VLM chess JSON. Extract best_move and alternatives.
# Produce two click actions (source square, destination square).
# Build orange arrow overlay for the chosen move.
# Build up to 3 blue arrow overlays for alternative moves.
# =========================================================================

def route(raw_vlm_output: str) -> RouteResult:
    input_text: str = raw_vlm_output
    output_user_text: str = ""
    output_actions: list[dict[str, str | int | list[int]]] = []
    output_overlays: list[dict[str, str | bool | float | list[list[int | float]]]] = []

    # Parse the JSON from VLM output
    parsed: dict[str, object] | None = _extract_json(input_text)
    if parsed is None:
        output_user_text = "Could not parse your response. Output ONLY a JSON object."
        return RouteResult(output_user_text, output_actions, output_overlays)

    # Extract fields
    best_move: object = parsed.get("best_move", None)
    alternatives: object = parsed.get("alternatives", [])
    analysis: object = parsed.get("analysis", "")

    move_label: str = ""

    # Process best move -> two click actions + orange arrow
    if isinstance(best_move, dict):
        from_bbox: object = best_move.get("from", None)
        to_bbox: object = best_move.get("to", None)
        move_label = str(best_move.get("label", ""))

        if isinstance(from_bbox, list) and len(from_bbox) == 4:
            from_clamped: list[int] = [
                max(0, min(1000, int(from_bbox[0]))),
                max(0, min(1000, int(from_bbox[1]))),
                max(0, min(1000, int(from_bbox[2]))),
                max(0, min(1000, int(from_bbox[3]))),
            ]
            # Click 1: select the piece
            output_actions.append({
                "type": "click",
                "bbox_2d": from_clamped,
                "params": "",
            })

        if isinstance(to_bbox, list) and len(to_bbox) == 4:
            to_clamped: list[int] = [
                max(0, min(1000, int(to_bbox[0]))),
                max(0, min(1000, int(to_bbox[1]))),
                max(0, min(1000, int(to_bbox[2]))),
                max(0, min(1000, int(to_bbox[3]))),
            ]
            # Click 2: place the piece
            output_actions.append({
                "type": "click",
                "bbox_2d": to_clamped,
                "params": "",
            })

        # Orange arrow for the chosen move
        if (isinstance(from_bbox, list) and len(from_bbox) == 4
                and isinstance(to_bbox, list) and len(to_bbox) == 4):
            from_cx: int = (int(from_bbox[0]) + int(from_bbox[2])) // 2
            from_cy: int = (int(from_bbox[1]) + int(from_bbox[3])) // 2
            to_cx: int = (int(to_bbox[0]) + int(to_bbox[2])) // 2
            to_cy: int = (int(to_bbox[1]) + int(to_bbox[3])) // 2
            output_overlays.append({
                "points": _make_arrow_points(from_cx, from_cy, to_cx, to_cy),
                "closed": True,
                "stroke": "#ff6600",
                "fill": "rgba(255,120,0,0.35)",
                "label": move_label,
                "label_position": [to_cx, to_cy - 25],
                "label_style": {
                    "font_size": 12,
                    "bg": "#cc5500",
                    "color": "#ffffff",
                    "align": "center",
                },
            })

    # Blue arrows for alternatives (max 3)
    if isinstance(alternatives, list):
        alt_count: int = 0
        for alt_obj in alternatives:
            if alt_count >= 3:
                break
            if not isinstance(alt_obj, dict):
                continue
            alt_from: object = alt_obj.get("from", None)
            alt_to: object = alt_obj.get("to", None)
            alt_label: str = str(alt_obj.get("label", ""))
            if (isinstance(alt_from, list) and len(alt_from) == 4
                    and isinstance(alt_to, list) and len(alt_to) == 4):
                alt_from_cx: int = (int(alt_from[0]) + int(alt_from[2])) // 2
                alt_from_cy: int = (int(alt_from[1]) + int(alt_from[3])) // 2
                alt_to_cx: int = (int(alt_to[0]) + int(alt_to[2])) // 2
                alt_to_cy: int = (int(alt_to[1]) + int(alt_to[3])) // 2
                output_overlays.append({
                    "points": _make_arrow_points(
                        alt_from_cx, alt_from_cy, alt_to_cx, alt_to_cy,
                        shaft_half_width=6.0, head_length=20.0, head_half_width=14.0,
                    ),
                    "closed": True,
                    "stroke": "#4488ff",
                    "fill": "rgba(68,136,255,0.2)",
                    "label": alt_label,
                    "label_position": [alt_to_cx, alt_to_cy - 20],
                    "label_style": {
                        "font_size": 10,
                        "bg": "#224488",
                        "color": "#aaccff",
                        "align": "center",
                    },
                })
                alt_count += 1

    # Build user text for next VLM call
    analysis_str: str = str(analysis) if analysis else ""
    output_user_text = (
        f"Your last move was: {move_label}\n"
        f"Your analysis: {analysis_str}\n"
        f"The orange arrow on the screenshot shows your last move.\n"
        f"Blue arrows show the alternatives you considered.\n"
        f"Now look at the new board after both moves.\n"
        f"Propose your next move as White. Output only JSON."
    )

    return RouteResult(output_user_text, output_actions, output_overlays)


# =========================================================================
# ZONE 2: THE SEQUENCE
#
# Chess pipeline:
#   1. Parse VLM response (route)
#   2. Execute clicks (move the piece on chess.com)
#   3. Capture screenshot (3s delay so opponent bot responds)
#   4. Annotate new screenshot with arrows from THIS move
#   5. Send annotated image to VLM
#
# Note: we pass result.overlays to annotate_fn (not overlays_from_previous)
# so the VLM sees arrows for the move it just made on the NEW board.
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

    # Execute: click source piece, click destination square
    execute_fn(result.actions)

    # Capture: waits capture_delay_seconds (3s) then screenshots
    # This gives the chess.com bot time to make its counter-move
    screenshot: str = capture_fn()

    # Annotate the NEW screenshot with THIS move's arrows
    # The VLM will see the board after both moves + arrows showing what it did
    annotated: str = annotate_fn(screenshot, result.overlays)

    # Call VLM with annotated image + context about last move
    next_response: str = call_vlm_fn(annotated, result.user_text)

    return next_response, result.overlays


# =========================================================================
# ZONE 3: THE OVERLAY BUILDER
#
# Overlays are already built in route() because the arrow coordinates
# come directly from the VLM parse. Here we just pass them through.
# Add a red warning if the screen did not change (move may have failed).
# =========================================================================

def build_overlays(
    action_results: list[dict[str, str | int | list[int]]],
    screen_changed: bool,
    user_overlays: list[dict[str, str | bool | float | list[list[int | float]]]],
) -> list[dict[str, str | bool | float | list[list[int | float]]]]:

    final_overlays: list[dict[str, str | bool | float | list[list[int | float]]]] = list(user_overlays)

    if not screen_changed and len(action_results) > 0:
        # The board did not change -- the move may have failed
        final_overlays.append({
            "points": [[500, 40]],
            "closed": False,
            "stroke": "",
            "fill": "",
            "label": "MOVE MAY HAVE FAILED - SCREEN UNCHANGED",
            "label_position": [500, 40],
            "label_style": {
                "font_size": 13,
                "bg": "#cc0000",
                "color": "#ffffff",
                "align": "center",
            },
        })

    return final_overlays


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


def _make_arrow_points(
    from_x: int, from_y: int, to_x: int, to_y: int,
    shaft_half_width: float = 10.0,
    head_length: float = 30.0,
    head_half_width: float = 22.0,
) -> list[list[int]]:
    delta_x: float = float(to_x - from_x)
    delta_y: float = float(to_y - from_y)
    length: float = math.hypot(delta_x, delta_y)
    if length < 1.0:
        return [[from_x, from_y]]

    unit_x: float = delta_x / length
    unit_y: float = delta_y / length
    normal_x: float = -unit_y
    normal_y: float = unit_x

    effective_head_len: float = head_length
    effective_head_hw: float = head_half_width
    if length < head_length * 1.5:
        effective_head_len = length * 0.4
        effective_head_hw = effective_head_len * 0.7

    shaft_end_x: float = to_x - unit_x * effective_head_len
    shaft_end_y: float = to_y - unit_y * effective_head_len

    return [
        [int(from_x + normal_x * shaft_half_width),
         int(from_y + normal_y * shaft_half_width)],
        [int(shaft_end_x + normal_x * shaft_half_width),
         int(shaft_end_y + normal_y * shaft_half_width)],
        [int(shaft_end_x + normal_x * effective_head_hw),
         int(shaft_end_y + normal_y * effective_head_hw)],
        [int(to_x), int(to_y)],
        [int(shaft_end_x - normal_x * effective_head_hw),
         int(shaft_end_y - normal_y * effective_head_hw)],
        [int(shaft_end_x - normal_x * shaft_half_width),
         int(shaft_end_y - normal_y * shaft_half_width)],
        [int(from_x - normal_x * shaft_half_width),
         int(from_y - normal_y * shaft_half_width)],
    ]
