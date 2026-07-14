from __future__ import annotations

import argparse
import time
from dataclasses import dataclass
from typing import Literal

import smbus
from gpiozero import DigitalOutputDevice, Servo
from gpiozero.pins.lgpio import LGPIOFactory


# =========================
# MPU6050 settings
# =========================

MPU_ADDR = 0x68

PWR_MGMT_1 = 0x6B
GYRO_CONFIG = 0x1B
GYRO_ZOUT_H = 0x47

GYRO_SCALE = 131.0  # ±250 deg/s


# =========================
# Robot settings
# =========================

TurnDirection = Literal["left", "right"]


@dataclass
class RobotPins:
    # L293D IN pins
    in1_l: int = 5
    in2_l: int = 6
    in1_r: int = 23
    in2_r: int = 24

    # Servo signal
    servo: int = 18


@dataclass
class TurnConfig:
    # servo values
    servo_center: float = 0.0
    servo_left: float = 0.85
    servo_right: float = -0.85

    # IMU turn control
    target_degrees: float = 88.0
    max_turn_seconds: float = 2.0

    # timing
    servo_settle_seconds: float = 0.50
    stop_delay_seconds: float = 0.30

    # gyro noise cut
    gyro_deadband: float = 0.8

    # motor mode
    # left turn:  left motor backward, right motor forward
    # right turn: left motor forward,  right motor backward
    use_diff_turn: bool = True


class MPU6050Gyro:
    def __init__(self, bus_number: int = 1) -> None:
        self.bus = smbus.SMBus(bus_number)
        self.offset_z = 0.0

    def setup(self) -> None:
        # Wake up MPU6050
        self.bus.write_byte_data(MPU_ADDR, PWR_MGMT_1, 0)

        # Gyro range ±250 deg/s
        self.bus.write_byte_data(MPU_ADDR, GYRO_CONFIG, 0x00)

        time.sleep(0.1)

    def read_word_2c(self, reg: int) -> int:
        high = self.bus.read_byte_data(MPU_ADDR, reg)
        low = self.bus.read_byte_data(MPU_ADDR, reg + 1)
        value = (high << 8) + low

        if value >= 0x8000:
            value = -((65535 - value) + 1)

        return value

    def read_gyro_z(self) -> float:
        return self.read_word_2c(GYRO_ZOUT_H) / GYRO_SCALE

    def calibrate_z(self, seconds: float = 2.0) -> float:
        print("Calibrating gyro_z offset. Keep robot still...")

        values: list[float] = []
        start = time.monotonic()

        while time.monotonic() - start < seconds:
            values.append(self.read_gyro_z())
            time.sleep(0.01)

        self.offset_z = sum(values) / len(values)
        print(f"gyro_z offset = {self.offset_z:.3f} deg/s")
        return self.offset_z

    def read_corrected_z(self, deadband: float = 0.8) -> float:
        z = self.read_gyro_z() - self.offset_z

        if abs(z) < deadband:
            return 0.0

        return z


class RobotTurnDriver:
    def __init__(self, pins: RobotPins, config: TurnConfig) -> None:
        self.pins = pins
        self.config = config

        self.factory = LGPIOFactory()

        self.left_in1: DigitalOutputDevice | None = None
        self.left_in2: DigitalOutputDevice | None = None
        self.right_in1: DigitalOutputDevice | None = None
        self.right_in2: DigitalOutputDevice | None = None
        self.servo: Servo | None = None

    def setup(self) -> None:
        self.left_in1 = DigitalOutputDevice(self.pins.in1_l, pin_factory=self.factory)
        self.left_in2 = DigitalOutputDevice(self.pins.in2_l, pin_factory=self.factory)
        self.right_in1 = DigitalOutputDevice(self.pins.in1_r, pin_factory=self.factory)
        self.right_in2 = DigitalOutputDevice(self.pins.in2_r, pin_factory=self.factory)

        self.servo = Servo(self.pins.servo, pin_factory=self.factory)

        self.stop()
        self.set_servo(self.config.servo_center)
        time.sleep(self.config.stop_delay_seconds)

    def close(self) -> None:
        self.stop()

        if self.servo is not None:
            self.servo.value = self.config.servo_center
            time.sleep(0.1)
            self.servo.close()

        for device in [
            self.left_in1,
            self.left_in2,
            self.right_in1,
            self.right_in2,
        ]:
            if device is not None:
                device.close()

    def require_devices(self) -> None:
        if (
            self.left_in1 is None
            or self.left_in2 is None
            or self.right_in1 is None
            or self.right_in2 is None
            or self.servo is None
        ):
            raise RuntimeError("RobotTurnDriver.setup() has not been called.")

    def set_servo(self, value: float) -> None:
        self.require_devices()
        assert self.servo is not None

        value = max(-1.0, min(1.0, value))
        self.servo.value = value

    def stop(self) -> None:
        if self.left_in1 is not None:
            self.left_in1.off()
        if self.left_in2 is not None:
            self.left_in2.off()
        if self.right_in1 is not None:
            self.right_in1.off()
        if self.right_in2 is not None:
            self.right_in2.off()

    def left_forward(self) -> None:
        self.require_devices()
        assert self.left_in1 is not None
        assert self.left_in2 is not None

        self.left_in1.on()
        self.left_in2.off()

    def left_backward(self) -> None:
        self.require_devices()
        assert self.left_in1 is not None
        assert self.left_in2 is not None

        self.left_in1.off()
        self.left_in2.on()

    def right_forward(self) -> None:
        self.require_devices()
        assert self.right_in1 is not None
        assert self.right_in2 is not None

        self.right_in1.on()
        self.right_in2.off()

    def right_backward(self) -> None:
        self.require_devices()
        assert self.right_in1 is not None
        assert self.right_in2 is not None

        self.right_in1.off()
        self.right_in2.on()

    def start_turn_motors(self, direction: TurnDirection) -> None:
        if direction == "left":
            # LEFT:
            # servo left
            # left motor backward
            # right motor forward
            self.left_backward()
            self.right_forward()

        elif direction == "right":
            # RIGHT:
            # servo right
            # left motor forward
            # right motor backward
            self.left_forward()
            self.right_backward()

        else:
            raise ValueError(f"Unknown direction: {direction}")

    def imu_turn_90(
        self,
        gyro: MPU6050Gyro,
        direction: TurnDirection,
    ) -> float:
        self.require_devices()

        if direction == "left":
            servo_value = self.config.servo_left
            target = abs(self.config.target_degrees)
            reached = lambda angle: angle >= target
            print(f"IMU LEFT turn target: +{target:.1f} deg")

        elif direction == "right":
            servo_value = self.config.servo_right
            target = -abs(self.config.target_degrees)
            reached = lambda angle: angle <= target
            print(f"IMU RIGHT turn target: {target:.1f} deg")

        else:
            raise ValueError(f"Unknown direction: {direction}")

        # stop before turn
        self.stop()
        time.sleep(self.config.stop_delay_seconds)

        # cut steering first
        self.set_servo(servo_value)
        time.sleep(self.config.servo_settle_seconds)

        angle = 0.0
        last_time = time.monotonic()
        start_time = last_time

        # start motors after servo reached angle
        self.start_turn_motors(direction)

        try:
            while True:
                now = time.monotonic()
                dt = now - last_time
                last_time = now

                corrected_z = gyro.read_corrected_z(deadband=self.config.gyro_deadband)
                angle += corrected_z * dt

                print(
                    f"z={corrected_z:8.2f} deg/s  "
                    f"angle={angle:8.2f} deg",
                    end="\r",
                )

                if reached(angle):
                    print()
                    print(f"Target reached. angle={angle:.2f} deg")
                    break

                if now - start_time > self.config.max_turn_seconds:
                    print()
                    print(
                        f"TIMEOUT. angle={angle:.2f} deg. "
                        "Stopping for safety."
                    )
                    break

                time.sleep(0.01)

        finally:
            self.stop()
            time.sleep(self.config.stop_delay_seconds)
            self.set_servo(self.config.servo_center)
            time.sleep(self.config.servo_settle_seconds)

        return angle


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="IMU based 90 degree turn test for guide robot."
    )

    parser.add_argument(
        "direction",
        choices=["left", "right"],
        help="Turn direction",
    )

    parser.add_argument(
        "--target",
        type=float,
        default=88.0,
        help="Target angle in degrees. Use 85-90 to tune stopping inertia.",
    )

    parser.add_argument(
        "--max-turn-seconds",
        type=float,
        default=2.0,
        help="Safety timeout seconds",
    )

    parser.add_argument(
        "--servo-center",
        type=float,
        default=0.0,
        help="Servo center value",
    )

    parser.add_argument(
        "--servo-left",
        type=float,
        default=0.85,
        help="Servo left value",
    )

    parser.add_argument(
        "--servo-right",
        type=float,
        default=-0.85,
        help="Servo right value",
    )

    parser.add_argument(
        "--servo-settle-seconds",
        type=float,
        default=0.50,
        help="Wait time after moving servo",
    )

    parser.add_argument(
        "--stop-delay-seconds",
        type=float,
        default=0.30,
        help="Wait time after stopping motors",
    )

    parser.add_argument(
        "--gyro-deadband",
        type=float,
        default=0.8,
        help="Ignore small gyro noise below this deg/s",
    )

    parser.add_argument(
        "--calibration-seconds",
        type=float,
        default=2.0,
        help="Gyro offset calibration time. Keep robot still.",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    pins = RobotPins()

    config = TurnConfig(
        servo_center=args.servo_center,
        servo_left=args.servo_left,
        servo_right=args.servo_right,
        target_degrees=args.target,
        max_turn_seconds=args.max_turn_seconds,
        servo_settle_seconds=args.servo_settle_seconds,
        stop_delay_seconds=args.stop_delay_seconds,
        gyro_deadband=args.gyro_deadband,
    )

    gyro = MPU6050Gyro(bus_number=1)
    driver = RobotTurnDriver(pins=pins, config=config)

    gyro.setup()

    print("Robot must stay still during calibration.")
    gyro.calibrate_z(seconds=args.calibration_seconds)

    print("Setting up motors and servo...")
    driver.setup()

    try:
        final_angle = driver.imu_turn_90(gyro=gyro, direction=args.direction)
        print(f"Final angle = {final_angle:.2f} deg")

    finally:
        driver.close()
        print("Done.")


if __name__ == "__main__":
    main()
