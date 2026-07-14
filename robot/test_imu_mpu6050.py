from __future__ import annotations

import time
import smbus


MPU_ADDR = 0x68

PWR_MGMT_1 = 0x6B
GYRO_CONFIG = 0x1B

GYRO_XOUT_H = 0x43
GYRO_YOUT_H = 0x45
GYRO_ZOUT_H = 0x47


def read_word_2c(bus: smbus.SMBus, reg: int) -> int:
    high = bus.read_byte_data(MPU_ADDR, reg)
    low = bus.read_byte_data(MPU_ADDR, reg + 1)
    value = (high << 8) + low

    if value >= 0x8000:
        value = -((65535 - value) + 1)

    return value


def main() -> None:
    bus = smbus.SMBus(1)

    # MPU6050を起動
    bus.write_byte_data(MPU_ADDR, PWR_MGMT_1, 0)

    # ジャイロ範囲 ±250 deg/s
    bus.write_byte_data(MPU_ADDR, GYRO_CONFIG, 0x00)

    gyro_scale = 131.0

    print("MPU6050 gyro test")
    print("gyro_z を見る。車体を左右に回すと値が変わる。")
    print("Ctrl+C で終了。")

    try:
        while True:
            gyro_x = read_word_2c(bus, GYRO_XOUT_H) / gyro_scale
            gyro_y = read_word_2c(bus, GYRO_YOUT_H) / gyro_scale
            gyro_z = read_word_2c(bus, GYRO_ZOUT_H) / gyro_scale

            print(
                f"gyro_x={gyro_x:8.2f} deg/s  "
                f"gyro_y={gyro_y:8.2f} deg/s  "
                f"gyro_z={gyro_z:8.2f} deg/s"
            )

            time.sleep(0.1)

    except KeyboardInterrupt:
        print("Stopping...")


if __name__ == "__main__":
    main()
