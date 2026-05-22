from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


COMMAND_FILE = Path(__file__).with_name("test_commands.json")

# 仮の実行時間。実機測定前なので、今はprint確認用。
FORWARD_SECONDS = 0.15
TURN_SECONDS = 0.10
STOP_SECONDS = 0.20


def load_commands(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Command file not found: {path}")

    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, list):
        raise ValueError("Command JSON must be a list")

    commands: list[dict[str, Any]] = []

    for index, item in enumerate(data, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"Command #{index} must be an object")

        command_type = item.get("type")

        if not isinstance(command_type, str):
            raise ValueError(f"Command #{index} has no valid type")

        commands.append(item)

    return commands


def describe_command(command: dict[str, Any]) -> str:
    command_type = command.get("type")

    if command_type == "FORWARD":
        start = command.get("from", {})
        end = command.get("to", {})
        direction = command.get("direction", "?")

        return (
            f"FORWARD "
            f"({start.get('x')},{start.get('y')}) "
            f"-> ({end.get('x')},{end.get('y')}) "
            f"dir={direction}"
        )

    if command_type in {"LEFT", "RIGHT"}:
        return (
            f"{command_type} "
            f"{command.get('fromDirection', '?')} "
            f"-> {command.get('toDirection', '?')}"
        )

    if command_type == "STOP":
        return "STOP"

    if command_type == "ERROR":
        return f"ERROR {command.get('reason', '')}"

    return f"UNKNOWN {command_type}"


def execute_command_dry_run(command: dict[str, Any]) -> None:
    command_type = command.get("type")

    print(describe_command(command))

    if command_type == "FORWARD":
        time.sleep(FORWARD_SECONDS)
        return

    if command_type in {"LEFT", "RIGHT"}:
        time.sleep(TURN_SECONDS)
        return

    if command_type == "STOP":
        time.sleep(STOP_SECONDS)
        return

    if command_type == "ERROR":
        raise RuntimeError(f"Invalid command from JSON: {command}")

    raise ValueError(f"Unknown command type: {command_type}")


def run_commands(commands: list[dict[str, Any]]) -> None:
    print(f"Loaded {len(commands)} commands")
    print("=== DRY RUN START ===")

    for index, command in enumerate(commands, start=1):
        print(f"{index:03d}: ", end="")
        execute_command_dry_run(command)

    print("=== DRY RUN END ===")


def main() -> None:
    commands = load_commands(COMMAND_FILE)
    run_commands(commands)


if __name__ == "__main__":
    main()