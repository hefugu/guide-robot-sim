from __future__ import annotations

import argparse
import time

from gpiozero import DigitalOutputDevice
from gpiozero.pins.lgpio import LGPIOFactory


factory = LGPIOFactory()

# L293D IN pins
left_in1 = DigitalOutputDevice(5, pin_factory=factory)
left_in2 = DigitalOutputDevice(6, pin_factory=factory)
right_in1 = DigitalOutputDevice(23, pin_factory=factory)
right_in2 = DigitalOutputDevice(24, pin_factory=factory)


def stop() -> None:
    left_in1.off()
    left_in2.off()
    right_in1.off()
    right_in2.off()


def left_forward() -> None:
    left_in1.on()
    left_in2.off()


def right_forward() -> None:
    right_in1.on()
    right_in2.off()


def left_backward() -> None:
    left_in1.off()
    left_in2.on()


def right_backward() -> None:
    right_in1.off()
    right_in2.on()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["left", "right", "both", "left_back", "right_back"])
    parser.add_argument("--seconds", type=float, default=2.0)
    args = parser.parse_args()

    try:
        stop()
        time.sleep(0.2)

        print(f"MODE: {args.mode}")
        print(f"RUN: {args.seconds} seconds")

        if args.mode == "left":
            left_forward()
        elif args.mode == "right":
            right_forward()
        elif args.mode == "both":
            left_forward()
            right_forward()
        elif args.mode == "left_back":
            left_backward()
        elif args.mode == "right_back":
            right_backward()

        time.sleep(args.seconds)

    finally:
        print("STOP")
        stop()

        left_in1.close()
        left_in2.close()
        right_in1.close()
        right_in2.close()


if __name__ == "__main__":
    main()
