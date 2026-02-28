import json
from dataclasses import dataclass


@dataclass(slots=True)
class ScenarioConfig:
    vlm_endpoint_url: str = "http://127.0.0.1:1235/v1/chat/completions"
    vlm_model_name: str = "qwen3-vl-2b"
    vlm_temperature: float = 0.4
    vlm_top_p: float = 0.9
    vlm_max_tokens: int = 700
    server_host: str = "127.0.0.1"
    server_port: int = 1234
    capture_region: str = ""
    capture_width: int = 640
    capture_height: int = 640
    capture_delay_seconds: float = 2.0
    system_prompt: str = (
        "You are a Windows 11 desktop tester. You see a screenshot.\n"
        "Your goal: test every available action type one by one.\n"
        "\n"
        "You must test these actions IN ORDER, one per turn:\n"
        "  1. click - Open Start menu (click the taskbar center)\n"
        "  2. type - Type 'notepad' in the Start search\n"
        "  3. key - Press Enter to open Notepad\n"
        "  4. click - Click inside the Notepad text area\n"
        "  5. type - Type 'Hello Franz Test' in Notepad\n"
        "  6. hotkey - Press Ctrl+A to select all text\n"
        "  7. hotkey - Press Ctrl+C to copy\n"
        "  8. hotkey - Press Ctrl+V to paste (duplicates text)\n"
        "  9. scroll_up - Scroll up in Notepad\n"
        "  10. scroll_down - Scroll down in Notepad\n"
        "  11. hotkey - Press Alt+F4 to close Notepad\n"
        "  12. click - Click 'Don't Save' if prompted\n"
        "  13. click - Open Start menu again\n"
        "  14. type - Type 'mspaint'\n"
        "  15. key - Press Enter to open Paint\n"
        "  16. click - Click on Paint canvas\n"
        "  17. drag_start + drag_end - Draw a line in Paint\n"
        "  18. double_click - Double click on canvas\n"
        "  19. right_click - Right click on canvas\n"
        "  20. key - Press Escape to close any menu\n"
        "\n"
        "Coordinates are [x1,y1,x2,y2], integers 0 to 1000.\n"
        "\n"
        "Respond with ONLY a JSON object:\n"
        "{\n"
        '  "step": 1,\n'
        '  "test": "What action type you are testing",\n'
        '  "do": [{"type": "click", "bbox_2d": [x1,y1,x2,y2], "params": ""}],\n'
        '  "result": "What you expect to happen",\n'
        '  "next_test": "What you will test next"\n'
        "}\n"
        "\n"
        "One action type per turn. Be methodical.\n"
        "Output ONLY JSON. No other text."
    )
    seed_vlm_text: str = (
        '{"step":1,"test":"click - Open Start menu",'
        '"do":[{"type":"click","bbox_2d":[490,980,510,1000],"params":""}],'
        '"result":"Start menu should open",'
        '"next_test":"type - Type notepad in search"}'
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
# Parse the test step JSON. Extract actions.
# Build overlays that show step number, action type being tested,
# and colored markers at action locations.
# Green = success expected, yellow = keyboard action, red = closing.
# =========================================================================

def route(raw_vlm_output: str) -> RouteResult:
    input_text: str = raw_vlm_output
    output_user_text: str = ""
    output_actions: list[dict[str, str | int | list[int]]] = []
    output_overlays: list[dict[str, str | bool | float | list[list[int | float]]]] = []

    parsed: dict[str, object] | None = _extract_json(input_text)
    if parsed is None:
        output_user_text = "Could not parse. Output only JSON with step, test, do, result, next_test."
        return RouteResult(output_user_text, output_actions, output_overlays)

    # Extract fields
    step_num: int = int(parsed.get("step", 0)) if isinstance(parsed.get("step"), (int, float)) else 0
    test_name: str = str(parsed.get("test", ""))
    result_expect: str = str(parsed.get("result", ""))
    next_test: str = str(parsed.get("next_test", ""))
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

            # Overlay marker per action
            center_x: int = (bbox_list[0] + bbox_list[2]) // 2
            center_y: int = (bbox_list[1] + bbox_list[3]) // 2
            atype: str = action_type.strip().lower()

            # Color code by action category
            marker_color: str = "#00cc66"
            if atype in ("type", "key", "hotkey"):
                marker_color = "#ffaa00"
            elif atype in ("drag_start", "drag_end"):
                marker_color = "#cc44ff"
            elif atype == "right_click":
                marker_color = "#ff4466"

            output_overlays.append({
                "points": [[center_x, center_y]],
                "closed": False,
                "stroke": "",
                "fill": "",
                "label": atype,
                "label_position": [center_x, center_y + 12],
                "label_style": {
                    "font_size": 9,
                    "bg": "",
                    "color": marker_color,
                    "align": "center",
                },
            })

    # HUD overlay: step number and test name
    output_overlays.append({
        "points": [[500, 15]],
        "closed": False,
        "stroke": "",
        "fill": "",
        "label": f"Step {step_num}: {test_name}",
        "label_position": [500, 10],
        "label_style": {
            "font_size": 12,
            "bg": "rgba(0,0,0,0.7)",
            "color": "#ffffff",
            "align": "center",
        },
    })

    # Build user text for next VLM call
    output_user_text = (
        f"Step {step_num} tested: {test_name}\n"
        f"Expected result: {result_expect}\n"
        f"Next planned test: {next_test}\n"
        f"Look at the screenshot. Did step {step_num} work as expected?\n"
        f"Now perform the next test step. Increment the step number.\n"
        f"Output only JSON."
    )

    return RouteResult(output_user_text, output_actions, output_overlays)


# =========================================================================
# ZONE 2: THE SEQUENCE
#
# Standard pipeline: parse -> execute -> capture -> annotate -> call VLM
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

    annotated: str = annotate_fn(screenshot, result.overlays)

    next_response: str = call_vlm_fn(annotated, result.user_text)

    return next_response, result.overlays


# =========================================================================
# ZONE 3: THE OVERLAY BUILDER
#
# Add pass/fail indicator based on screen change.
# For tests that involve typing or keyboard, no screen change
# might be expected (e.g., Ctrl+C copies silently).
# =========================================================================

def build_overlays(
    action_results: list[dict[str, str | int | list[int]]],
    screen_changed: bool,
    user_overlays: list[dict[str, str | bool | float | list[list[int | float]]]],
) -> list[dict[str, str | bool | float | list[list[int | float]]]]:

    final_overlays: list[dict[str, str | bool | float | list[list[int | float]]]] = list(user_overlays)

    # Status indicator in top-right corner
    if len(action_results) > 0:
        status_text: str = "SCREEN CHANGED" if screen_changed else "NO CHANGE"
        status_color: str = "#00cc66" if screen_changed else "#ffaa00"
        final_overlays.append({
            "points": [[950, 40]],
            "closed": False,
            "stroke": "",
            "fill": "",
            "label": status_text,
            "label_position": [950, 35],
            "label_style": {
                "font_size": 10,
                "bg": "rgba(0,0,0,0.6)",
                "color": status_color,
                "align": "right",
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
