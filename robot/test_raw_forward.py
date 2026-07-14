from __future__ import annotations

import argparse
import time

from gpiozero import DigitalOutputDevice, Servo
from gpiozero.pins.lgpio import LGPIOFactory


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seconds", type=float, default=0.70)
    parser.add_argument("--servo-center", type=float, default=0.0)
    args = parser.parse_args()

    factory = LGPIOFactory()

    left_in1 = DigitalOutputDevice(5, pin_factory=factory)
    left_in2 = DigitalOutputDevice(6, pin_factory=factory)
    right_in1 = DigitalOutputDevice(23, pin_factory=factory)
    right_in2 = DigitalOutputDevice(24, pin_factory=factory)
    servo = Servo(18, pin_factory=factory)

    def stop() -> None:
        left_in1.off()
        left_in2.off()
        right_in1.off()
        right_in2.off()

    try:
        print(f"RAW FORWARD: {args.seconds}s / servo={args.servo_center}")
        stop()

        servo.value = args.servo_center
        time.sleep(0.6)

        left_in1.on()
        left_in2.off()
        right_in1.on()
        right_in2.off()

        time.sleep(args.seconds)

    finally:
        print("STOP")
        stop()
        servo.value = args.servo_center
        time.sleep(0.2)

        left_in1.close()
        left_in2.close()
        right_in1.close()
        right_in2.close()
        servo.close()


if __name__ == "__main__":
    main()
