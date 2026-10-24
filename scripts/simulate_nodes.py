"""Giả lập 10 node publish MQTT để test gateway khi CHƯA có phần cứng.

Chạy song song với gateway:
    python scripts/simulate_nodes.py
Yêu cầu: Mosquitto đang chạy trên 127.0.0.1:1883.
"""
from __future__ import annotations

import json
import random
import sys
import time

import paho.mqtt.client as mqtt

BASE_TOPIC = "iot/nodes"

# Sinh dữ liệu ngẫu nhiên hợp lý cho từng loại node
GENERATORS = {
    "node-01": lambda: {"temperature": round(random.uniform(22, 32), 1), "humidity": round(random.uniform(40, 80), 1)},
    "node-02": lambda: {"temperature": round(random.uniform(20, 30), 1), "humidity": round(random.uniform(45, 85), 1)},
    "node-03": lambda: {"lux": round(random.uniform(0, 1000), 1)},
    "node-04": lambda: {"co2_ppm": round(random.uniform(400, 1200), 0), "voc": round(random.uniform(0, 500), 0)},
    "node-05": lambda: {"soil_moisture": round(random.uniform(10, 90), 1)},
    "node-06": lambda: {"motion": random.randint(0, 1), "door": random.randint(0, 1)},
    "node-07": lambda: {"voltage": round(random.uniform(210, 240), 1), "current": round(random.uniform(0, 10), 2),
                         "power": round(random.uniform(0, 2000), 1), "energy": round(random.uniform(0, 500), 2)},
    "node-08": lambda: {"level_cm": round(random.uniform(0, 400), 1)},
    "node-09": lambda: {"temperature": round(random.uniform(-10, 60), 1)},
    "node-10": lambda: {"pressure": round(random.uniform(990, 1025), 1), "temperature": round(random.uniform(18, 35), 1)},
}


def main() -> int:
    client = mqtt.Client(client_id="node-simulator")
    client.connect("127.0.0.1", 1883, 60)
    client.loop_start()
    print("Bat dau gia lap 10 node (Ctrl+C de dung)...")
    try:
        while True:
            for node_id, gen in GENERATORS.items():
                payload = json.dumps(gen())
                client.publish(f"{BASE_TOPIC}/{node_id}", payload, qos=1)
                print(f"  {node_id} -> {payload}")
            print("--- gui xong 1 vong, cho 5s ---")
            time.sleep(5)
    except KeyboardInterrupt:
        print("\nDung gia lap.")
    finally:
        client.loop_stop()
        client.disconnect()
    return 0


if __name__ == "__main__":
    sys.exit(main())
