import base64
import http.server
import json
import subprocess
import sys
import threading
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


HERE: Path = Path(__file__).resolve().parent
PANEL_PATH: Path = HERE / "panel.html"
WIN32_PATH: Path = HERE / "win32.py"

CURSOR_ARM: int = 12
CURSOR_LABEL_OFFSET: int = 18
CURSOR_LABEL_LIMIT: int = 980
CURSOR_FONT_SIZE: int = 11
DEFAULT_CURSOR_POS: int = 500
MIN_ANNOTATION_LENGTH: int = 100
VLM_TIMEOUT: int = 120
FALLBACK_SLEEP: float = 1.0
ERROR_SLEEP: float = 2.0
NO_RESIZE: int = 0


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")


def _load_module(name: str, filename: str) -> object:
    import importlib.util
    filepath: Path = HERE / filename
    if not filepath.exists():
        print(f"ERROR: {filename} not found")
        raise SystemExit(1)
    spec: object = importlib.util.spec_from_file_location(name, str(filepath))
    module: object = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    loader: object = getattr(spec, "loader", None)
    loader.exec_module(module)
    return module


_runtime_overrides: dict[str, object] = {}


def _cfg(brain: object, name: str, default: object) -> object:
    if name in _runtime_overrides:
        return _runtime_overrides[name]
    return getattr(brain, name, default)


class SessionLog:
    def __init__(self, session_dir: Path, turns_file: Path) -> None:
        self.session_dir: Path = session_dir
        self.turns_file: Path = turns_file

    @staticmethod
    def create() -> "SessionLog":
        logs_root: Path = HERE / "logs"
        logs_root.mkdir(exist_ok=True)
        session_dir: Path = logs_root / _utc_stamp()
        session_dir.mkdir(exist_ok=True)
        return SessionLog(session_dir=session_dir, turns_file=session_dir / "turns.txt")

    def write_turn(self, turn: int, label: str, text: str) -> None:
        with self.turns_file.open("a", encoding="utf-8") as handle:
            handle.write(f"--- TURN {turn} | {_utc_stamp()} | {label} ---\n{text}\n")

    def save_png(self, data_b64: str) -> None:
        (self.session_dir / f"{_utc_stamp()}.png").write_bytes(base64.b64decode(data_b64))


class ServerState:
    def __init__(self) -> None:
        self.phase: str = "init"
        self.turn: int = 0
        self.raw_b64: str = ""
        self.raw_seq: int = 0
        self.overlays: list[dict[str, object]] = []
        self.pending_seq: int = 0
        self.annotated_seq: int = -1
        self.annotated_b64: str = ""
        self.annotated_ready: threading.Event = threading.Event()
        self.display_text: str = ""
        self.display_actions: list[dict[str, object]] = []
        self.error_text: str = ""
        self.lock: threading.Lock = threading.Lock()


STATE: ServerState = ServerState()


def _subprocess_capture(brain: object) -> str:
    cmd: list[str] = [sys.executable, str(WIN32_PATH), "capture"]
    region: str = str(_cfg(brain, "CAPTURE_REGION", ""))
    if region:
        cmd.extend(["--region", region])
    width: int = int(_cfg(brain, "CAPTURE_WIDTH", 640))
    height: int = int(_cfg(brain, "CAPTURE_HEIGHT", 640))
    cmd.extend(["--width", str(width)])
    cmd.extend(["--height", str(height)])
    proc: subprocess.CompletedProcess[bytes] = subprocess.run(cmd, capture_output=True)
    if proc.returncode != 0 or not proc.stdout:
        return ""
    return base64.b64encode(proc.stdout).decode("ascii")


def _subprocess_cursor_pos(brain: object) -> tuple[int, int]:
    cmd: list[str] = [sys.executable, str(WIN32_PATH), "cursor_pos"]
    region: str = str(_cfg(brain, "CAPTURE_REGION", ""))
    if region:
        cmd.extend(["--region", region])
    proc: subprocess.CompletedProcess[bytes] = subprocess.run(cmd, capture_output=True)
    if proc.returncode != 0 or not proc.stdout:
        return DEFAULT_CURSOR_POS, DEFAULT_CURSOR_POS
    parts: list[str] = proc.stdout.decode("ascii").strip().split(",")
    if len(parts) != 2:
        return DEFAULT_CURSOR_POS, DEFAULT_CURSOR_POS
    return int(parts[0]), int(parts[1])


def _action_xy_str(action: dict[str, object]) -> str:
    x_val: int = int(action.get("x", DEFAULT_CURSOR_POS))
    y_val: int = int(action.get("y", DEFAULT_CURSOR_POS))
    return f"{x_val},{y_val}"


def _subprocess_execute_one(action: dict[str, object], brain: object) -> None:
    action_type: str = str(action.get("type", ""))
    params_str: str = str(action.get("params", ""))
    region: str = str(_cfg(brain, "CAPTURE_REGION", ""))
    cmd: list[str] = [sys.executable, str(WIN32_PATH)]

    match action_type:
        case "click":
            cmd.extend(["click", "--pos", _action_xy_str(action)])
        case "double_click":
            cmd.extend(["double_click", "--pos", _action_xy_str(action)])
        case "right_click":
            cmd.extend(["right_click", "--pos", _action_xy_str(action)])
        case "type_text":
            cmd.extend(["type_text", "--text", params_str])
        case "press_key":
            cmd.extend(["press_key", "--key", params_str])
        case "hotkey":
            cmd.extend(["hotkey", "--keys", params_str])
        case "scroll_up":
            cmd.extend(["scroll_up", "--pos", _action_xy_str(action)])
        case "scroll_down":
            cmd.extend(["scroll_down", "--pos", _action_xy_str(action)])
        case _:
            return

    if region:
        cmd.extend(["--region", region])
    subprocess.run(cmd, capture_output=True)


def _subprocess_execute_drag(
    from_action: dict[str, object], to_action: dict[str, object], brain: object,
) -> None:
    cmd: list[str] = [
        sys.executable, str(WIN32_PATH), "drag",
        "--from_pos", _action_xy_str(from_action),
        "--to_pos", _action_xy_str(to_action),
    ]
    region: str = str(_cfg(brain, "CAPTURE_REGION", ""))
    if region:
        cmd.extend(["--region", region])
    subprocess.run(cmd, capture_output=True)


def _call_vlm(image_b64: str, user_text: str, system_prompt: str, brain: object) -> str:
    user_content: list[dict[str, object]] = []
    if user_text:
        user_content.append({"type": "text", "text": user_text})
    user_content.append({
        "type": "image_url",
        "image_url": {"url": f"data:image/png;base64,{image_b64}"},
    })
    body: bytes = json.dumps({
        "model": str(_cfg(brain, "VLM_MODEL_NAME", "")),
        "temperature": float(_cfg(brain, "VLM_TEMPERATURE", 0.6)),
        "top_p": float(_cfg(brain, "VLM_TOP_P", 0.85)),
        "max_tokens": int(_cfg(brain, "VLM_MAX_TOKENS", 800)),
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
    }).encode("utf-8")
    endpoint: str = str(_cfg(brain, "VLM_ENDPOINT_URL", ""))
    req: urllib.request.Request = urllib.request.Request(
        endpoint,
        data=body,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=VLM_TIMEOUT) as resp:
            resp_obj: object = json.loads(resp.read().decode("utf-8"))
        if isinstance(resp_obj, dict):
            choices: object = resp_obj.get("choices", [])
            if isinstance(choices, list) and len(choices) > 0:
                first: object = choices[0]
                if isinstance(first, dict):
                    msg: object = first.get("message", {})
                    if isinstance(msg, dict):
                        content: object = msg.get("content", "")
                        if isinstance(content, str):
                            return content
    except Exception as exc:
        print(f"VLM error: {exc}", file=sys.stderr)
    return ""


def _make_cursor_overlay(cx: int, cy: int) -> dict[str, object]:
    return {
        "points": [
            [cx - CURSOR_ARM, cy], [cx + CURSOR_ARM, cy],
            [cx, cy], [cx, cy - CURSOR_ARM], [cx, cy + CURSOR_ARM],
        ],
        "closed": False,
        "stroke": "#00ff00",
        "fill": "",
        "label": f"[{cx},{cy}]",
        "label_position": [
            min(cx + CURSOR_LABEL_OFFSET, CURSOR_LABEL_LIMIT),
            min(cy + CURSOR_LABEL_OFFSET, CURSOR_LABEL_LIMIT),
        ],
        "label_style": {
            "font_size": CURSOR_FONT_SIZE,
            "bg": "#000000",
            "color": "#00ff00",
            "align": "left",
        },
    }


def _engine_loop(brain: object, franz: object, session: SessionLog) -> None:
    system_prompt: str = str(getattr(brain, "SYSTEM_PROMPT", ""))
    on_vlm_response_fn: object = getattr(brain, "on_vlm_response")
    flush_pipes_fn: object = getattr(franz, "_flush_pipes")
    capture_delay: float = float(_cfg(brain, "CAPTURE_DELAY_SECONDS", 3.0))
    action_delay: float = float(_cfg(brain, "ACTION_DELAY_SECONDS", 0.3))
    show_cursor: bool = bool(_cfg(brain, "SHOW_CURSOR", True))

    previous_user_text: str = ""
    last_cursor_pos: tuple[int, int] = (DEFAULT_CURSOR_POS, DEFAULT_CURSOR_POS)

    while True:
        with STATE.lock:
            STATE.turn += 1
            STATE.phase = "capturing"

        if capture_delay > 0:
            time.sleep(capture_delay)
        raw_b64: str = _subprocess_capture(brain)
        if not raw_b64:
            time.sleep(FALLBACK_SLEEP)
            continue

        with STATE.lock:
            STATE.raw_b64 = raw_b64
            STATE.raw_seq += 1
            STATE.phase = "calling_vlm"

        current_turn: int = STATE.turn
        user_text_for_vlm: str = (
            f"Previous: {previous_user_text}"
            if previous_user_text
            else "What do you see? What should you do?"
        )
        session.write_turn(current_turn, "INPUT", user_text_for_vlm)

        vlm_response: str = _call_vlm(raw_b64, user_text_for_vlm, system_prompt, brain)
        session.write_turn(current_turn, "OUTPUT", vlm_response)

        if not vlm_response:
            with STATE.lock:
                STATE.phase = "error"
                STATE.error_text = "VLM returned empty"
            time.sleep(ERROR_SLEEP)
            continue

        with STATE.lock:
            STATE.phase = "parsing"

        try:
            user_text_out: str = on_vlm_response_fn(vlm_response)
        except Exception as exc:
            print(f"on_vlm_response error: {exc}", file=sys.stderr)
            user_text_out = vlm_response

        pipe_actions: list[dict[str, object]]
        pipe_overlays: list[dict[str, object]]
        pipe_actions, pipe_overlays = flush_pipes_fn()

        with STATE.lock:
            STATE.display_text = vlm_response
            STATE.display_actions = list(pipe_actions)
            STATE.phase = "executing"

        executed_count: int = 0
        pending_drag: dict[str, object] | None = None
        for action in pipe_actions:
            action_type: str = str(action.get("type", ""))
            if action_type == "drag_start":
                pending_drag = action
                continue
            if action_type == "drag_end" and pending_drag is not None:
                _subprocess_execute_drag(pending_drag, action, brain)
                pending_drag = None
                last_cursor_pos = _subprocess_cursor_pos(brain)
                continue
            if executed_count > 0:
                time.sleep(action_delay)
            _subprocess_execute_one(action, brain)
            executed_count += 1
            last_cursor_pos = _subprocess_cursor_pos(brain)

        with STATE.lock:
            STATE.phase = "annotating"

        if capture_delay > 0:
            time.sleep(capture_delay)
        post_b64: str = _subprocess_capture(brain)
        if post_b64:
            raw_b64 = post_b64
            with STATE.lock:
                STATE.raw_b64 = raw_b64
                STATE.raw_seq += 1

        final_overlays: list[dict[str, object]] = list(pipe_overlays)
        if show_cursor:
            final_overlays.append(
                _make_cursor_overlay(last_cursor_pos[0], last_cursor_pos[1])
            )

        with STATE.lock:
            STATE.overlays = final_overlays
            STATE.pending_seq = current_turn
            STATE.annotated_seq = -1
            STATE.annotated_b64 = ""
            STATE.annotated_ready.clear()
            STATE.phase = "waiting_annotated"

        STATE.annotated_ready.wait()

        with STATE.lock:
            annotated_result: str = STATE.annotated_b64

        session.save_png(annotated_result)
        previous_user_text = user_text_out if isinstance(user_text_out, str) else vlm_response

        with STATE.lock:
            STATE.phase = "idle"


class FranzHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format_str: str, *args: object) -> None:
        pass

    def _send_json(self, code: int, data: dict[str, object]) -> None:
        body: bytes = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, code: int, html_bytes: bytes) -> None:
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(html_bytes)))
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(html_bytes)

    def do_GET(self) -> None:
        path: str = self.path.split("?", 1)[0]
        match path:
            case "/" | "/index.html":
                self._send_html(200, PANEL_PATH.read_bytes())
            case "/state":
                with STATE.lock:
                    self._send_json(200, {
                        "phase": STATE.phase,
                        "turn": STATE.turn,
                        "pending_seq": STATE.pending_seq,
                        "annotated_seq": STATE.annotated_seq,
                        "raw_seq": STATE.raw_seq,
                        "error": STATE.error_text,
                        "text": STATE.display_text,
                        "display": {
                            "text": STATE.display_text,
                            "actions": STATE.display_actions,
                        },
                        "msg_id": STATE.turn,
                    })
            case "/frame":
                with STATE.lock:
                    self._send_json(200, {
                        "seq": STATE.raw_seq,
                        "raw_b64": STATE.raw_b64,
                        "overlays": STATE.overlays,
                    })
            case _:
                self._send_json(404, {"error": "not found"})

    def do_POST(self) -> None:
        path: str = self.path.split("?", 1)[0]
        content_length: int = int(self.headers.get("Content-Length", "0"))
        body: bytes = self.rfile.read(content_length) if content_length > 0 else b""
        match path:
            case "/annotated":
                try:
                    parsed: object = json.loads(body.decode("utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    self._send_json(400, {"ok": False, "err": "bad json"})
                    return
                if not isinstance(parsed, dict):
                    self._send_json(400, {"ok": False, "err": "bad json"})
                    return
                seq_val: object = parsed.get("seq")
                img_val: object = parsed.get("image_b64", "")
                with STATE.lock:
                    expected: int = STATE.pending_seq
                if seq_val != expected:
                    self._send_json(409, {"ok": False, "err": "seq mismatch"})
                    return
                if not isinstance(img_val, str) or len(img_val) < MIN_ANNOTATION_LENGTH:
                    self._send_json(400, {"ok": False, "err": "image too short"})
                    return
                with STATE.lock:
                    STATE.annotated_b64 = img_val
                    STATE.annotated_seq = expected
                STATE.annotated_ready.set()
                self._send_json(200, {"ok": True, "seq": expected})
            case _:
                self._send_json(404, {"error": "not found"})

    def do_OPTIONS(self) -> None:
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", "0")
        self.end_headers()


def _run_select_region() -> tuple[str, int]:
    proc: subprocess.CompletedProcess[bytes] = subprocess.run(
        [sys.executable, str(WIN32_PATH), "select_region"],
        capture_output=True,
    )
    if proc.returncode == 2:
        return "", 2
    if proc.returncode != 0 or not proc.stdout:
        return "", proc.returncode
    return proc.stdout.decode("ascii").strip(), 0


def main() -> None:
    franz: object = _load_module("franz", "franz.py")
    brain: object = _load_module("brain", "brain.py")

    for name in ("SYSTEM_PROMPT", "on_vlm_response"):
        if not hasattr(brain, name):
            print(f"ERROR: brain.py missing: {name}")
            raise SystemExit(1)

    if not hasattr(franz, "_flush_pipes"):
        print("ERROR: franz.py missing: _flush_pipes")
        raise SystemExit(1)

    print("Select capture region (drag), right-click for full screen, Escape to quit.")
    region_str, exit_code = _run_select_region()

    if exit_code == 2:
        print("Cancelled.")
        raise SystemExit(0)

    if region_str:
        print(f"Region selected: {region_str}")
        _runtime_overrides["CAPTURE_REGION"] = region_str
        _runtime_overrides["CAPTURE_WIDTH"] = NO_RESIZE
        _runtime_overrides["CAPTURE_HEIGHT"] = NO_RESIZE
    else:
        print("Full screen mode.")
        _runtime_overrides["CAPTURE_REGION"] = ""

    session: SessionLog = SessionLog.create()
    host: str = str(_cfg(brain, "SERVER_HOST", "127.0.0.1"))
    port: int = int(_cfg(brain, "SERVER_PORT", 1234))

    print(f"Franz starting on http://{host}:{port}")
    print(f"VLM: {_cfg(brain, 'VLM_ENDPOINT_URL', '?')}")
    print(f"Region: {_cfg(brain, 'CAPTURE_REGION', '') or 'full screen'}")
    print(f"Session: {session.session_dir}")

    engine: threading.Thread = threading.Thread(
        target=_engine_loop, args=(brain, franz, session), daemon=True,
    )
    engine.start()

    server: http.server.HTTPServer = http.server.HTTPServer((host, port), FranzHandler)
    print(f"Running at http://{host}:{port}")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping.")
        server.shutdown()


if __name__ == "__main__":
    main()
