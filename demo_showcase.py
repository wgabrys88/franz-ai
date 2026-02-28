import json
import math
import time
from dataclasses import dataclass


@dataclass(slots=True)
class ScenarioConfig:
    vlm_endpoint_url: str = "http://127.0.0.1:1235/v1/chat/completions"
    vlm_model_name: str = "qwen3-vl-2b"
    vlm_temperature: float = 0.4
    vlm_top_p: float = 0.9
    vlm_max_tokens: int = 1200
    server_host: str = "127.0.0.1"
    server_port: int = 1234
    capture_region: str = ""
    capture_width: int = 640
    capture_height: int = 640
    capture_delay_seconds: float = 2.5
    system_prompt: str = (
        "You are Franz. You live inside this screen.\n"
        "You have a story. You read your story each turn, look at the screenshot,\n"
        "and continue the story by doing things on the computer.\n"
        "\n"
        "YOUR STORY so far is given to you each turn. Continue it.\n"
        "Your story contains your memory, your progress, your plans.\n"
        "Write it like a journal. First person. Natural.\n"
        "\n"
        "You have a QUEST with three chapters:\n"
        "\n"
        "CHAPTER 1 - THE PAINTING\n"
        "  Open Microsoft Paint. Draw something creative - an animal, a landscape,\n"
        "  a pattern, anything you feel like. Use the brush tool.\n"
        "  When done, save the file to the Desktop as 'franz_art.png'.\n"
        "  Use File > Save As, navigate to Desktop, type the filename.\n"
        "\n"
        "CHAPTER 2 - THE CHESS GAME\n"
        "  Open Chrome. Go to chess.com. Start a game against a bot (1 minute).\n"
        "  Play as White. Make at least 5 moves. You don't need to win.\n"
        "  Take a screenshot of the board using Win+Shift+S (snipping tool)\n"
        "  or just use Print Screen. Save it to Desktop as 'chess_game.png'.\n"
        "\n"
        "CHAPTER 3 - THE POST\n"
        "  Open Chrome. Go to x.com (Twitter). Click the compose button.\n"
        "  Type a short message about your day: painting and playing chess.\n"
        "  Attach the chess screenshot if possible. Post it.\n"
        "\n"
        "RULES:\n"
        "- Do ONE small step per turn. Never rush.\n"
        "- Your story tracks where you are. Which chapter. What step.\n"
        "- If something fails, write about it in your story and try again.\n"
        "- Coordinates are [x1,y1,x2,y2], integers 0 to 1000.\n"
        "- Available actions: click, double_click, right_click, type, key,\n"
        "  hotkey, scroll_up, scroll_down, drag_start, drag_end\n"
        "\n"
        "YOUR CURRENT PHASE tells you where you are.\n"
        "Read it carefully before deciding what to do.\n"
        "\n"
        "JSON FORMAT (output ONLY this, nothing else):\n"
        "{\n"
        '  "story": "Your full continuing story. Everything you remember and plan.",\n'
        '  "chapter": 1,\n'
        '  "phase": "short description of current step",\n'
        '  "do": [{"type": "click", "bbox_2d": [x1,y1,x2,y2], "params": ""}],\n'
        '  "expect": "What should happen after this action"\n'
        "}\n"
        "\n"
        "IMPORTANT: Your story is your ONLY memory. Write everything important.\n"
        "What you tried. What worked. What failed. Where you are.\n"
        "Next turn you will read your own story and see a new screenshot.\n"
        "Output ONLY the JSON object."
    )
    seed_vlm_text: str = (
        '{"story":"I just woke up. I am Franz, living inside a computer screen. '
        "I have a quest today with three chapters: first I will open Paint and "
        "draw something creative, save it to the Desktop. Then I will play a "
        "chess game on chess.com and save a screenshot. Finally I will post "
        "about my day on x.com. Let me start by looking at what is on my screen "
        "right now. I need to find the Start menu or taskbar to begin. "
        'My first step: click the Start button to begin Chapter 1.",'
        '"chapter":1,'
        '"phase":"starting - about to click Start menu",'
        '"do":[{"type":"click","bbox_2d":[490,980,510,1000],"params":""}],'
        '"expect":"Start menu opens so I can search for Paint"}'
    )
    change_threshold: float = 0.005
    phase_colors: dict[str, str] = None

    def __post_init__(self) -> None:
        if self.phase_colors is None:
            self.phase_colors = {
                "chapter_1": "#ff6600",
                "chapter_2": "#4488ff",
                "chapter_3": "#cc44ff",
                "success": "#00cc66",
                "failure": "#ff2244",
                "neutral": "#aaaaaa",
            }


CONFIG: ScenarioConfig = ScenarioConfig()


@dataclass(slots=True)
class RouteResult:
    user_text: str
    actions: list[dict[str, str | int | list[int]]]
    overlays: list[dict[str, str | bool | float | list[list[int | float]]]]


CHAPTER_LABELS: dict[int, str] = {
    1: "CH1: THE PAINTING",
    2: "CH2: THE CHESS GAME",
    3: "CH3: THE POST",
}

CHAPTER_COLORS: dict[int, str] = {
    1: "#ff6600",
    2: "#4488ff",
    3: "#cc44ff",
}

CHAPTER_FILL: dict[int, str] = {
    1: "rgba(255,102,0,0.25)",
    2: "rgba(68,136,255,0.25)",
    3: "rgba(204,68,255,0.25)",
}


# =========================================================================
# ZONE 1: THE PARSER
#
# Parse the VLM story-driven JSON.
# Extract chapter, phase, actions, story.
# Build overlays:
#   - HUD banner showing current chapter and phase
#   - Action markers at each click/action location
#   - Chapter progress bar at the bottom
#   - Phase label in the corner
#
# The user_text fed back to VLM contains the full story and phase info
# so the VLM can continue where it left off.
# =========================================================================

def route(raw_vlm_output: str) -> RouteResult:
    input_text: str = raw_vlm_output
    output_user_text: str = ""
    output_actions: list[dict[str, str | int | list[int]]] = []
    output_overlays: list[dict[str, str | bool | float | list[list[int | float]]]] = []

    parsed: dict[str, object] | None = _extract_json(input_text)
    if parsed is None:
        output_user_text = (
            "I could not parse your last response as JSON.\n"
            "Remember: output ONLY a JSON object with story, chapter, phase, do, expect.\n"
            "Try again. Look at the screenshot and continue your quest."
        )
        # Draw an error overlay so VLM sees something went wrong
        output_overlays.append(_make_label_overlay(
            "PARSE ERROR - Output only JSON", 500, 500,
            font_size=14, bg_color="#cc0000", text_color="#ffffff",
        ))
        return RouteResult(output_user_text, output_actions, output_overlays)

    # Extract fields
    story: str = str(parsed.get("story", ""))
    chapter_raw: object = parsed.get("chapter", 1)
    chapter: int = int(chapter_raw) if isinstance(chapter_raw, (int, float)) else 1
    chapter = max(1, min(3, chapter))
    phase: str = str(parsed.get("phase", ""))
    expect: str = str(parsed.get("expect", ""))
    do_list: object = parsed.get("do", [])

    # Parse actions
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

            atype: str = action_type.strip().lower()
            output_actions.append({
                "type": atype,
                "bbox_2d": bbox_list,
                "params": str(params_raw) if params_raw else "",
            })

            # Action marker overlay
            center_x: int = (bbox_list[0] + bbox_list[2]) // 2
            center_y: int = (bbox_list[1] + bbox_list[3]) // 2
            marker_color: str = CHAPTER_COLORS.get(chapter, "#aaaaaa")

            # Circle marker at action point
            output_overlays.append({
                "points": _make_circle_points(center_x, center_y, 18),
                "closed": True,
                "stroke": marker_color,
                "fill": CHAPTER_FILL.get(chapter, "rgba(170,170,170,0.2)"),
                "label": atype,
                "label_position": [center_x, center_y - 22],
                "label_style": {
                    "font_size": 9,
                    "bg": "",
                    "color": marker_color,
                    "align": "center",
                },
            })

            # For drag actions, draw an arrow from start to end
            if atype == "drag_end" and len(output_actions) >= 2:
                prev_action: dict[str, str | int | list[int]] = output_actions[-2]
                if prev_action.get("type") == "drag_start":
                    prev_bbox: list[int] = prev_action.get("bbox_2d", [500, 500, 500, 500])
                    if isinstance(prev_bbox, list) and len(prev_bbox) == 4:
                        prev_cx: int = (prev_bbox[0] + prev_bbox[2]) // 2
                        prev_cy: int = (prev_bbox[1] + prev_bbox[3]) // 2
                        output_overlays.append({
                            "points": _make_arrow_points(prev_cx, prev_cy, center_x, center_y),
                            "closed": True,
                            "stroke": marker_color,
                            "fill": CHAPTER_FILL.get(chapter, "rgba(170,170,170,0.2)"),
                            "label": "",
                        })

    # HUD: Chapter banner at top
    chapter_label: str = CHAPTER_LABELS.get(chapter, f"CHAPTER {chapter}")
    chapter_color: str = CHAPTER_COLORS.get(chapter, "#aaaaaa")
    output_overlays.append(_make_label_overlay(
        chapter_label, 500, 12,
        font_size=13, bg_color=chapter_color, text_color="#ffffff",
        align="center",
    ))

    # HUD: Phase label below chapter banner
    if phase:
        output_overlays.append(_make_label_overlay(
            phase, 500, 30,
            font_size=10, bg_color="rgba(0,0,0,0.6)", text_color="#dddddd",
            align="center",
        ))

    # HUD: Chapter progress bar at bottom
    progress_overlays: list[dict[str, str | bool | float | list[list[int | float]]]] = _make_progress_bar(chapter)
    output_overlays.extend(progress_overlays)

    # Build user text: the full story + status for VLM to continue
    story_excerpt: str = story
    if len(story_excerpt) > 900:
        # Keep the last 900 characters of the story so it fits in context
        # We take from the end to preserve recent memory
        cut_point: int = len(story_excerpt) - 900
        # Find a sentence boundary near the cut point
        for search_idx in range(cut_point, min(cut_point + 100, len(story_excerpt))):
            if story_excerpt[search_idx] == ".":
                cut_point = search_idx + 1
                break
        story_excerpt = "..." + story_excerpt[cut_point:]

    output_user_text = (
        f"YOUR STORY SO FAR:\n"
        f"{story_excerpt}\n"
        f"\n"
        f"CURRENT STATUS:\n"
        f"  Chapter: {chapter} - {CHAPTER_LABELS.get(chapter, '?')}\n"
        f"  Phase: {phase}\n"
        f"  Last expected: {expect}\n"
        f"\n"
        f"Look at the screenshot. Did your last action work?\n"
        f"Continue your story. Do the next small step.\n"
        f"Remember: one action at a time. Write everything important in your story.\n"
        f"Output only JSON."
    )

    return RouteResult(output_user_text, output_actions, output_overlays)


# =========================================================================
# ZONE 2: THE SEQUENCE
#
# Demo showcase pipeline:
#   1. Parse VLM response (route) - extract story, actions, overlays
#   2. Execute actions on desktop
#   3. Wait capture_delay (2.5s) for desktop to settle
#   4. Capture new screenshot
#   5. Annotate with chapter HUD, action markers, progress bar
#   6. Send to VLM with story context
#
# We pass result.overlays (not overlays_from_previous) to annotate_fn
# so the VLM sees markers for what JUST happened, on the NEW screenshot.
# =========================================================================

def run_cycle(
    vlm_response_text: str,
    overlays_from_previous: list[dict[str, str | bool | float | list[list[int | float]]]],
    capture_fn: object,
    execute_fn: object,
    annotate_fn: object,
    call_vlm_fn: object,
) -> tuple[str, list[dict[str, str | bool | float | list[list[int | float]]]]]:

    # Parse the VLM story response
    result: RouteResult = route(vlm_response_text)

    # Execute whatever the VLM decided to do
    execute_fn(result.actions)

    # Capture the screen after actions + delay
    screenshot: str = capture_fn()

    # Annotate the NEW screenshot with this turn's overlays
    # VLM sees: fresh screenshot + chapter HUD + action markers
    annotated: str = annotate_fn(screenshot, result.overlays)

    # Ask VLM to continue the story
    next_response: str = call_vlm_fn(annotated, result.user_text)

    return next_response, result.overlays


# =========================================================================
# ZONE 3: THE OVERLAY BUILDER
#
# Post-process overlays. Add screen change indicator.
# If screen did NOT change after an action, add a yellow warning
# so the VLM knows to try something different.
# =========================================================================

def build_overlays(
    action_results: list[dict[str, str | int | list[int]]],
    screen_changed: bool,
    user_overlays: list[dict[str, str | bool | float | list[list[int | float]]]],
) -> list[dict[str, str | bool | float | list[list[int | float]]]]]:

    final_overlays: list[dict[str, str | bool | float | list[list[int | float]]]] = list(user_overlays)

    if len(action_results) > 0:
        if screen_changed:
            final_overlays.append(_make_label_overlay(
                "OK", 970, 965,
                font_size=9, bg_color="rgba(0,180,80,0.7)", text_color="#ffffff",
                align="right",
            ))
        else:
            final_overlays.append(_make_label_overlay(
                "NO CHANGE - try different approach", 500, 965,
                font_size=10, bg_color="rgba(200,150,0,0.8)", text_color="#ffffff",
                align="center",
            ))

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


def _make_circle_points(
    center_x: int, center_y: int, radius: int, segments: int = 12,
) -> list[list[int]]:
    points: list[list[int]] = []
    for idx in range(segments):
        angle: float = 2.0 * math.pi * idx / segments
        px_val: int = int(center_x + radius * math.cos(angle))
        py_val: int = int(center_y + radius * math.sin(angle))
        points.append([px_val, py_val])
    return points


def _make_arrow_points(
    from_x: int, from_y: int, to_x: int, to_y: int,
    shaft_half_width: float = 8.0,
    head_length: float = 25.0,
    head_half_width: float = 18.0,
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


def _make_label_overlay(
    text: str,
    pos_x: int,
    pos_y: int,
    font_size: int = 10,
    bg_color: str = "rgba(0,0,0,0.6)",
    text_color: str = "#ffffff",
    align: str = "center",
) -> dict[str, str | bool | float | list[list[int | float]]]:
    return {
        "points": [[pos_x, pos_y]],
        "closed": False,
        "stroke": "",
        "fill": "",
        "label": text,
        "label_position": [pos_x, pos_y],
        "label_style": {
            "font_size": font_size,
            "bg": bg_color,
            "color": text_color,
            "align": align,
        },
    }


def _make_progress_bar(
    current_chapter: int,
) -> list[dict[str, str | bool | float | list[list[int | float]]]]:
    overlays: list[dict[str, str | bool | float | list[list[int | float]]]] = []

    bar_y: int = 985
    bar_height: int = 10
    segment_width: int = 300
    bar_start_x: int = 50

    for chapter_num in range(1, 4):
        seg_x1: int = bar_start_x + (chapter_num - 1) * (segment_width + 10)
        seg_x2: int = seg_x1 + segment_width
        seg_y1: int = bar_y
        seg_y2: int = bar_y + bar_height

        if chapter_num < current_chapter:
            # Completed chapter: solid fill
            fill_color: str = CHAPTER_COLORS.get(chapter_num, "#aaaaaa")
            overlays.append({
                "points": [[seg_x1, seg_y1], [seg_x2, seg_y1],
                           [seg_x2, seg_y2], [seg_x1, seg_y2]],
                "closed": True,
                "stroke": fill_color,
                "fill": fill_color,
                "label": "",
            })
        elif chapter_num == current_chapter:
            # Current chapter: outlined with partial fill
            chapter_color: str = CHAPTER_COLORS.get(chapter_num, "#aaaaaa")
            chapter_fill: str = CHAPTER_FILL.get(chapter_num, "rgba(170,170,170,0.3)")
            overlays.append({
                "points": [[seg_x1, seg_y1], [seg_x2, seg_y1],
                           [seg_x2, seg_y2], [seg_x1, seg_y2]],
                "closed": True,
                "stroke": chapter_color,
                "fill": chapter_fill,
                "label": "",
            })
            # Pulsing dot at current position
            dot_x: int = (seg_x1 + seg_x2) // 2
            dot_y: int = (seg_y1 + seg_y2) // 2
            overlays.append({
                "points": _make_circle_points(dot_x, dot_y, 5, 8),
                "closed": True,
                "stroke": "#ffffff",
                "fill": chapter_color,
                "label": "",
            })
        else:
            # Future chapter: dim outline only
            overlays.append({
                "points": [[seg_x1, seg_y1], [seg_x2, seg_y1],
                           [seg_x2, seg_y2], [seg_x1, seg_y2]],
                "closed": True,
                "stroke": "rgba(100,100,100,0.4)",
                "fill": "",
                "label": "",
            })

        # Chapter number label
        label_x: int = (seg_x1 + seg_x2) // 2
        label_color: str = CHAPTER_COLORS.get(chapter_num, "#aaaaaa") if chapter_num <= current_chapter else "rgba(100,100,100,0.5)"
        overlays.append(_make_label_overlay(
            f"Ch.{chapter_num}", label_x, bar_y - 10,
            font_size=8, bg_color="", text_color=label_color,
            align="center",
        ))

    return overlays
