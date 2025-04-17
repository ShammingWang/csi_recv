from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware     # ★ 新增
from contextlib import asynccontextmanager
import json, sqlite3, threading, logging, os, time
from datetime import datetime
from zoneinfo import ZoneInfo
import paho.mqtt.client as mqtt
import uvicorn
from utils.bpm import calculate_bpm_once
from utils.motion_detection import motion_detection

# ---------- 日志配置 ----------
LOG_FILE = "mqtt_csi.log"
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(f"logs/{LOG_FILE}", encoding="utf-8")]
)

bpm_ready = False

# ---------- 1. 初始化数据库 ----------
DB_PATH = "csi_data.db"
SQL_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS csi_frame (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    received_at_utc TEXT NOT NULL,
    mac TEXT NOT NULL,
    rssi INTEGER NOT NULL,
    rate INTEGER NOT NULL,
    noise_floor INTEGER NOT NULL,
    fft_gain INTEGER NOT NULL,
    agc_gain INTEGER NOT NULL,
    channel INTEGER NOT NULL,
    csi_timestamp INTEGER NOT NULL,
    sig_len INTEGER NOT NULL,
    rx_state INTEGER NOT NULL,
    first_word_invalid INTEGER NOT NULL,
    csi_json TEXT NOT NULL
);
"""
db = sqlite3.connect(DB_PATH, check_same_thread=False)
db.execute(SQL_CREATE_TABLE)
db.commit()

# ---------- 2. MQTT 逻辑 ----------
def on_connect(client, _userdata, _flags, rc):
    print(f"[MQTT] Connected, rc={rc}")
    client.subscribe("/esp32/#")

def on_message(_client, _userdata, msg):
    try:
        payload = json.loads(msg.payload.decode(errors="replace"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return

    now_iso = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M:%S")
    rows = []
    for f in payload.get("frames", []):
        try:
            rows.append((
                now_iso, f["mac"], int(f["rssi"]), int(f["rate"]),
                int(f["noise_floor"]), int(f["fft_gain"]), int(f["agc_gain"]),
                int(f["channel"]), int(f["timestamp"]), int(f["sig_len"]),
                int(f["rx_state"]), int(f["first_word_invalid"]),
                json.dumps(f["csi"], separators=(",", ":"))
            ))
        except (KeyError, TypeError, ValueError):
            continue

    if rows:
        db.executemany(
            """INSERT INTO csi_frame
               (received_at_utc, mac, rssi, rate, noise_floor, fft_gain, agc_gain,
                channel, csi_timestamp, sig_len, rx_state, first_word_invalid, csi_json)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            rows
        )
        db.commit()

def start_mqtt_loop():
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect("192.168.137.60", 1883)
    client.loop_forever()

# ---------- 3. FastAPI + Lifespan ----------
@asynccontextmanager
async def lifespan(app: FastAPI):
    threading.Thread(target=start_mqtt_loop, daemon=True).start()

    def set_ready():
        global bpm_ready
        time.sleep(20)
        bpm_ready = True
        logging.info("BPM interface is now ready.")
    threading.Thread(target=set_ready, daemon=True).start()

    yield
    logging.info("FastAPI shutdown")

app = FastAPI(title="CSI MQTT Receiver", lifespan=lifespan)

# ★★★★★★★★★★★★★★★★★★★★★★★★
#            CORS
# ★★★★★★★★★★★★★★★★★★★★★★★★
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],            # 生产环境建议替换为具体域名列表
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- 4. API ----------
@app.get("/status")
def get_status():
    return {"status": "running", "db": DB_PATH}

@app.get("/bpm")
def get_bpm():
    if not bpm_ready:
        return JSONResponse(status_code=503, content={"message": "BPM not ready. Please wait 20 seconds after startup."})
    now, fs, bpm = calculate_bpm_once(db_path=DB_PATH, window_length_sec=20)
    if bpm == 0:
        return JSONResponse(status_code=204, content={"message": "Not enough CSI data."})
    return {"code": 200, "data": {"bpm": bpm, "timestamp": now.strftime('%Y-%m-%d %H:%M:%S'), "sampling_rate": round(fs, 2)}}

@app.get("/motion")
def get_motion():
    res = motion_detection()
    if res is None:
        return JSONResponse(status_code=204, content={"message": "Not enough CSI data."})
    return {"code": 200, "data": {"motion": res}}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)