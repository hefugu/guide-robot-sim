from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

from motor_driver import RobotConfig, RobotDriver


DEFAULT_COMMAND_FILE = Path(__file__).with_name("test_commands.json")


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

        if command_type not in {"FORWARD", "LEFT", "RIGHT", "STOP", "ERROR"}:
            raise ValueError(f"Command #{index} has unknown type: {command_type}")

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


def build_config(args: argparse.Namespace) -> RobotConfig:
    return RobotConfig(
        forward_one_cell_seconds=args.forward_seconds,
        left_90_seconds=args.left_seconds,
        right_90_seconds=args.right_seconds,
        motor_speed=args.motor_speed,
        turn_speed=args.turn_speed,
        servo_center_us=args.servo_center,
        servo_left_us=args.servo_left,
        servo_right_us=args.servo_right,
        turn_mode=args.turn_mode,
    )


def execute_command(
    driver: RobotDriver,
    command: dict[str, Any],
    step_delay: float,
) -> None:
    command_type = command.get("type")

    print(describe_command(command))

    if command_type == "ERROR":
        raise RuntimeError(f"Invalid command from JSON: {command}")

    if not isinstance(command_type, str):
        raise ValueError(f"Invalid command type: {command_type}")

    driver.execute_type(command_type)

    if step_delay > 0:
        time.sleep(step_delay)


def run_commands(
    commands: list[dict[str, Any]],
    driver: RobotDriver,
    limit: int | None,
    step_delay: float,
) -> None:
    total = len(commands)
    selected = commands[:limit] if limit is not None else commands

    print(f"Loaded {total} commands")
    print(f"Running {len(selected)} commands")
    print("=== RUN START ===")

    for index, command in enumerate(selected, start=1):
        print(f"{index:03d}: ", end="")
        execute_command(driver, command, step_delay)

    print("=== RUN END ===")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run guide robot command JSON",
    )

    parser.add_argument(
        "--file",
        type=Path,
        default=DEFAULT_COMMAND_FILE,
        help="Command JSON file path",
    )

    parser.add_argument(
        "--live",
        action="store_true",
        help="Actually drive GPIO and servo. Without this, dry-run only.",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Run only first N commands. Useful for safe testing.",
    )

    parser.add_argument(
        "--step-delay",
        type=float,
        default=0.05,
        help="Delay between commands",
    )

    parser.add_argument(
        "--forward-seconds",
        type=float,
        default=0.80,
        help="Seconds to drive forward for one grid cell",
    )

    parser.add_argument(
        "--left-seconds",
        type=float,
        default=0.55,
        help="Seconds for left 90 degree turn",
    )

    parser.add_argument(
        "--right-seconds",
        type=float,
        default=0.55,
        help="Seconds for right 90 degree turn",
    )

    parser.add_argument(
        "--motor-speed",
        type=float,
        default=0.40,
        help="Forward motor speed 0.0 to 1.0",
    )

    parser.add_argument(
        "--turn-speed",
        type=float,
        default=0.38,
        help="Turn motor speed 0.0 to 1.0",
    )

    parser.add_argument(
        "--servo-center",
        type=int,
        default=1500,
        help="Servo center pulse width in microseconds",
    )

    parser.add_argument(
        "--servo-left",
        type=int,
        default=1100,
        help="Servo left pulse width in microseconds",
    )

    parser.add_argument(
        "--servo-right",
        type=int,
        default=1900,
        help="Servo right pulse width in microseconds",
    )

    parser.add_argument(
        "--turn-mode",
        choices=[
            "STEER_AND_ONE_SIDE",
            "STEER_AND_BOTH_FORWARD",
            "STEER_AND_DIFF",
        ],
        default="STEER_AND_ONE_SIDE",
        help="How to rotate during LEFT/RIGHT commands",
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    commands = load_commands(args.file)
    config = build_config(args)

    dry_run = not args.live

    if dry_run:
        print("MODE: DRY RUN. GPIO will not be used.")
    else:
        print("MODE: LIVE. Robot will move.")
        print("Press Ctrl+C to emergency stop.")

    try:
        with RobotDriver(config=config, dry_run=dry_run) as driver:
            run_commands(
                commands=commands,
                driver=driver,
                limit=args.limit,
                step_delay=args.step_delay,
            )
    except KeyboardInterrupt:
        print("\nInterrupted. Stopping robot.")
        return 130
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())