from __future__ import annotations

import argparse
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from command_runner import build_config, run_commands
from motor_driver import RobotDriver


ALLOWED_TYPES = {"FORWARD", "LEFT", "RIGHT", "STOP"}


def validate_commands(data: Any) -> list[dict[str, Any]]:
    if not isinstance(data, list) or not data:
        raise ValueError("Command JSON must be a non-empty list")
    for index, item in enumerate(data, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"Command #{index} must be an object")
        if item.get("type") not in ALLOWED_TYPES:
            raise ValueError(f"Command #{index} has invalid type: {item.get('type')}")
    return data


class CommandServer(ThreadingHTTPServer):
    def __init__(self, address: tuple[str, int], handler: type[BaseHTTPRequestHandler], args: argparse.Namespace):
        super().__init__(address, handler)
        self.args = args
        self.run_lock = threading.Lock()


class CommandHandler(BaseHTTPRequestHandler):
    server: CommandServer

    def _cors_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Private-Network", "true")

    def _reply(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self._cors_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self._cors_headers()
        self.end_headers()

    def do_POST(self) -> None:
        if self.path.rstrip("/") not in {"", "/commands"}:
            self._reply(404, {"error": "Not found"})
            return
        if not self.server.run_lock.acquire(blocking=False):
            self._reply(409, {"error": "Robot is already running"})
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > self.server.args.max_body_bytes:
                raise ValueError("Invalid request body size")
            commands = validate_commands(json.loads(self.rfile.read(length)))
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as error:
            self.server.run_lock.release()
            self._reply(400, {"error": str(error)})
            return

        self._reply(202, {"accepted": True, "commandCount": len(commands)})
        threading.Thread(target=self._execute, args=(commands,), daemon=True).start()

    def _execute(self, commands: list[dict[str, Any]]) -> None:
        try:
            config = build_config(self.server.args)
            with RobotDriver(config=config, dry_run=not self.server.args.live) as driver:
                run_commands(commands, driver, limit=None, step_delay=self.server.args.step_delay)
        except Exception as error:
            print(f"ERROR while running received commands: {error}")
        finally:
            self.server.run_lock.release()

    def log_message(self, format: str, *args: Any) -> None:
        print(f"{self.client_address[0]} - {format % args}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Receive and execute guide robot command JSON")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--live", action="store_true", help="Actually drive GPIO; default is dry-run")
    parser.add_argument("--max-body-bytes", type=int, default=1_000_000)
    parser.add_argument("--step-delay", type=float, default=0.05)
    parser.add_argument("--forward-seconds", type=float, default=0.70)
    parser.add_argument("--left-seconds", type=float, default=0.5)
    parser.add_argument("--right-seconds", type=float, default=0.5)
    parser.add_argument("--motor-speed", type=float, default=0.40)
    parser.add_argument("--turn-speed", type=float, default=0.38)
    parser.add_argument("--servo-center", type=float, default=0.0)
    parser.add_argument("--servo-left", type=float, default=0.85)
    parser.add_argument("--servo-right", type=float, default=-0.85)
    parser.add_argument("--servo-settle-seconds", type=float, default=0.18)
    parser.add_argument("--stop-delay-seconds", type=float, default=0.15)
    parser.add_argument("--turn-mode", choices=["STEER_AND_ONE_SIDE", "STEER_AND_BOTH_FORWARD", "STEER_AND_DIFF"], default="STEER_AND_DIFF")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    mode = "LIVE" if args.live else "DRY RUN"
    print(f"Command server listening on http://{args.host}:{args.port} ({mode})")
    CommandServer((args.host, args.port), CommandHandler, args).serve_forever()


if __name__ == "__main__":
    main()
