from __future__ import annotations

import argparse
import time

from gpiozero import Servo
from gpiozero.pins.lgpio import LGPIOFactory


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--value", type=float, default=0.0)
    parser.add_argument("--hold", type=float, default=10.0)
    args = parser.parse_args()

    factory = LGPIOFactory()
    servo = Servo(18, pin_factory=factory)

    value = max(-1.0, min(1.0, args.value))

    try:
        print(f"Servo value = {value}")
        print(f"Holding for {args.hold} seconds...")
        servo.value = value
        time.sleep(args.hold)

    finally:
        servo.close()
        print("Done.")


if __name__ == "__main__":
    main()
