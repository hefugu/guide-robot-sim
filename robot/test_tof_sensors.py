from __future__ import annotations

import time

import board
import busio
import adafruit_tca9548a
import adafruit_vl53l1x


def make_sensor(tca: adafruit_tca9548a.TCA9548A, channel: int) -> adafruit_vl53l1x.VL53L1X:
    sensor = adafruit_vl53l1x.VL53L1X(tca[channel])

    # 1 = short, 2 = long
    sensor.distance_mode = 2

    # ms
    sensor.timing_budget = 100

    sensor.start_ranging()
    return sensor


def read_cm(sensor: adafruit_vl53l1x.VL53L1X) -> float | None:
    if not sensor.data_ready:
        return None

    distance = sensor.distance
    sensor.clear_interrupt()

    if distance is None:
        return None

    return float(distance)


def main() -> None:
    print("Starting I2C...")
    i2c = busio.I2C(board.SCL, board.SDA)

    print("Starting TCA9548A...")
    tca = adafruit_tca9548a.TCA9548A(i2c)

    print("Starting left VL53L1X on CH0...")
    left_sensor = make_sensor(tca, 0)

    print("Starting right VL53L1X on CH1...")
    right_sensor = make_sensor(tca, 1)

    print("VL53L1X sensors started.")
    print("Move your hand near each sensor.")
    print("Ctrl+C to stop.")

    try:
        while True:
            left_cm = read_cm(left_sensor)
            right_cm = read_cm(right_sensor)

            if left_cm is not None and right_cm is not None:
                error = left_cm - right_cm
                print(
                    f"LEFT={left_cm:7.1f} cm  "
                    f"RIGHT={right_cm:7.1f} cm  "
                    f"ERROR={error:7.1f} cm"
                )
            else:
                print(f"LEFT={left_cm}  RIGHT={right_cm}")

            time.sleep(0.10)

    except KeyboardInterrupt:
        print("Stopping...")

    finally:
        left_sensor.stop_ranging()
        right_sensor.stop_ranging()
        print("Done.")


if __name__ == "__main__":
    main()
