from __future__ import annotations

import time
import smbus


MPU_ADDR = 0x68

PWR_MGMT_1 = 0x6B
GYRO_CONFIG = 0x1B
GYRO_ZOUT_H = 0x47


def read_word_2c(bus: smbus.SMBus, reg: int) -> int:
    high = bus.read_byte_data(MPU_ADDR, reg)
    low = bus.read_byte_data(MPU_ADDR, reg + 1)
    value = (high << 8) + low

    if value >= 0x8000:
        value = -((65535 - value) + 1)

    return value


def read_gyro_z(bus: smbus.SMBus) -> float:
    gyro_scale = 131.0  # ±250 deg/s
    return read_word_2c(bus, GYRO_ZOUT_H) / gyro_scale


def calibrate_gyro_z(bus: smbus.SMBus, seconds: float = 2.0) -> float:
    print("Calibrating gyro_z offset. Keep robot still...")

    values: list[float] = []
    start = time.monotonic()

    while time.monotonic() - start < seconds:
        values.append(read_gyro_z(bus))
        time.sleep(0.01)

    offset = sum(values) / len(values)
    print(f"gyro_z offset = {offset:.3f} deg/s")
    return offset


def main() -> None:
    bus = smbus.SMBus(1)

    # MPU6050起動
    bus.write_byte_data(MPU_ADDR, PWR_MGMT_1, 0)

    # ジャイロ範囲 ±250 deg/s
    bus.write_byte_data(MPU_ADDR, GYRO_CONFIG, 0x00)

    offset = calibrate_gyro_z(bus, seconds=2.0)

    angle = 0.0
    last_time = time.monotonic()

    print("Angle integration test")
    print("左回転でプラス、右回転でマイナスになるはず。")
    print("Ctrl+C で終了。")

    try:
        while True:
            now = time.monotonic()
            dt = now - last_time
            last_time = now

            gyro_z = read_gyro_z(bus)
            corrected_z = gyro_z - offset

            # 小さいノイズは無視
            if abs(corrected_z) < 0.8:
                corrected_z = 0.0

            angle += corrected_z * dt

            print(
                f"gyro_z={gyro_z:8.2f} deg/s  "
                f"corrected={corrected_z:8.2f} deg/s  "
                f"angle={angle:8.2f} deg"
            )

            time.sleep(0.02)

    except KeyboardInterrupt:
        print("Stopping...")


if __name__ == "__main__":
    main()
