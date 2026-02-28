import re


NORM_MIN: int = 0
NORM_MAX: int = 1000


_action_pipe: list[dict[str, object]] = []
_overlay_pipe: list[dict[str, object]] = []


def actions(action: dict[str, object]) -> None:
    _action_pipe.append(action)


def overlays(overlay: dict[str, object]) -> None:
    _overlay_pipe.append(overlay)


def _flush_pipes() -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    flushed_actions: list[dict[str, object]] = list(_action_pipe)
    flushed_overlays: list[dict[str, object]] = list(_overlay_pipe)
    _action_pipe.clear()
    _overlay_pipe.clear()
    return flushed_actions, flushed_overlays


def _clamp(value: int) -> int:
    return max(NORM_MIN, min(NORM_MAX, value))


def click(x: int, y: int) -> dict[str, object]:
    return {"type": "click", "x": _clamp(x), "y": _clamp(y)}


def double_click(x: int, y: int) -> dict[str, object]:
    return {"type": "double_click", "x": _clamp(x), "y": _clamp(y)}


def right_click(x: int, y: int) -> dict[str, object]:
    return {"type": "right_click", "x": _clamp(x), "y": _clamp(y)}


def type_text(text: str) -> dict[str, object]:
    return {"type": "type_text", "params": text}


def press_key(name: str) -> dict[str, object]:
    return {"type": "press_key", "params": name}


def hotkey(combo: str) -> dict[str, object]:
    return {"type": "hotkey", "params": combo}


def scroll_up(x: int, y: int) -> dict[str, object]:
    return {"type": "scroll_up", "x": _clamp(x), "y": _clamp(y)}


def scroll_down(x: int, y: int) -> dict[str, object]:
    return {"type": "scroll_down", "x": _clamp(x), "y": _clamp(y)}


def drag_start(x: int, y: int) -> dict[str, object]:
    return {"type": "drag_start", "x": _clamp(x), "y": _clamp(y)}


def drag_end(x: int, y: int) -> dict[str, object]:
    return {"type": "drag_end", "x": _clamp(x), "y": _clamp(y)}


def dot(
    x: int, y: int, label: str = "", color: str = "#00ff00",
) -> dict[str, object]:
    return {
        "points": [[x, y]],
        "closed": False,
        "stroke": color,
        "fill": "",
        "label": label,
        "label_position": [x, y],
        "label_style": {"font_size": 10, "bg": "", "color": color, "align": "left"},
    }


def box(
    x1: int, y1: int, x2: int, y2: int,
    label: str = "", stroke_color: str = "#ff6600", fill_color: str = "",
) -> dict[str, object]:
    return {
        "points": [[x1, y1], [x2, y1], [x2, y2], [x1, y2]],
        "closed": True,
        "stroke": stroke_color,
        "fill": fill_color,
        "label": label,
        "label_position": [x1, y1],
        "label_style": {
            "font_size": 10, "bg": "", "color": stroke_color, "align": "left",
        },
    }


def line(
    points: list[list[int]], label: str = "", color: str = "#4488ff",
) -> dict[str, object]:
    return {
        "points": points,
        "closed": False,
        "stroke": color,
        "fill": "",
        "label": label,
        "label_position": points[0] if points else [0, 0],
        "label_style": {"font_size": 10, "bg": "", "color": color, "align": "left"},
    }
