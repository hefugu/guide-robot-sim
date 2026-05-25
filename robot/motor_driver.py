from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Literal


TurnMode = Literal[
    "STEER_AND_ONE_SIDE",
    "STEER_AND_BOTH_FORWARD",
    "STEER_AND_DIFF",
]


@dataclass(frozen=True)
class RobotPins:
    # BCM GPIO numbering
    en_l: int = 12
    in1_l: int = 5
    in2_l: int = 6

    en_r: int = 13
    in1_r: int = 23
    in2_r: int = 24

    servo: int = 18


@dataclass
class RobotConfig:
    # 1マス = 50cm 前提。必ず実測で調整する。
    forward_one_cell_seconds: float = 0.80

    # その場90度旋回。左右差が出るなら別々に調整する。
    left_90_seconds: float = 0.55
    right_90_seconds: float = 0.55

    # PWM出力。0.0〜1.0。
    # 最初は低速。いきなり0.8以上にしない。
    motor_speed: float = 0.40
    turn_speed: float = 0.38

    # サーボパルス幅。実機に合わせて調整。
    servo_center_us: int = 1500
    servo_left_us: int = 1100
    servo_right_us: int = 1900

    # サーボが角度に到達するまでの待ち時間。
    servo_settle_seconds: float = 0.18

    # STOP後の安全待機。
    stop_delay_seconds: float = 0.15

    # 旋回方式。
    # 君の説明だと、サーボを切って片側モーターを回すのが近い。
    turn_mode: TurnMode = "STEER_AND_ONE_SIDE"

    # pigpio PWM
    pwm_frequency_hz: int = 1000


class RobotDriver:
    def __init__(
        self,
        pins: RobotPins | None = None,
        config: RobotConfig | None = None,
        dry_run: bool = True,
    ) -> None:
        self.pins = pins or RobotPins()
        self.config = config or RobotConfig()
        self.dry_run = dry_run
        self.pi = None

    def __enter__(self) -> "RobotDriver":
        self.setup()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.cleanup()

    def setup(self) -> None:
        if self.dry_run:
            print("[DRY] setup robot driver")
            return

        try:
            import pigpio
        except ImportError as error:
            raise RuntimeError(
                "pigpio が見つかりません。Pi上で `sudo apt install pigpio python3-pigpio` "
                "または `sudo apt-get install pigpio` を入れてください。"
            ) from error

        self.pi = pigpio.pi()

        if not self.pi.connected:
            raise RuntimeError(
                "pigpio daemon に接続できません。"
                "`sudo systemctl enable pigpiod` と "
                "`sudo systemctl start pigpiod` を実行してください。"
            )

        output_pins = [
            self.pins.en_l,
            self.pins.in1_l,
            self.pins.in2_l,
            self.pins.en_r,
            self.pins.in1_r,
            self.pins.in2_r,
            self.pins.servo,
        ]

        for pin in output_pins:
            self.pi.set_mode(pin, pigpio.OUTPUT)

        for pin in [self.pins.en_l, self.pins.en_r]:
            self.pi.set_PWM_frequency(pin, self.config.pwm_frequency_hz)
            self.pi.set_PWM_range(pin, 255)
            self.pi.set_PWM_dutycycle(pin, 0)

        self.servo_center()
        self.stop()

    def cleanup(self) -> None:
        try:
            self.stop()
            self.servo_center()
        finally:
            if self.dry_run:
                print("[DRY] cleanup robot driver")
            elif self.pi is not None:
                self.pi.set_servo_pulsewidth(self.pins.servo, 0)
                self.pi.stop()
                self.pi = None

    def _write(self, pin: int, value: int) -> None:
        if self.dry_run:
            print(f"[DRY] GPIO {pin} = {value}")
            return

        assert self.pi is not None
        self.pi.write(pin, value)

    def _pwm(self, pin: int, duty: int) -> None:
        duty = max(0, min(255, int(duty)))

        if self.dry_run:
            print(f"[DRY] PWM GPIO {pin} = {duty}/255")
            return

        assert self.pi is not None
        self.pi.set_PWM_dutycycle(pin, duty)

    def _servo(self, pulse_us: int) -> None:
        if self.dry_run:
            print(f"[DRY] SERVO GPIO {self.pins.servo} = {pulse_us}us")
            return

        assert self.pi is not None
        self.pi.set_servo_pulsewidth(self.pins.servo, pulse_us)

    def _sleep(self, seconds: float) -> None:
        seconds = max(0.0, float(seconds))
        time.sleep(seconds)

    def _clamp_speed(self, speed: float) -> float:
        return max(-1.0, min(1.0, float(speed)))

    def _set_motor_raw(
        self,
        en_pin: int,
        in1_pin: int,
        in2_pin: int,
        speed: float,
    ) -> None:
        speed = self._clamp_speed(speed)
        duty = int(abs(speed) * 255)

        if speed > 0:
            self._write(in1_pin, 1)
            self._write(in2_pin, 0)
        elif speed < 0:
            self._write(in1_pin, 0)
            self._write(in2_pin, 1)
        else:
            self._write(in1_pin, 0)
            self._write(in2_pin, 0)

        self._pwm(en_pin, duty)

    def set_motors(self, left_speed: float, right_speed: float) -> None:
        self._set_motor_raw(
            self.pins.en_l,
            self.pins.in1_l,
            self.pins.in2_l,
            left_speed,
        )
        self._set_motor_raw(
            self.pins.en_r,
            self.pins.in1_r,
            self.pins.in2_r,
            right_speed,
        )

    def stop(self) -> None:
        print("ACTION: STOP motors")
        self.set_motors(0.0, 0.0)
        self._sleep(self.config.stop_delay_seconds)

    def servo_center(self) -> None:
        print("ACTION: servo CENTER")
        self._servo(self.config.servo_center_us)
        self._sleep(self.config.servo_settle_seconds)

    def servo_left(self) -> None:
        print("ACTION: servo LEFT")
        self._servo(self.config.servo_left_us)
        self._sleep(self.config.servo_settle_seconds)

    def servo_right(self) -> None:
        print("ACTION: servo RIGHT")
        self._servo(self.config.servo_right_us)
        self._sleep(self.config.servo_settle_seconds)

    def forward_one_cell(self) -> None:
        print("ACTION: FORWARD one cell")
        self.servo_center()
        self.set_motors(
            self.config.motor_speed,
            self.config.motor_speed,
        )
        self._sleep(self.config.forward_one_cell_seconds)
        self.stop()

    def turn_left_90(self) -> None:
        print("ACTION: LEFT 90")
        self.stop()
        self.servo_left()

        if self.config.turn_mode == "STEER_AND_ONE_SIDE":
            # 左へ切って右モーター中心で回す。実機で逆なら左右を入れ替える。
            self.set_motors(0.0, self.config.turn_speed)

        elif self.config.turn_mode == "STEER_AND_BOTH_FORWARD":
            self.set_motors(self.config.turn_speed, self.config.turn_speed)

        elif self.config.turn_mode == "STEER_AND_DIFF":
            self.set_motors(-self.config.turn_speed, self.config.turn_speed)

        else:
            raise ValueError(f"Unknown turn_mode: {self.config.turn_mode}")

        self._sleep(self.config.left_90_seconds)
        self.stop()
        self.servo_center()

    def turn_right_90(self) -> None:
        print("ACTION: RIGHT 90")
        self.stop()
        self.servo_right()

        if self.config.turn_mode == "STEER_AND_ONE_SIDE":
            # 右へ切って左モーター中心で回す。実機で逆なら左右を入れ替える。
            self.set_motors(self.config.turn_speed, 0.0)

        elif self.config.turn_mode == "STEER_AND_BOTH_FORWARD":
            self.set_motors(self.config.turn_speed, self.config.turn_speed)

        elif self.config.turn_mode == "STEER_AND_DIFF":
            self.set_motors(self.config.turn_speed, -self.config.turn_speed)

        else:
            raise ValueError(f"Unknown turn_mode: {self.config.turn_mode}")

        self._sleep(self.config.right_90_seconds)
        self.stop()
        self.servo_center()

    def execute_type(self, command_type: str) -> None:
        if command_type == "FORWARD":
            self.forward_one_cell()
            return

        if command_type == "LEFT":
            self.turn_left_90()
            return

        if command_type == "RIGHT":
            self.turn_right_90()
            return

        if command_type == "STOP":
            self.stop()
            self.servo_center()
            return

        raise ValueError(f"Unknown command type: {command_type}")