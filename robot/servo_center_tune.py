from __future__ import annotations

import time

from gpiozero import Servo
from gpiozero.pins.lgpio import LGPIOFactory


SERVO_PIN = 18


def clamp(value: float) -> float:
    return max(-1.0, min(1.0, value))


def main() -> None:
    factory = LGPIOFactory()
    servo = Servo(SERVO_PIN, pin_factory=factory)

    print("Servo center tuning")
    print("Input servo value like: 0, -0.01, -0.02, -0.03, 0.01")
    print("右に切る = マイナス方向")
    print("左に切る = プラス方向")
    print("q で終了")

    try:
        while True:
            raw = input("servo value > ").strip()

            if raw.lower() in {"q", "quit", "exit"}:
                break

            try:
                value = clamp(float(raw))
            except ValueError:
                print("number or q only")
                continue

            servo.value = value
            print(f"servo = {value:.4f}")
            time.sleep(0.3)

    finally:
        servo.value = 0.0
        time.sleep(0.2)
        servo.close()
        print("Done.")


if __name__ == "__main__":
    main()
