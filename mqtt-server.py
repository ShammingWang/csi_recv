#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Subscribe to /esp32/#, parse CSI JSON payloads and save every frame
into a local SQLite database.  —  订阅 /esp32/#，解析 CSI JSON 负载，
并把每帧数据写入本地 SQLite 数据库。
"""

import json
import sqlite3
from datetime import datetime, timedelta   # timestamp in UTC
import paho.mqtt.client as mqtt


# ---------- 1. SQLite initialisation  数据库初始化 ----------
DB_PATH = "csi_data.db"

SQL_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS csi_frame (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    received_at_utc   TEXT    NOT NULL,            -- ISO 8601
    mac               TEXT    NOT NULL,
    rssi              INTEGER NOT NULL,
    rate              INTEGER NOT NULL,
    noise_floor       INTEGER NOT NULL,
    fft_gain          INTEGER NOT NULL,
    agc_gain          INTEGER NOT NULL,
    channel           INTEGER NOT NULL,
    csi_timestamp     INTEGER NOT NULL,            -- ESP32 side
    sig_len           INTEGER NOT NULL,
    rx_state          INTEGER NOT NULL,
    first_word_invalid INTEGER NOT NULL,
    csi_json          TEXT    NOT NULL             -- full array as JSON
);
"""

db = sqlite3.connect(DB_PATH, check_same_thread=False)  # OK inside MQTT callbacks
db.execute(SQL_CREATE_TABLE)
db.commit()

# ---------- 2. MQTT callbacks  MQTT 回调 ----------
def on_connect(client, _userdata, _flags, rc):
    print(f"[MQTT] Connected, rc={rc}")
    client.subscribe("/esp32/#")
    print("[MQTT] Subscribed to /esp32/#")

def on_message(_client, _userdata, msg):
    try:
        payload_str = msg.payload.decode(errors="replace")
        payload    = json.loads(payload_str)  # expect {"frames":[ ... ]}
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        print("[ERROR] Payload decode/parse failed:", e)
        return

    # 使用北京时间（UTC+8）
    now = datetime.utcnow() + timedelta(hours=8)
    now_iso = now.strftime("%Y-%m-%d %H:%M:%S")

    frames = payload.get("frames", [])
    if not isinstance(frames, list):
        print("[WARN] payload missing 'frames' list")
        return

    rows = []
    for f in frames:
        try:
            rows.append((
                now_iso,
                f["mac"],
                int(f["rssi"]),
                int(f["rate"]),
                int(f["noise_floor"]),
                int(f["fft_gain"]),
                int(f["agc_gain"]),
                int(f["channel"]),
                int(f["timestamp"]),
                int(f["sig_len"]),
                int(f["rx_state"]),
                int(f["first_word_invalid"]),
                json.dumps(f["csi"], separators=(",", ":"))
            ))
        except (KeyError, TypeError, ValueError) as e:
            print("[WARN] Skip bad frame:", e, "| frame:", f)
            continue

    if rows:
        db.executemany("""
            INSERT INTO csi_frame
            (received_at_utc, mac, rssi, rate, noise_floor, fft_gain, agc_gain,
             channel, csi_timestamp, sig_len, rx_state, first_word_invalid, csi_json)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, rows)
        db.commit()
        print(f"[INFO] {now_iso} | Saved {len(rows)} frame(s) from topic {msg.topic}")

# ---------- 3. MQTT client setup  启动 MQTT ----------

if __name__ == "__main__":

    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect("192.168.137.60", 1883)
    print("[MAIN] Waiting for packets …")

    client.loop_forever()

