import csv
import sqlite3
import json
import numpy as np
import time
from datetime import datetime, timedelta, timezone
from scipy.signal import savgol_filter
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation

socketio = None

def set_socketio(socketio_instance):
    global socketio
    socketio = socketio_instance

def update_websocket(time_str, median_bpm, avg_bpm_int):
    # 如果 socketio 已初始化，则推送当前窗口数据
    global socketio
    if socketio:
        socketio.emit('bpm_update', {
            'time': time_str,
            'bpm': median_bpm,
            'bpm_int': avg_bpm_int
        })

def animate_bpm(dict_cal_plot, dt_format="%Y-%m-%d %H:%M:%S"):
    # 对时间键按照时间顺序排序，并转换为 datetime 对象
    sorted_times = sorted(dict_cal_plot.keys(), key=lambda t: datetime.strptime(t, dt_format))
    times_dt = [datetime.strptime(t, dt_format) for t in sorted_times]
    bpm_values = [dict_cal_plot[t] for t in sorted_times]

    fig, ax = plt.subplots(figsize=(10, 6))
    line, = ax.plot_date([], [], linestyle='-', marker='o', color='b')
    ax.set_xlabel("Time")
    ax.set_ylabel("BPM")
    ax.set_title("Dynamic Breathing Rate Over Time")
    ax.grid(True)
    
    # 初始化函数：设置坐标范围和空数据
    def init():
        ax.set_xlim(times_dt[0], times_dt[-1])
        # y 轴范围设置为数据范围的适当扩展
        y_min = min(bpm_values) - 5 if bpm_values else 0
        y_max = max(bpm_values) + 5 if bpm_values else 40
        ax.set_ylim(y_min, y_max)
        line.set_data([], [])
        return line,
    
    # 更新函数：每次显示前 frame+1 个数据点
    def update(frame):
        current_times = times_dt[:frame+1]
        current_bpm = bpm_values[:frame+1]
        line.set_data(current_times, current_bpm)
        return line,
    
    # 创建动画对象，interval 指定更新间隔（毫秒），frames 为数据点个数
    anim = FuncAnimation(fig, update, frames=len(times_dt), init_func=init, interval=500, blit=True, repeat=False)
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.show()

def parse_csi_file(filepath):
    """
    parse csi file
    """
    csi_signals = []
    timestamps = []
    time_format_in = "%Y-%m-%d %H:%M:%S.%f"
    time_format_out = "%Y-%m-%d %H:%M:%S"
    with open(filepath, 'r', encoding='utf-8') as f:
        reader = csv.reader(f, delimiter=',', quotechar='"')
        for row in reader:
            if not row or not row[0].startswith("CSI_DATA"):
                continue
            csi_data_str = row[-2].strip('[]')
            time_str = row[-1].strip()
            csi_array = [int(x) for x in csi_data_str.split(',')]
            if len(csi_array) != 234:
                continue
            csi_signals.append(np.array(csi_array))
            try:
                dt = datetime.strptime(time_str[:26], time_format_in)
            except ValueError:
                dt = datetime.strptime(time_str, time_format_out)
            timestamps.append(dt.strftime(time_format_out))
    return csi_signals, timestamps

def parse_csi_file_v2(db_path="csi_data.db"):
    """
      从 SQLite 数据库中读取 CSI 数据，返回与 parse_csi_file 相同的格式：
      csi_signals: list of numpy.array，每个数组包含 114 个整数
      timestamps: list of str，每个时间戳格式为 "%Y-%m-%d %H:%M:%S"
    """

    csi_signals = []
    timestamps = []

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    # 按 id 升序读取所有 CSI 帧数据
    query = "SELECT received_at_utc, csi_json FROM csi_frame ORDER BY id ASC"
    cursor.execute(query)
    rows = cursor.fetchall()
    for row in rows:
        time_str, csi_json_str = row[0], row[1]
        try:
            csi_list = json.loads(csi_json_str)
        except Exception as e:
            print("JSON decode error:", e)
            continue
        if len(csi_list) != 114:
            continue
        csi_signals.append(np.array(csi_list))
        try:
            dt = datetime.strptime(time_str, "%Y-%m-%dT%H:%M:%S.%f%z")
            # 将时间转换为本地时间字符串（例如 UTC+0 转为 "%Y-%m-%d %H:%M:%S"）
            time_str = dt.astimezone().strftime("%Y-%m-%d %H:%M:%S")
        except Exception as e:
            pass
        timestamps.append(time_str)
    conn.close()
    return csi_signals, timestamps

def csi_to_complex(csi_signals):
    """
    put CSI signals into complex numbers
    """
    complex_signals = []
    for a in csi_signals:
        if len(a) != 234:
            continue
        real = a[0::2]
        imag = a[1::2]
        complex_signals.append(real + 1j * np.array(imag))
    return complex_signals

def csi_to_complex_v2(csi_signals):
    """
    put CSI signals into complex numbers
    """
    complex_signals = []
    for a in csi_signals:
        if len(a) != 114:
            continue
        real = a[0::2]
        imag = a[1::2]
        complex_signals.append(real + 1j * np.array(imag))
    return complex_signals

def pre_process_signal(signal, fs):
    """
    去直流、使用中值滤波平滑信号（代替带通滤波）。
    """
    # Savitzky-Golay filter
    window_length = int(1 * fs)  
    if window_length < 3:
        window_length = 3
    if window_length % 2 == 0:
        window_length += 1
    smooth_signal = savgol_filter(signal, window_length, polyorder=2)
    return smooth_signal

def estimate_bpm_acf(signal, fs, min_period_sec=1.2):
    """
    use ACF to estimate breathing rate
    """
    if len(signal) < 2:
        return 0.0
    signal = signal - np.mean(signal)
    acf_full = np.correlate(signal, signal, mode='full')
    acf = acf_full[len(acf_full)//2:]
    min_idx = int(min_period_sec * fs)
    if min_idx >= len(acf):
        return 0.0
    peak_local = np.argmax(acf[min_idx:])
    peak_index = min_idx + peak_local
    period_sec = peak_index / fs
    if period_sec <= 0:
        return 0.0
    bpm = 60.0 / period_sec
    return bpm

def process_breathing_rate_sliding_window(complex_signals, timestamps, window_length_sec=15, step_sec=1):
    """
    use sliding window to process breathing rate
    """
    dt_format = "%Y-%m-%d %H:%M:%S"
    dt_list = [datetime.strptime(t, dt_format) for t in timestamps]
    results = []
    csi_data = list(zip(dt_list, complex_signals))
    current_time = dt_list[0]
    end_time = dt_list[-1]
    window_len = timedelta(seconds=window_length_sec)
    step = timedelta(seconds=step_sec)
    dict_cal_int = {}   # formatting MAE
    dict_cal_plot = {}  # formatting plot
    
    while current_time + window_len <= end_time:
        window_start = current_time
        window_end = current_time + window_len
        window_signals = [sig for (ts, sig) in csi_data if window_start <= ts < window_end]
        if not window_signals:
            current_time += step
            continue
        
        # fs
        fs = len(window_signals) / (window_end - window_start).total_seconds()
        n_subcarriers = window_signals[0].shape[0]
        bpm_list = []
        # for each subcarrier
        for sub_idx in range(n_subcarriers):
            subcarrier_series = np.array([np.abs(s[sub_idx]) for s in window_signals])
            if len(subcarrier_series) < 2:
                continue
            proc = pre_process_signal(subcarrier_series, fs)
            bpm = estimate_bpm_acf(proc, fs)
            if 8 <= bpm <= 30:
                bpm_list.append(bpm)
        if bpm_list:
            # reserve the median
            median_bpm = np.median(bpm_list)
            # round()
            avg_bpm_int = round(median_bpm)
        else:
            median_bpm = 0.0
            avg_bpm_int = 0
        
        results.append((window_start.strftime(dt_format), window_end.strftime(dt_format), avg_bpm_int))
        print(f"{window_end}, fs = {fs:.2f}, BPM = {avg_bpm_int}")
        dict_cal_int[window_end.strftime(dt_format)] = avg_bpm_int
        dict_cal_plot[window_end.strftime(dt_format)] = median_bpm
        current_time += step
    return results, dict_cal_int, dict_cal_plot


def calculate_bpm_once(db_path="csi_data.db", window_length_sec=15):
    """
    从数据库中提取最近 window_length_sec 秒的数据，返回当前时间、采样率、BPM。
    """
    dt_format = "%Y-%m-%d %H:%M:%S"
    now = datetime.now()
    window_start = now - timedelta(seconds=window_length_sec)
    window_start_str = window_start.strftime(dt_format)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    query = ("SELECT received_at_utc, csi_json FROM csi_frame "
             "WHERE received_at_utc >= ? ORDER BY received_at_utc ASC")
    cursor.execute(query, (window_start_str,))
    rows = cursor.fetchall()
    conn.close()

    csi_signals = []
    timestamps = []

    for row in rows:
        ts = row[0]
        csi_json_str = row[1]
        try:
            csi_list = json.loads(csi_json_str)
        except Exception as e:
            print("JSON decode error:", e)
            continue
        if len(csi_list) != 114:
            continue
        csi_signals.append(np.array(csi_list))
        timestamps.append(ts)

    if not csi_signals:
        return now, 0.0, 0

    # 转复数
    complex_signals = csi_to_complex_v2(csi_signals)
    dt_list = []
    for t in timestamps:
        try:
            if "T" in t:
                t_clean = t.split('.')[0].replace("T", " ")
                dt_elem = datetime.strptime(t_clean, "%Y-%m-%d %H:%M:%S")
            else:
                dt_elem = datetime.strptime(t, "%Y-%m-%d %H:%M:%S")
        except Exception as e:
            print("Error parsing time", t, e)
            continue
        dt_list.append(dt_elem)

    duration = (dt_list[-1] - dt_list[0]).total_seconds()
    if duration <= 0:
        duration = 1.0
    fs = len(dt_list) / duration

    n_subcarriers = complex_signals[0].shape[0]
    bpm_list = []
    for sub_idx in range(n_subcarriers):
        subcarrier_series = np.array([np.abs(s[sub_idx]) for s in complex_signals])
        if len(subcarrier_series) < 2:
            continue
        proc = pre_process_signal(subcarrier_series, fs)
        bpm = estimate_bpm_acf(proc, fs)
        if 8 <= bpm <= 30:
            bpm_list.append(bpm)

    if bpm_list:
        median_bpm = np.median(bpm_list)
        avg_bpm_int = round(median_bpm)
    else:
        median_bpm = 0.0
        avg_bpm_int = 0

    return now, fs, avg_bpm_int


def process_breathing_rate_from_db(db_path="csi_data.db", window_length_sec=15, update_interval=1):
    """
    每隔 update_interval 秒循环调用一次 BPM 计算函数。
    """
    while True:
        now, fs, bpm = calculate_bpm_once(db_path=db_path, window_length_sec=window_length_sec)
        time_str = now.strftime("%Y-%m-%d %H:%M:%S")
        if bpm == 0:
            print(f"{time_str}: No valid CSI data in the last {window_length_sec}s.")
        else:
            print(f"{time_str}: fs = {fs:.2f} Hz, BPM = {bpm}")
        time.sleep(update_interval)


if __name__ == "__main__":
    filepath = "/Users/mac/Documents/code/aiot/comp7310_2025_group_project/benchmark/breathing_rate/test/CSI20250227_201424.csv"
    
    # csi_signals, timestamps = parse_csi_file(filepath)
    # complex_signals = csi_to_complex(csi_signals)
    # _, dict_cal_int, dict_cal_plot = process_breathing_rate_sliding_window(complex_signals, timestamps, window_length_sec=20, step_sec=1)

    # csi_signals, timestamps = parse_csi_file_v2("/Users/mac/Documents/code/aiot/csi_data.db")
    # complex_signals = csi_to_complex_v2(csi_signals)
    # _, dict_cal_int, dict_cal_plot = process_breathing_rate_sliding_window(complex_signals, timestamps, window_length_sec=20, step_sec=1)

    # mean_bpm = np.mean(list(dict_cal_int.values()))
    # print(f"Mean BPM: {mean_bpm:.2f}")
    
    process_breathing_rate_from_db(db_path="csi_data.db", window_length_sec=20, update_interval=1)

    # # read ground truth
    # df = pd.read_csv('/Users/mac/Documents/code/aiot/comp7310_2025_group_project/benchmark/breathing_rate/evaluation/gt_20250227_191018.csv')
    # result_dict = df.set_index('time')['bpm'].to_dict()
    # mae = 0.0
    # count = 0

    # # compute MAE
    # for time, bpm_cal in dict_cal_int.items():
    #     if time in result_dict:
    #         bpm_gt = result_dict[time]
    #         mae += abs(bpm_cal - bpm_gt)
    #         count += 1

    # if count > 0:
    #     mae /= count
    # else:
    #     mae = float('nan')
    # print(count)
    # print(f"MAE: {mae}")

    # draw plot
    # dt_format = "%Y-%m-%d %H:%M:%S"
    # sorted_times = sorted(dict_cal_plot.keys(), key=lambda t: datetime.strptime(t, dt_format))
    # sorted_bpm = [dict_cal_plot[t] for t in sorted_times]
    # times_dt = [datetime.strptime(t, dt_format) for t in sorted_times]

    # import matplotlib.pyplot as plt
    # plt.figure(figsize=(10, 6))
    # plt.plot(times_dt, sorted_bpm, marker='o', linestyle='-', color='b')
    # plt.xlabel("Time")
    # plt.ylabel("BPM")
    # plt.title("Breathing Rate Over Time")
    # plt.grid(True)
    # plt.xticks(rotation=45)
    # plt.tight_layout()
    # plt.show()

    # animate_bpm(dict_cal_plot)


