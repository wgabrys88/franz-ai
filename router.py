import base64
import http.server
import json
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import webbrowser
from dataclasses import dataclass, field
from pathlib import Path


HERE: Path = Path(__file__).resolve().parent
PANEL_PATH: Path = HERE / "panel.html"
WIN32_PATH: Path = HERE / "win32.py"


def _print_usage() -> None:
    sys.stdout.write(
        "Usage: python router.py <scenario.py>\n"
        "\n"
        "Examples:\n"
        "  python router.py chess.py\n"
        "  python router.py paint_cat.py\n"
        "  python router.py test_tools.py\n"
        "\n"
        "The scenario file defines CONFIG, route(), run_cycle(),\n"
        "and build_overlays(). See any example scenario for the template.\n"
    )
    sys.stdout.flush()


def _load_scenario(filepath: Path) -> object:
    import importlib.util
    spec: object = importlib.util.spec_from_file_location("scenario", str(filepath))
    if spec is None:
        raise ImportError(f"Cannot create module spec from {filepath}")
    loader: object = getattr(spec, "loader", None)
    if loader is None:
        raise ImportError(f"No loader for {filepath}")
    module: object = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def _validate_scenario(module: object, filepath: Path) -> None:
    missing: list[str] = []
    for name in ("CONFIG", "route", "run_cycle", "build_overlays"):
        if not hasattr(module, name):
            missing.append(name)
    if missing:
        raise ImportError(
            f"{filepath.name} is missing required attributes: {', '.join(missing)}\n"
            f"Every scenario must define: CONFIG, route(), run_cycle(), build_overlays()"
        )
    config: object = getattr(module, "CONFIG")
    for field_name in (
        "vlm_endpoint_url", "vlm_model_name", "vlm_temperature", "vlm_top_p",
        "vlm_max_tokens", "server_host", "server_port", "capture_region",
        "capture_width", "capture_height", "capture_delay_seconds",
        "system_prompt", "seed_vlm_text", "change_threshold",
    ):
        if not hasattr(config, field_name):
            raise ImportError(
                f"{filepath.name} CONFIG is missing field: {field_name}"
            )


@dataclass
class ServerState:
    phase: str = "init"
    turn: int = 0
    vlm_text: str = ""
    raw_b64: str = ""
    raw_seq: int = 0
    overlays: list[dict[str, object]] = field(default_factory=list)
    pending_seq: int = 0
    annotated_seq: int = -1
    annotated_b64: str = ""
    annotated_ready: threading.Event = field(default_factory=threading.Event)
    display_text: str = ""
    display_actions: list[dict[str, object]] = field(default_factory=list)
    error_text: str = ""
    lock: threading.Lock = field(default_factory=threading.Lock)


STATE: ServerState = ServerState()


def _subprocess_capture(scenario_mod: object) -> str:
    config: object = getattr(scenario_mod, "CONFIG")
    cmd_args: list[str] = [sys.executable, str(WIN32_PATH), "capture"]
    region: str = getattr(config, "capture_region", "")
    if region:
        cmd_args.extend(["--region", region])
    cmd_args.extend(["--width", str(getattr(config, "capture_width", 640))])
    cmd_args.extend(["--height", str(getattr(config, "capture_height", 640))])
    proc: subprocess.CompletedProcess[bytes] = subprocess.run(
        cmd_args, capture_output=True
    )
    if proc.returncode != 0 or not proc.stdout:
        return ""
    return base64.b64encode(proc.stdout).decode("ascii")


def _subprocess_execute(actions: list[dict[str, object]], scenario_mod: object) -> None:
    config: object = getattr(scenario_mod, "CONFIG")
    region_arg: str = getattr(config, "capture_region", "")

    drag_from: str = ""
    for action in actions:
        action_type_val: object = action.get("type", "")
        if not isinstance(action_type_val, str):
            continue
        action_type: str = action_type_val
        bbox_val: object = action.get("bbox_2d", [500, 500, 500, 500])
        if not isinstance(bbox_val, list):
            continue
        bbox_list: list[int] = [int(v) for v in bbox_val]
        if len(bbox_list) != 4:
            continue
        params_val: object = action.get("params", "")
        params_str: str = str(params_val) if params_val else ""
        bbox_str: str = f"{bbox_list[0]},{bbox_list[1]},{bbox_list[2]},{bbox_list[3]}"

        cmd_args: list[str] = [sys.executable, str(WIN32_PATH)]

        match action_type:
            case "click":
                cmd_args.extend(["click", "--bbox", bbox_str])
            case "double_click":
                cmd_args.extend(["double_click", "--bbox", bbox_str])
            case "right_click":
                cmd_args.extend(["right_click", "--bbox", bbox_str])
            case "type":
                cmd_args.extend(["type_text", "--text", params_str])
            case "hotkey":
                cmd_args.extend(["hotkey", "--keys", params_str])
            case "key":
                cmd_args.extend(["press_key", "--key", params_str])
            case "scroll_up":
                clicks_str: str = params_str if params_str.isdigit() else "3"
                cmd_args.extend(["scroll_up", "--bbox", bbox_str, "--clicks", clicks_str])
            case "scroll_down":
                clicks_str = params_str if params_str.isdigit() else "3"
                cmd_args.extend(["scroll_down", "--bbox", bbox_str, "--clicks", clicks_str])
            case "drag_start":
                drag_from = bbox_str
                continue
            case "drag_end":
                if drag_from:
                    drag_cmd: list[str] = [
                        sys.executable, str(WIN32_PATH), "drag",
                        "--from", drag_from, "--to", bbox_str,
                    ]
                    if region_arg:
                        drag_cmd.extend(["--region", region_arg])
                    subprocess.run(drag_cmd, capture_output=True)
                    drag_from = ""
                continue
            case _:
                continue

        if region_arg:
            cmd_args.extend(["--region", region_arg])

        subprocess.run(cmd_args, capture_output=True)


def _subprocess_compare(png_a: bytes, png_b: bytes) -> float:
    tmp_dir: str = tempfile.mkdtemp()
    path_a: Path = Path(tmp_dir) / "frame_a.png"
    path_b: Path = Path(tmp_dir) / "frame_b.png"
    path_a.write_bytes(png_a)
    path_b.write_bytes(png_b)
    proc: subprocess.CompletedProcess[bytes] = subprocess.run(
        [sys.executable, str(WIN32_PATH), "compare",
         "--file_a", str(path_a), "--file_b", str(path_b)],
        capture_output=True,
    )
    try:
        path_a.unlink(missing_ok=True)
        path_b.unlink(missing_ok=True)
        Path(tmp_dir).rmdir()
    except OSError:
        pass
    if proc.returncode != 0 or not proc.stdout:
        return -1.0
    try:
        return float(proc.stdout.decode("ascii").strip())
    except ValueError:
        return -1.0


def _call_vlm(annotated_b64: str, user_text: str, scenario_mod: object) -> str:
    config: object = getattr(scenario_mod, "CONFIG")
    endpoint: str = getattr(config, "vlm_endpoint_url", "")
    system_prompt: str = getattr(config, "system_prompt", "")

    user_content: list[dict[str, str | dict[str, str]]] = []
    if user_text:
        user_content.append({"type": "text", "text": user_text})
    user_content.append({
        "type": "image_url",
        "image_url": {"url": f"data:image/png;base64,{annotated_b64}"},
    })

    messages: list[dict[str, str | list[dict[str, str | dict[str, str]]]]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]

    body: bytes = json.dumps({
        "model": getattr(config, "vlm_model_name", ""),
        "temperature": getattr(config, "vlm_temperature", 0.6),
        "top_p": getattr(config, "vlm_top_p", 0.85),
        "max_tokens": getattr(config, "vlm_max_tokens", 800),
        "messages": messages,
    }).encode("utf-8")

    req: urllib.request.Request = urllib.request.Request(
        endpoint,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            resp_data: bytes = resp.read()
        resp_obj: object = json.loads(resp_data.decode("utf-8"))
        if isinstance(resp_obj, dict):
            choices: object = resp_obj.get("choices", [])
            if isinstance(choices, list) and len(choices) > 0:
                first_choice: object = choices[0]
                if isinstance(first_choice, dict):
                    message: object = first_choice.get("message", {})
                    if isinstance(message, dict):
                        content: object = message.get("content", "")
                        if isinstance(content, str):
                            return content
        return ""
    except Exception as exc:
        print(f"VLM error: {exc}", file=sys.stderr)
        return ""


def _engine_loop(scenario_mod: object) -> None:
    config: object = getattr(scenario_mod, "CONFIG")
    run_cycle_fn: object = getattr(scenario_mod, "run_cycle")
    build_overlays_fn: object = getattr(scenario_mod, "build_overlays")
    change_threshold: float = getattr(config, "change_threshold", 0.01)
    capture_delay: float = getattr(config, "capture_delay_seconds", 3.0)

    previous_response: str = getattr(config, "seed_vlm_text", "")
    previous_overlays: list[dict[str, object]] = []
    previous_png_bytes: bytes = b""

    def capture_fn() -> str:
        nonlocal previous_png_bytes
        if capture_delay > 0:
            time.sleep(capture_delay)
        raw_b64: str = _subprocess_capture(scenario_mod)
        if raw_b64:
            with STATE.lock:
                STATE.raw_b64 = raw_b64
                STATE.raw_seq += 1
        return raw_b64

    def execute_fn(actions: list[dict[str, object]]) -> None:
        with STATE.lock:
            STATE.display_actions = list(actions)
            STATE.phase = "executing"
        _subprocess_execute(actions, scenario_mod)

    def annotate_fn(screenshot_b64: str, overlays: list[dict[str, object]]) -> str:
        nonlocal previous_png_bytes
        if not screenshot_b64:
            return ""

        current_png_bytes: bytes = base64.b64decode(screenshot_b64)
        change_ratio: float = -1.0
        if previous_png_bytes:
            change_ratio = _subprocess_compare(previous_png_bytes, current_png_bytes)
        previous_png_bytes = current_png_bytes
        screen_changed: bool = change_ratio >= change_threshold if change_ratio >= 0 else True

        route_result_actions: list[dict[str, object]] = []
        with STATE.lock:
            route_result_actions = list(STATE.display_actions)

        final_overlays: list[dict[str, object]] = build_overlays_fn(
            route_result_actions, screen_changed, overlays
        )

        with STATE.lock:
            current_turn: int = STATE.turn
            STATE.overlays = final_overlays
            STATE.pending_seq = current_turn
            STATE.annotated_seq = -1
            STATE.annotated_b64 = ""
            STATE.annotated_ready.clear()
            STATE.phase = "waiting_annotated"

        STATE.annotated_ready.wait()

        with STATE.lock:
            return STATE.annotated_b64

    def call_vlm_fn(annotated_b64: str, user_text: str) -> str:
        with STATE.lock:
            STATE.phase = "calling_vlm"
        return _call_vlm(annotated_b64, user_text, scenario_mod)

    while True:
        with STATE.lock:
            STATE.turn += 1
            STATE.phase = "running"

        try:
            result_holder: object = run_cycle_fn(
                previous_response,
                previous_overlays,
                capture_fn,
                execute_fn,
                annotate_fn,
                call_vlm_fn,
            )

            next_response: str = ""
            next_overlays: list[dict[str, object]] = []

            if isinstance(result_holder, tuple) and len(result_holder) == 2:
                next_response = str(result_holder[0])
                next_overlays_raw: object = result_holder[1]
                next_overlays = next_overlays_raw if isinstance(next_overlays_raw, list) else []
            else:
                next_response = str(result_holder) if result_holder else ""

            if not next_response:
                with STATE.lock:
                    STATE.phase = "error"
                    STATE.error_text = "VLM returned empty response"
                time.sleep(1.0)
                next_response = previous_response

            with STATE.lock:
                STATE.vlm_text = next_response
                STATE.display_text = next_response

            previous_response = next_response
            previous_overlays = next_overlays

        except Exception as exc:
            with STATE.lock:
                STATE.phase = "error"
                STATE.error_text = str(exc)
            print(f"Engine error: {exc}", file=sys.stderr)
            time.sleep(2.0)


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
                if PANEL_PATH.exists():
                    self._send_html(200, PANEL_PATH.read_bytes())
                else:
                    self._send_json(404, {"error": "panel.html not found"})

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
                            "regions": [],
                            "actions": STATE.display_actions,
                            "parse_error": "",
                        },
                        "msg_id": STATE.turn,
                        "parse_error": "",
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
                parsed_body: object = None
                try:
                    parsed_body = json.loads(body.decode("utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    self._send_json(400, {"ok": False, "err": "bad json"})
                    return

                if not isinstance(parsed_body, dict):
                    self._send_json(400, {"ok": False, "err": "bad json"})
                    return

                seq_val: object = parsed_body.get("seq")
                img_val: object = parsed_body.get("image_b64", "")

                with STATE.lock:
                    expected_seq: int = STATE.pending_seq

                if seq_val != expected_seq:
                    self._send_json(409, {"ok": False, "err": "seq mismatch"})
                    return

                if not isinstance(img_val, str) or len(img_val) < 100:
                    self._send_json(400, {"ok": False, "err": "image too short"})
                    return

                with STATE.lock:
                    STATE.annotated_b64 = img_val
                    STATE.annotated_seq = expected_seq
                STATE.annotated_ready.set()
                self._send_json(200, {"ok": True, "seq": expected_seq})

            case _:
                self._send_json(404, {"error": "not found"})

    def do_OPTIONS(self) -> None:
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", "0")
        self.end_headers()


def main() -> None:
    if len(sys.argv) < 2:
        _print_usage()
        raise SystemExit(1)

    scenario_filename: str = sys.argv[1]
    scenario_path: Path = HERE / scenario_filename

    if not scenario_path.exists():
        abs_path: Path = Path(scenario_filename).resolve()
        if abs_path.exists():
            scenario_path = abs_path
        else:
            print(f"ERROR: Scenario file not found: {scenario_filename}")
            print(f"Looked in: {HERE}")
            raise SystemExit(1)

    print(f"Loading {scenario_path.name}...")
    try:
        scenario_mod: object = _load_scenario(scenario_path)
    except Exception as exc:
        print(f"ERROR: Failed to load {scenario_path.name}:")
        print(f"  {exc}")
        print(f"Fix {scenario_path.name} and restart.")
        raise SystemExit(1)

    try:
        _validate_scenario(scenario_mod, scenario_path)
    except ImportError as exc:
        print(f"ERROR: {exc}")
        raise SystemExit(1)

    config: object = getattr(scenario_mod, "CONFIG")
    host: str = getattr(config, "server_host", "127.0.0.1")
    port: int = getattr(config, "server_port", 1234)

    print(f"Franz starting on http://{host}:{port}")
    print(f"VLM endpoint: {getattr(config, 'vlm_endpoint_url', '?')}")
    print(f"Capture region: {getattr(config, 'capture_region', '') or 'full screen'}")
    print(f"Capture size: {getattr(config, 'capture_width', 640)}x{getattr(config, 'capture_height', 640)}")
    print(f"Scenario: {scenario_path.name}")

    engine_thread: threading.Thread = threading.Thread(
        target=_engine_loop, args=(scenario_mod,), daemon=True
    )
    engine_thread.start()

    server: http.server.HTTPServer = http.server.HTTPServer(
        (host, port), FranzHandler
    )
    print(f"Server running at http://{host}:{port}")

    webbrowser.open(f"http://{host}:{port}")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()


if __name__ == "__main__":
    main()
