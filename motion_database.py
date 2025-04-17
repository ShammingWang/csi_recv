import json
import sqlite3
import numpy as np
import pandas as pd
import os
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score
from datetime import datetime, timedelta, timezone
# 配置参数
DB_PATH = "csi_data.db"
WINDOW_SIZE = 5
NUM_SUBCARRIERS = 117

# 解析 CSI IQ 字符串为振幅数组
def parse_csi_json(csi_json_str):
    try:
        iq_list = json.loads(csi_json_str)
        iq_array = np.array(iq_list).reshape(-1, 2)
        amplitude = np.sqrt(np.sum(iq_array**2, axis=1))
        return amplitude[:NUM_SUBCARRIERS]
    except Exception as e:
        return None

# 从 DataFrame 提取特征
def extract_features_from_dataframe_train(df):
    features = []
    df['amplitude'] = df['data'].apply(parse_csi_json)
    amplitudes = df['amplitude'].dropna().to_list()

    if len(amplitudes) < WINDOW_SIZE:
        return []

    for i in range(len(amplitudes) - WINDOW_SIZE + 1):
        window = np.array(amplitudes[i:i+WINDOW_SIZE])
        mean_std = np.mean(np.std(window, axis=0))
        max_std = np.max(np.std(window, axis=0))
        features.append([mean_std, max_std])
    return features

def extract_features_from_dataframe_test(df):
    features = []
    df['amplitude'] = df['csi_json'].apply(parse_csi_json)
    amplitudes = df['amplitude'].dropna().to_list()

    if len(amplitudes) < WINDOW_SIZE:
        return []

    for i in range(len(amplitudes) - WINDOW_SIZE + 1):
        window = np.array(amplitudes[i:i+WINDOW_SIZE])
        mean_std = np.mean(np.std(window, axis=0))
        max_std = np.max(np.std(window, axis=0))
        features.append([mean_std, max_std])
    return features
# 从 SQLite 数据库加载数据

# def load_from_database(limit=500):
#     conn = sqlite3.connect(DB_PATH)
#     query = f"""
#     SELECT csi_json FROM csi_frame 
#     ORDER BY datetime(received_at_utc) DESC 
#     LIMIT {limit}
#     """
#     df = pd.read_sql_query(query, conn)
#     conn.close()
#     return df


def load_from_database(seconds=30):
    conn = sqlite3.connect(DB_PATH)
    now = datetime.now()
    recent_time = now - timedelta(seconds=seconds)
    dt_format = "%Y-%m-%d %H:%M:%S"
    recent_time_str = recent_time.strftime(dt_format)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    query = f"""
    SELECT csi_json FROM csi_frame 
    WHERE received_at_utc >= ?
    ORDER BY received_at_utc ASC
    """
    cursor.execute(query, (recent_time_str,))
    rows = cursor.fetchall()
    df = pd.DataFrame(rows, columns=["csi_json"])
    # df = pd.read_sql_query(query, conn)
    conn.close()
    return df

# 从 CSV 文件夹加载数据并打标签
def load_dataset_from_folder(folder_path, label):
    X, y = [], []
    for fname in os.listdir(folder_path):
        if not fname.endswith(".csv"):
            continue
        fpath = os.path.join(folder_path, fname)
        try:
            df = pd.read_csv(fpath)
            feats = extract_features_from_dataframe_train(df)
            X.extend(feats)
            y.extend([label] * len(feats))
        except Exception as e:
            print(f"Failed on {fname}: {e}")
    return X, y

# 使用模型预测数据库中数据
def predict_from_database(clf):
    # df = load_from_database(limit=200)
    df = load_from_database(seconds=5)
    feats = extract_features_from_dataframe_test(df)
    if not feats:
        print("没有有效的 CSI 数据可用于预测")
        return

    preds = clf.predict(feats)
    majority_vote = int(np.round(np.mean(preds)))
    print(f"\nPrediction：{'motion (true)' if majority_vote == 1 else 'static (false)'}")
    #print(f"[细节] 每帧预测：{preds.tolist()}")

# 训练模型
def train_model():
    X_motion, y_motion = load_dataset_from_folder("evaluation_motion", label=1)
    X_static, y_static = load_dataset_from_folder("evaluation_static", label=0)
    X = X_motion + X_static
    y = y_motion + y_static

    if len(X) == 0:
        print("无有效训练数据")
        return None

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    clf = RandomForestClassifier(n_estimators=100, random_state=42)
    clf.fit(X_train, y_train)

    acc = accuracy_score(y_test, clf.predict(X_test))
    return clf

def motion_detection():
    # 训练模型
    clf = train_model()
    if clf:
        predict_from_database(clf)

import time

if __name__ == "__main__":
    clf = train_model()
    if clf:
        while True:
            # 每 10 秒预测一次
            predict_from_database(clf)
            time.sleep(5)
