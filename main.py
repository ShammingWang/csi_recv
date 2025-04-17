from fastapi import FastAPI
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import json
import sqlite3
from datetime import datetime, timedelta
import threading
import paho.mqtt.client as mqtt
import uvicorn
from zoneinfo import ZoneInfo
import logging
import os, time
from utils.bpm import calculate_bpm_once
from utils.motion_detection import motion_detection

# ---------- 日志配置 ----------
LOG_FILE = "mqtt_csi.log"
os.makedirs("logs", exist_ok=True)  # 可选：将日志文件放入 logs 文件夹
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(f"logs/{LOG_FILE}", encoding="utf-8"),
        # logging.StreamHandler()  # 如果你希望同时输出到终端，可以保留这一行
    ]
)

bpm_ready = False # 用于指示 BPM 接口是否准备就绪


# ---------- 1. 初始化数据库 ----------
DB_PATH = "csi_data.db"
SQL_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS csi_frame (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    received_at_utc   TEXT    NOT NULL,
    mac               TEXT    NOT NULL,
    rssi              INTEGER NOT NULL,
    rate              INTEGER NOT NULL,
    noise_floor       INTEGER NOT NULL,
    fft_gain          INTEGER NOT NULL,
    agc_gain          INTEGER NOT NULL,
    channel           INTEGER NOT NULL,
    csi_timestamp     INTEGER NOT NULL,
    sig_len           INTEGER NOT NULL,
    rx_state          INTEGER NOT NULL,
    first_word_invalid INTEGER NOT NULL,
    csi_json          TEXT    NOT NULL
);
"""
db = sqlite3.connect(DB_PATH, check_same_thread=False)
db.execute(SQL_CREATE_TABLE)
db.commit()

# ---------- 2. MQTT 逻辑 ----------
def on_connect(client, _userdata, _flags, rc):
    print(f"[MQTT] Connected, rc={rc}")
    client.subscribe("/esp32/#")
    print("[MQTT] Subscribed to /esp32/#")

def on_message(_client, _userdata, msg):
    try:
        payload_str = msg.payload.decode(errors="replace")
        payload = json.loads(payload_str)
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        print("[ERROR] Payload decode/parse failed:", e)
        return

    # now = datetime.utcnow() + timedelta(hours=8)  # UTC+8
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
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
        # print(f"[INFO] {now_iso} | Saved {len(rows)} frame(s) from {msg.topic}")
        logging.info(f"{now_iso} | Saved {len(rows)} frame(s) from {msg.topic}")

def start_mqtt_loop():
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect("192.168.137.60", 1883)
    print("[MQTT] Client created and connected")
    client.loop_forever()

# ---------- 3. FastAPI + Lifespan ----------
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("[FASTAPI] Starting MQTT thread with lifespan …")
    threading.Thread(target=start_mqtt_loop, daemon=True).start()
    # 启动一个线程，延迟 20 秒后设置 ready 状态
    def set_bpm_ready_after_delay():
        global bpm_ready
        time.sleep(20)
        bpm_ready = True
        logging.info("BPM interface is now ready.")
    
    threading.Thread(target=set_bpm_ready_after_delay, daemon=True).start()
    yield  # 等待 FastAPI 正常运行
    print("[FASTAPI] App shutting down …")  # 可选添加关闭处理

app = FastAPI(title="CSI MQTT Receiver", lifespan=lifespan)

@app.get("/status")
def get_status():
    return JSONResponse(content={"status": "running", "db": DB_PATH})


@app.get("/bpm")
def get_bpm():
    global bpm_ready
    if not bpm_ready:
        return JSONResponse(status_code=503, content={"message": "BPM not ready. Please wait 20 seconds after startup."})
    now, fs, bpm = calculate_bpm_once(db_path=DB_PATH, window_length_sec=20)
    if bpm == 0:
        return JSONResponse(status_code=204, content={"message": "Not enough CSI data."})
    return {
        "code": 200,
        "data": {
            "bpm": bpm,
            "timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
            "sampling_rate": round(fs, 2)
        }
    }


@app.get("/motion")
def get_motion():
    res = motion_detection()
    if res == None:
        return JSONResponse(status_code=204, content={"message": "Not enough CSI data."})
    return {
        "code": 200,
        "data": {
            "motion": res
        }
    }
if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)

