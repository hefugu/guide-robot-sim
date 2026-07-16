from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Literal

import smbus

import board
import busio
import adafruit_tca9548a
import adafruit_vl53l1x

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


CommandType = Literal["FORWARD", "LEFT", "RIGHT", "STOP"]
TurnMode = Literal["STEER_AND_ONE_SIDE", "STEER_AND_BOTH_FORWARD", "STEER_AND_DIFF"]
TurnServoMode = Literal["CENTER", "STEER"]


def clamp(value: float, min_value: float, max_value: float) -> float:
    return max(min_value, min(max_value, value))


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
class RobotConfig:
    # movement calibration
    forward_one_cell_seconds: float = 0.70
    left_90_seconds: float = 0.50
    right_90_seconds: float = 0.50

    # kept for compatibility with command_runner.py
    # DigitalOutputDevice版では速度値は符号だけ使う
    motor_speed: float = 1.00
    turn_speed: float = 1.00

    # servo values
    # 現状の車体では -0.03 付近が一番マシだったためデフォルトにする
    servo_center_value: float = 0.0
    servo_left_value: float = 0.85
    servo_right_value: float = -0.85

    # timing
    servo_settle_seconds: float = 0.50
    stop_delay_seconds: float = 0.30

    # command delay is handled in command_runner.py
    turn_mode: TurnMode = "STEER_AND_DIFF"

    # 差動旋回時は前輪をセンターにした方が横流れしにくい
    turn_servo_mode: TurnServoMode = "CENTER"

    # IMU turn settings
    use_imu_turn: bool = True
    imu_left_target_degrees: float = 85.0
    imu_right_target_degrees: float = 88.0
    imu_max_turn_seconds: float = 2.0
    imu_calibration_seconds: float = 2.0
    gyro_deadband: float = 0.8

    # IMU forward heading hold
    use_imu_forward: bool = True
    forward_heading_kp: float = 0.020
    forward_heading_limit: float = 0.25
    forward_loop_sleep: float = 0.03

    # ToF wall correction during forward
    use_tof_forward: bool = True
    tof_left_channel: int = 0
    tof_right_channel: int = 1

    # 左右両壁が見える時の中央維持
    tof_wall_kp: float = 0.0015

    # 片側壁だけ見える時、そのFORWARD開始時の距離を維持する弱い補正
    tof_single_wall_kp: float = 0.0012

    # ToF補正の最大量
    tof_wall_limit: float = 0.12

    # VL53L1Xの有効距離範囲
    tof_min_valid_cm: float = 20.0
    tof_max_valid_cm: float = 300.0

    # 廊下幅の目安。両側壁判定に使う。
    tof_expected_width_cm: float = 290.0
    tof_width_tolerance_cm: float = 65.0

    # 片側がこれより遠い時は「壁ではなく階段/開口部かも」と判断
    tof_side_wall_max_for_both_cm: float = 220.0

    # ToFの平滑化
    tof_smoothing_alpha: float = 0.35

    # ToFが一時的に読めない時、前回補正を少しずつ抜く
    tof_correction_decay: float = 0.85


class MPU6050Gyro:
    def __init__(self, bus_number: int = 1) -> None:
        self.bus = smbus.SMBus(bus_number)
        self.offset_z = 0.0
        self.is_ready = False

    def setup(self) -> None:
        self.bus.write_byte_data(MPU_ADDR, PWR_MGMT_1, 0)
        self.bus.write_byte_data(MPU_ADDR, GYRO_CONFIG, 0x00)
        time.sleep(0.1)
        self.is_ready = True

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
        print("Calibrating MPU6050 gyro_z offset. Keep robot still...")

        values: list[float] = []
        start = time.monotonic()

        while time.monotonic() - start < seconds:
            values.append(self.read_gyro_z())
            time.sleep(0.01)

        self.offset_z = sum(values) / len(values)
        print(f"gyro_z offset = {self.offset_z:.3f} deg/s")
        return self.offset_z

    def read_corrected_z(self, deadband: float = 0.8) -> float:
        try:
            z = self.read_gyro_z() - self.offset_z
        except OSError as error:
            print(f"\nWARNING: MPU6050 I2C read failed: {error}")
            return 0.0

        if abs(z) < deadband:
            return 0.0

        return z


class WallToFSensors:
    def __init__(
        self,
        left_channel: int = 0,
        right_channel: int = 1,
        min_valid_cm: float = 20.0,
        max_valid_cm: float = 300.0,
    ) -> None:
        self.left_channel = left_channel
        self.right_channel = right_channel
        self.min_valid_cm = min_valid_cm
        self.max_valid_cm = max_valid_cm

        self.i2c: Any | None = None
        self.tca: Any | None = None
        self.left_sensor: Any | None = None
        self.right_sensor: Any | None = None
        self.is_ready = False

    def setup(self) -> None:
        print("Starting TCA9548A + VL53L1X wall sensors...")

        self.i2c = busio.I2C(board.SCL, board.SDA)
        self.tca = adafruit_tca9548a.TCA9548A(self.i2c)

        self.left_sensor = self._make_sensor(self.left_channel)
        self.right_sensor = self._make_sensor(self.right_channel)

        self.is_ready = True
        print(
            "ToF wall sensors: ENABLED "
            f"(left CH{self.left_channel}, right CH{self.right_channel})"
        )

    def _make_sensor(self, channel: int) -> Any:
        assert self.tca is not None

        sensor = adafruit_vl53l1x.VL53L1X(self.tca[channel])

        # 1 = short, 2 = long
        sensor.distance_mode = 2

        # milliseconds
        sensor.timing_budget = 100

        sensor.start_ranging()
        return sensor

    def _read_sensor_cm(self, sensor: Any | None) -> float | None:
        if sensor is None:
            return None

        try:
            if not sensor.data_ready:
                return None

            distance = sensor.distance
            sensor.clear_interrupt()

        except OSError as error:
            print(f"\nWARNING: VL53L1X I2C read failed: {error}")
            return None

        if distance is None:
            return None

        distance_cm = float(distance)

        if distance_cm < self.min_valid_cm:
            return None

        if distance_cm > self.max_valid_cm:
            return None

        return distance_cm

    def read_left_right_cm(self) -> tuple[float | None, float | None]:
        if not self.is_ready:
            return None, None

        left_cm = self._read_sensor_cm(self.left_sensor)
        right_cm = self._read_sensor_cm(self.right_sensor)

        return left_cm, right_cm

    def close(self) -> None:
        for sensor in [self.left_sensor, self.right_sensor]:
            try:
                if sensor is not None:
                    sensor.stop_ranging()
            except Exception as error:
                print(f"WARNING: VL53L1X stop_ranging failed: {error}")


class RobotDriver:
    def __init__(
        self,
        pins: RobotPins | None = None,
        config: RobotConfig | None = None,
        dry_run: bool = True,
    ) -> None:
        self.pins = pins if pins is not None else RobotPins()
        self.config = config if config is not None else RobotConfig()
        self.dry_run = dry_run

        self.factory = LGPIOFactory()

        self.left_in1: DigitalOutputDevice | None = None
        self.left_in2: DigitalOutputDevice | None = None
        self.right_in1: DigitalOutputDevice | None = None
        self.right_in2: DigitalOutputDevice | None = None
        self.servo: Servo | None = None

        self.gyro: MPU6050Gyro | None = None
        self.wall_sensors: WallToFSensors | None = None

    def __enter__(self) -> "RobotDriver":
        self.setup()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()

    def setup(self) -> None:
        if self.dry_run:
            print("DRY RUN: RobotDriver setup skipped.")
            return

        self.left_in1 = DigitalOutputDevice(self.pins.in1_l, pin_factory=self.factory)
        self.left_in2 = DigitalOutputDevice(self.pins.in2_l, pin_factory=self.factory)
        self.right_in1 = DigitalOutputDevice(self.pins.in1_r, pin_factory=self.factory)
        self.right_in2 = DigitalOutputDevice(self.pins.in2_r, pin_factory=self.factory)

        self.servo = Servo(self.pins.servo, pin_factory=self.factory)

        self.stop()
        self.set_servo(self.config.servo_center_value)
        time.sleep(self.config.stop_delay_seconds)

        if self.config.use_imu_turn or self.config.use_imu_forward:
            try:
                self.gyro = MPU6050Gyro(bus_number=1)
                self.gyro.setup()
                self.gyro.calibrate_z(seconds=self.config.imu_calibration_seconds)
                print("MPU6050 IMU mode: ENABLED")

            except Exception as error:
                print("WARNING: MPU6050 setup failed.")
                print(f"Reason: {error}")
                print("Fallback: timed turn / no heading hold will be used.")
                self.gyro = None

    def close(self) -> None:
        if self.dry_run:
            print("DRY RUN: RobotDriver close.")
            return

        try:
            self.stop()
        except Exception as error:
            print(f"WARNING: stop during close failed: {error}")

        try:
            if self.wall_sensors is not None:
                self.wall_sensors.close()
        except Exception as error:
            print(f"WARNING: wall sensors close failed: {error}")

        try:
            if self.servo is not None:
                self.servo.value = self.config.servo_center_value
                time.sleep(0.1)
                self.servo.close()
        except Exception as error:
            print(f"WARNING: servo close failed: {error}")

        for name, device in [
            ("left_in1", self.left_in1),
            ("left_in2", self.left_in2),
            ("right_in1", self.right_in1),
            ("right_in2", self.right_in2),
        ]:
            try:
                if device is not None:
                    device.close()
            except Exception as error:
                print(f"WARNING: {name} close failed: {error}")

    def require_devices(self) -> None:
        if self.dry_run:
            return

        if (
            self.left_in1 is None
            or self.left_in2 is None
            or self.right_in1 is None
            or self.right_in2 is None
            or self.servo is None
        ):
            raise RuntimeError("RobotDriver.setup() has not been called.")

    def set_servo(self, value: float) -> None:
        self.require_devices()

        value = clamp(value, -1.0, 1.0)

        if self.dry_run:
            print(f"DRY RUN: servo={value:.3f}")
            return

        assert self.servo is not None
        self.servo.value = value

    def stop(self) -> None:
        if self.dry_run:
            print("DRY RUN: stop motors")
            return

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

        if self.dry_run:
            print("DRY RUN: left forward")
            return

        assert self.left_in1 is not None
        assert self.left_in2 is not None

        self.left_in1.on()
        self.left_in2.off()

    def left_backward(self) -> None:
        self.require_devices()

        if self.dry_run:
            print("DRY RUN: left backward")
            return

        assert self.left_in1 is not None
        assert self.left_in2 is not None

        self.left_in1.off()
        self.left_in2.on()

    def right_forward(self) -> None:
        self.require_devices()

        if self.dry_run:
            print("DRY RUN: right forward")
            return

        assert self.right_in1 is not None
        assert self.right_in2 is not None

        self.right_in1.on()
        self.right_in2.off()

    def right_backward(self) -> None:
        self.require_devices()

        if self.dry_run:
            print("DRY RUN: right backward")
            return

        assert self.right_in1 is not None
        assert self.right_in2 is not None

        self.right_in1.off()
        self.right_in2.on()

    def set_motors(self, left_speed: float, right_speed: float) -> None:
        if self.dry_run:
            print(f"DRY RUN: motors left={left_speed:.2f} right={right_speed:.2f}")
            return

        if left_speed > 0:
            self.left_forward()
        elif left_speed < 0:
            self.left_backward()
        else:
            assert self.left_in1 is not None
            assert self.left_in2 is not None
            self.left_in1.off()
            self.left_in2.off()

        if right_speed > 0:
            self.right_forward()
        elif right_speed < 0:
            self.right_backward()
        else:
            assert self.right_in1 is not None
            assert self.right_in2 is not None
            self.right_in1.off()
            self.right_in2.off()

    def setup_tof_if_needed(self) -> None:
        if self.dry_run:
            return

        if not self.config.use_tof_forward:
            return

        if self.wall_sensors is not None:
            return

        try:
            self.wall_sensors = WallToFSensors(
                left_channel=self.config.tof_left_channel,
                right_channel=self.config.tof_right_channel,
                min_valid_cm=self.config.tof_min_valid_cm,
                max_valid_cm=self.config.tof_max_valid_cm,
            )
            self.wall_sensors.setup()

        except Exception as error:
            print("WARNING: ToF wall sensors setup failed.")
            print(f"Reason: {error}")
            print("Fallback: IMU-only forward correction will be used.")
            self.wall_sensors = None

    def smooth_value(self, previous: float | None, new_value: float | None) -> float | None:
        if new_value is None:
            return previous

        if previous is None:
            return new_value

        alpha = self.config.tof_smoothing_alpha
        return previous * (1.0 - alpha) + new_value * alpha

    def compute_tof_wall_correction(
        self,
        left_cm: float | None,
        right_cm: float | None,
        left_baseline_cm: float | None,
        right_baseline_cm: float | None,
        last_wall_correction: float,
    ) -> tuple[float, str, float | None, float | None, float | None]:
        """
        Returns:
            correction
            mode
            wall_error
            new_left_baseline
            new_right_baseline
        """

        new_left_baseline = left_baseline_cm
        new_right_baseline = right_baseline_cm

        if left_cm is None and right_cm is None:
            return (
                last_wall_correction * self.config.tof_correction_decay,
                "IMU_ONLY",
                None,
                new_left_baseline,
                new_right_baseline,
            )

        left_wall_like = (
            left_cm is not None
            and left_cm <= self.config.tof_side_wall_max_for_both_cm
        )

        right_wall_like = (
            right_cm is not None
            and right_cm <= self.config.tof_side_wall_max_for_both_cm
        )

        # 両側が壁っぽく、合計幅も廊下幅として自然なら中央維持
        if left_wall_like and right_wall_like and left_cm is not None and right_cm is not None:
            width_cm = left_cm + right_cm
            min_width = self.config.tof_expected_width_cm - self.config.tof_width_tolerance_cm
            max_width = self.config.tof_expected_width_cm + self.config.tof_width_tolerance_cm

            if min_width <= width_cm <= max_width:
                wall_error = left_cm - right_cm

                # wall_error < 0:
                #   左壁が近い -> 車体が左寄り -> 右へ補正 -> negative
                #
                # wall_error > 0:
                #   右壁が近い -> 車体が右寄り -> 左へ補正 -> positive
                correction = wall_error * self.config.tof_wall_kp
                correction = clamp(
                    correction,
                    -self.config.tof_wall_limit,
                    self.config.tof_wall_limit,
                )

                return correction, "BOTH_WALLS", wall_error, new_left_baseline, new_right_baseline

        # 片側だけ壁っぽい時は「固定目標距離」ではなく、
        # そのFORWARD開始時の距離を維持する。
        # これなら階段/開口部の位置やロボの向きが変わっても破綻しにくい。
        if left_wall_like and left_cm is not None and not right_wall_like:
            if new_left_baseline is None:
                new_left_baseline = left_cm

            wall_error = left_cm - new_left_baseline

            # left_cm が小さくなった -> 左壁に近づいた -> 右へ補正 -> negative
            # left_cm が大きくなった -> 左壁から離れた -> 左へ補正 -> positive
            correction = wall_error * self.config.tof_single_wall_kp
            correction = clamp(
                correction,
                -self.config.tof_wall_limit,
                self.config.tof_wall_limit,
            )

            return correction, "LEFT_WALL_HOLD", wall_error, new_left_baseline, new_right_baseline

        if right_wall_like and right_cm is not None and not left_wall_like:
            if new_right_baseline is None:
                new_right_baseline = right_cm

            wall_error = new_right_baseline - right_cm

            # right_cm が小さくなった -> 右壁に近づいた -> 左へ補正 -> positive
            # right_cm が大きくなった -> 右壁から離れた -> 右へ補正 -> negative
            correction = wall_error * self.config.tof_single_wall_kp
            correction = clamp(
                correction,
                -self.config.tof_wall_limit,
                self.config.tof_wall_limit,
            )

            return correction, "RIGHT_WALL_HOLD", wall_error, new_left_baseline, new_right_baseline

        # 階段/開口部/値飛びっぽい時はToFを弱めて、IMU主体に戻す
        return (
            last_wall_correction * self.config.tof_correction_decay,
            "IMU_ONLY",
            None,
            new_left_baseline,
            new_right_baseline,
        )

    def forward_cells(self, cell_count: int = 1) -> None:
        self.require_devices()

        if cell_count < 1:
            raise ValueError("cell_count must be 1 or greater")

        forward_seconds = self.config.forward_one_cell_seconds * cell_count
        print(f"FORWARD x{cell_count}: {forward_seconds:.2f}s continuous")

        self.stop()
        time.sleep(self.config.stop_delay_seconds)

        self.set_servo(self.config.servo_center_value)
        time.sleep(self.config.servo_settle_seconds)

        self.setup_tof_if_needed()

        use_heading_hold = (
            self.config.use_imu_forward
            and self.gyro is not None
        )

        use_tof = (
            self.config.use_tof_forward
            and self.wall_sensors is not None
        )

        angle = 0.0
        last_time = time.monotonic()
        start_time = last_time

        left_filtered: float | None = None
        right_filtered: float | None = None

        left_baseline_cm: float | None = None
        right_baseline_cm: float | None = None

        last_wall_error: float | None = None
        last_wall_correction = 0.0
        tof_mode = "IMU_ONLY"

        self.set_motors(1.0, 1.0)

        try:
            while True:
                now = time.monotonic()
                dt = now - last_time
                last_time = now

                elapsed = now - start_time

                imu_correction = 0.0
                wall_correction = 0.0

                if use_heading_hold and self.gyro is not None:
                    corrected_z = self.gyro.read_corrected_z(
                        deadband=self.config.gyro_deadband
                    )
                    angle += corrected_z * dt

                    # left yaw  = positive angle
                    # right yaw = negative angle
                    #
                    # servo-left  = positive
                    # servo-right = negative
                    #
                    # left yaw  -> steer right -> negative correction
                    # right yaw -> steer left  -> positive correction
                    imu_correction = -angle * self.config.forward_heading_kp

                if use_tof and self.wall_sensors is not None:
                    raw_left_cm, raw_right_cm = self.wall_sensors.read_left_right_cm()

                    left_filtered = self.smooth_value(left_filtered, raw_left_cm)
                    right_filtered = self.smooth_value(right_filtered, raw_right_cm)

                    (
                        wall_correction,
                        tof_mode,
                        last_wall_error,
                        left_baseline_cm,
                        right_baseline_cm,
                    ) = self.compute_tof_wall_correction(
                        left_cm=left_filtered,
                        right_cm=right_filtered,
                        left_baseline_cm=left_baseline_cm,
                        right_baseline_cm=right_baseline_cm,
                        last_wall_correction=last_wall_correction,
                    )

                    last_wall_correction = wall_correction

                total_correction = imu_correction + wall_correction
                total_correction = clamp(
                    total_correction,
                    -self.config.forward_heading_limit,
                    self.config.forward_heading_limit,
                )

                servo_value = self.config.servo_center_value + total_correction
                servo_value = clamp(servo_value, -1.0, 1.0)

                self.set_servo(servo_value)

                print(
                    f"FORWARD "
                    f"angle={angle:7.2f}deg "
                    f"imu={imu_correction:7.3f} "
                    f"L={left_filtered if left_filtered is not None else -1:6.1f}cm "
                    f"R={right_filtered if right_filtered is not None else -1:6.1f}cm "
                    f"mode={tof_mode:15s} "
                    f"wall={last_wall_error if last_wall_error is not None else 0:7.1f} "
                    f"wc={wall_correction:7.3f} "
                    f"servo={servo_value:7.3f}",
                    end="\r",
                )

                if elapsed >= forward_seconds:
                    break

                time.sleep(self.config.forward_loop_sleep)

        finally:
            self.stop()
            time.sleep(self.config.stop_delay_seconds)

            self.set_servo(self.config.servo_center_value)
            time.sleep(self.config.servo_settle_seconds)

            print()
            print(
                f"FORWARD final: "
                f"heading_error={angle:.2f} deg, "
                f"left={left_filtered}, "
                f"right={right_filtered}, "
                f"tof_mode={tof_mode}, "
                f"wall_error={last_wall_error}, "
                f"wall_correction={last_wall_correction:.3f}"
            )

    def start_left_turn_motors(self) -> None:
        if self.config.turn_mode == "STEER_AND_ONE_SIDE":
            self.set_motors(0.0, 1.0)

        elif self.config.turn_mode == "STEER_AND_BOTH_FORWARD":
            self.set_motors(1.0, 1.0)

        elif self.config.turn_mode == "STEER_AND_DIFF":
            self.set_motors(-1.0, 1.0)

        else:
            raise ValueError(f"Unknown turn_mode: {self.config.turn_mode}")

    def start_right_turn_motors(self) -> None:
        if self.config.turn_mode == "STEER_AND_ONE_SIDE":
            self.set_motors(1.0, 0.0)

        elif self.config.turn_mode == "STEER_AND_BOTH_FORWARD":
            self.set_motors(1.0, 1.0)

        elif self.config.turn_mode == "STEER_AND_DIFF":
            self.set_motors(1.0, -1.0)

        else:
            raise ValueError(f"Unknown turn_mode: {self.config.turn_mode}")

    def forward_one_cell(self) -> None:
        self.forward_cells(1)

    def get_left_turn_servo_value(self) -> float:
        if self.config.turn_servo_mode == "CENTER":
            return self.config.servo_center_value

        return self.config.servo_left_value

    def get_right_turn_servo_value(self) -> float:
        if self.config.turn_servo_mode == "CENTER":
            return self.config.servo_center_value

        return self.config.servo_right_value

    def timed_turn_left_90(self) -> None:
        self.require_devices()

        print(f"LEFT timed turn: {self.config.left_90_seconds:.2f}s")

        self.stop()
        time.sleep(self.config.stop_delay_seconds)

        self.set_servo(self.get_left_turn_servo_value())
        time.sleep(self.config.servo_settle_seconds)

        self.start_left_turn_motors()
        time.sleep(self.config.left_90_seconds)

        self.stop()
        time.sleep(self.config.stop_delay_seconds)

        self.set_servo(self.config.servo_center_value)
        time.sleep(self.config.servo_settle_seconds)

    def timed_turn_right_90(self) -> None:
        self.require_devices()

        print(f"RIGHT timed turn: {self.config.right_90_seconds:.2f}s")

        self.stop()
        time.sleep(self.config.stop_delay_seconds)

        self.set_servo(self.get_right_turn_servo_value())
        time.sleep(self.config.servo_settle_seconds)

        self.start_right_turn_motors()
        time.sleep(self.config.right_90_seconds)

        self.stop()
        time.sleep(self.config.stop_delay_seconds)

        self.set_servo(self.config.servo_center_value)
        time.sleep(self.config.servo_settle_seconds)

    def imu_turn_left_90(self) -> None:
        self.require_devices()

        if self.gyro is None:
            self.timed_turn_left_90()
            return

        target = abs(self.config.imu_left_target_degrees)
        print(f"LEFT IMU turn target: +{target:.1f} deg")

        self.stop()
        time.sleep(self.config.stop_delay_seconds)

        self.set_servo(self.get_left_turn_servo_value())
        time.sleep(self.config.servo_settle_seconds)

        angle = 0.0
        last_time = time.monotonic()
        start_time = last_time

        self.start_left_turn_motors()

        try:
            while True:
                now = time.monotonic()
                dt = now - last_time
                last_time = now

                corrected_z = self.gyro.read_corrected_z(deadband=self.config.gyro_deadband)
                angle += corrected_z * dt

                print(
                    f"LEFT z={corrected_z:8.2f} deg/s  "
                    f"angle={angle:8.2f} deg",
                    end="\r",
                )

                if angle >= target:
                    print()
                    print(f"LEFT target reached. angle={angle:.2f} deg")
                    break

                if now - start_time > self.config.imu_max_turn_seconds:
                    print()
                    print(f"LEFT TIMEOUT. angle={angle:.2f} deg")
                    break

                time.sleep(0.01)

        finally:
            self.stop()
            time.sleep(self.config.stop_delay_seconds)

            self.set_servo(self.config.servo_center_value)
            time.sleep(self.config.servo_settle_seconds)

    def imu_turn_right_90(self) -> None:
        self.require_devices()

        if self.gyro is None:
            self.timed_turn_right_90()
            return

        target = -abs(self.config.imu_right_target_degrees)
        print(f"RIGHT IMU turn target: {target:.1f} deg")

        self.stop()
        time.sleep(self.config.stop_delay_seconds)

        self.set_servo(self.get_right_turn_servo_value())
        time.sleep(self.config.servo_settle_seconds)

        angle = 0.0
        last_time = time.monotonic()
        start_time = last_time

        self.start_right_turn_motors()

        try:
            while True:
                now = time.monotonic()
                dt = now - last_time
                last_time = now

                corrected_z = self.gyro.read_corrected_z(deadband=self.config.gyro_deadband)
                angle += corrected_z * dt

                print(
                    f"RIGHT z={corrected_z:8.2f} deg/s  "
                    f"angle={angle:8.2f} deg",
                    end="\r",
                )

                if angle <= target:
                    print()
                    print(f"RIGHT target reached. angle={angle:.2f} deg")
                    break

                if now - start_time > self.config.imu_max_turn_seconds:
                    print()
                    print(f"RIGHT TIMEOUT. angle={angle:.2f} deg")
                    break

                time.sleep(0.01)

        finally:
            self.stop()
            time.sleep(self.config.stop_delay_seconds)

            self.set_servo(self.config.servo_center_value)
            time.sleep(self.config.servo_settle_seconds)

    def turn_left_90(self) -> None:
        if self.config.use_imu_turn:
            self.imu_turn_left_90()
        else:
            self.timed_turn_left_90()

    def turn_right_90(self) -> None:
        if self.config.use_imu_turn:
            self.imu_turn_right_90()
        else:
            self.timed_turn_right_90()

    def execute_type(self, command_type: str) -> None:
        command_type = command_type.upper()

        if command_type == "FORWARD":
            self.forward_one_cell()

        elif command_type == "LEFT":
            self.turn_left_90()

        elif command_type == "RIGHT":
            self.turn_right_90()

        elif command_type == "STOP":
            print("STOP")
            self.stop()
            time.sleep(self.config.stop_delay_seconds)

        else:
            raise ValueError(f"Unknown command type: {command_type}")

    def execute_command(self, command: dict) -> None:
        command_type = command.get("type")

        if not isinstance(command_type, str):
            raise ValueError(f"Command must have string type: {command}")

        self.execute_type(command_type)
