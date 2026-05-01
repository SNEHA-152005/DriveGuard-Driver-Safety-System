"""
web/server.py — v3
===================
Flask server:
  - /           → Live dashboard (real-time SSE)
  - /history    → Session history + graphs
  - /api/state  → Current state JSON
  - /api/sessions → All sessions JSON
  - /api/graph/<session_id>/<metric> → PNG graph
  - /api/csv/<session_id>  → Raw CSV download

Server ab daemon=False option ke saath bhi chal sakta hai
taaki webcam band hone ke baad bhi alive rahe.
"""

import json
import os
import csv
import io
import glob
import threading
import logging
from datetime import datetime
from flask import (Flask, Response, render_template,
                   jsonify, send_from_directory, request)

logger = logging.getLogger(__name__)

app = Flask(__name__,
            template_folder="templates",
            static_folder="static")

# ── Shared live state ─────────────────────────────────────────────────────────
_state = {
    "ear": 0.0, "mar": 0.0,
    "pitch": 0.0, "yaw": 0.0, "roll": 0.0,
    "fatigue_score": 0.0, "fatigue_level": "LOW",
    "is_drowsy": False, "is_yawning": False,
    "is_distracted": False, "phone_detected": False,
    "blink_count": 0, "yawn_count": 0, "head_alerts": 0,
    "fps": 0.0, "face_detected": False,
    "alert_msg": "", "session_time": "00:00",
    "critical_elapsed": 0.0,
    "session_active": False,   # True = webcam chal raha hai
}
_state_lock = threading.Lock()


def update_state(**kwargs):
    with _state_lock:
        _state.update(kwargs)
        _state["session_active"] = True


def get_state() -> dict:
    with _state_lock:
        return dict(_state)


# ── SSE stream ────────────────────────────────────────────────────────────────
def _event_stream():
    import time
    while True:
        yield f"data: {json.dumps(get_state())}\n\n"
        time.sleep(0.1)


@app.route("/stream")
def stream():
    return Response(
        _event_stream(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache",
                 "X-Accel-Buffering": "no"},
    )


# ── Pages ─────────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("dashboard.html")


@app.route("/history")
def history():
    sessions = _get_sessions()
    return render_template("history.html", sessions=sessions)


# ── API ───────────────────────────────────────────────────────────────────────
@app.route("/api/state")
def api_state():
    return jsonify(get_state())


@app.route("/api/sessions")
def api_sessions():
    return jsonify(_get_sessions())


@app.route("/api/latest_summary")
def api_latest_summary():
    sessions = _get_sessions()
    if sessions:
        return jsonify(sessions[0])
    return jsonify({})


@app.route("/api/csv/<session_id>")
def download_csv(session_id):
    """Raw CSV download."""
    frames_file = _find_frames_csv(session_id)
    if not frames_file:
        return "Not found", 404
    directory = os.path.dirname(os.path.abspath(frames_file))
    filename  = os.path.basename(frames_file)
    return send_from_directory(directory, filename, as_attachment=True)


@app.route("/api/graph/<session_id>/<metric>")
def graph(session_id, metric):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        frames_file = _find_frames_csv(session_id)
        if not frames_file:
            return "CSV not found", 404

        times, values = [], []
        with open(frames_file, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    times.append(float(row["time_sec"]))
                    values.append(float(row[metric]))
                except (KeyError, ValueError):
                    continue

        if not times:
            return "No data", 404

        fig, ax = plt.subplots(figsize=(10, 3.2))
        fig.patch.set_facecolor("#0d1117")
        ax.set_facecolor("#0d1117")

        ax.fill_between(times, values, alpha=0.15, color="#00d4ff")
        ax.plot(times, values, color="#00d4ff", linewidth=1.5, alpha=0.9)

        thresholds = {
            "ear":           (0.25, "#ff4757", "Drowsy threshold"),
            "mar":           (0.65, "#ff6b35", "Yawn threshold"),
            "fatigue_score": (75,   "#ff4757", "Critical threshold"),
        }
        if metric in thresholds:
            val, col, lbl = thresholds[metric]
            ax.axhline(val, color=col, linestyle="--", alpha=0.7, linewidth=1)
            ax.text(times[-1], val, f" {lbl}",
                    color=col, fontsize=7, va="bottom")

        labels = {
            "ear": "Eye Aspect Ratio",
            "mar": "Mouth Aspect Ratio",
            "fatigue_score": "Fatigue Score (0-100)",
            "pitch": "Head Pitch (deg)",
            "yaw":   "Head Yaw (deg)",
            "roll":  "Head Roll (deg)",
            "drowsy": "Drowsy (0/1)",
            "phone":  "Phone Detected (0/1)",
        }
        ax.set_title(labels.get(metric, metric),
                     color="#e6edf3", fontsize=11, pad=8, fontweight="bold")
        ax.set_xlabel("Time (s)", color="#8b949e", fontsize=8)
        ax.tick_params(colors="#8b949e", labelsize=7)
        for spine in ax.spines.values():
            spine.set_edgecolor("#30363d")
        ax.grid(True, color="#21262d", linewidth=0.5, alpha=0.8)

        plt.tight_layout(pad=1.2)
        buf = io.BytesIO()
        plt.savefig(buf, format="png", dpi=110,
                    facecolor=fig.get_facecolor())
        plt.close(fig)
        buf.seek(0)
        return Response(buf.read(), mimetype="image/png")

    except Exception as e:
        logger.error(f"[Graph] {e}")
        return f"Error: {e}", 500


# ── Session helpers ───────────────────────────────────────────────────────────
def _get_sessions():
    pattern = os.path.join("reports", "sessions", "*_summary.csv")
    files   = sorted(glob.glob(pattern), reverse=True)
    sessions = []
    for f in files:
        sid = os.path.basename(f).replace("_summary.csv", "")
        try:
            with open(f, newline="", encoding="utf-8") as cf:
                row = next(csv.DictReader(cf))
                row["session_id"] = sid
                sessions.append(row)
        except Exception:
            continue
    return sessions


def _find_frames_csv(session_id: str):
    path = os.path.join(
        "reports", "sessions", f"{session_id}_frames.csv"
    )
    return path if os.path.exists(path) else None


# ── Server starter ────────────────────────────────────────────────────────────
_server_started = False


def start_server(host="127.0.0.1", port=5000, keep_alive=False):
    """
    Flask server start karo.
    keep_alive=True  → webcam band hone ke baad bhi chalta rahe
    keep_alive=False → daemon thread (process ke saath band ho)
    """
    global _server_started
    if _server_started:
        return
    _server_started = True

    log = logging.getLogger("werkzeug")
    log.setLevel(logging.ERROR)

    def _run():
        app.run(host=host, port=port,
                debug=False, threaded=True, use_reloader=False)

    t = threading.Thread(target=_run, daemon=not keep_alive)
    t.start()
    logger.info(f"[Web] Dashboard: http://{host}:{port}")
    print(f"\n[WEB] Dashboard: http://{host}:{port}")
    print(f"[WEB] History:   http://{host}:{port}/history\n")








# """
# web/server.py
# =============
# Flask server — real-time dashboard + session history + graphs.
# SSE (Server-Sent Events) se live data stream hota hai browser mein.
# """

# import json
# import os
# import csv
# import io
# import glob
# import threading
# import logging
# from datetime import datetime
# from flask import Flask, Response, render_template, jsonify, send_from_directory

# logger = logging.getLogger(__name__)

# app = Flask(__name__, template_folder="templates", static_folder="static")

# # ── Shared state (main loop update karta hai, Flask read karta hai) ───────────
# _state = {
#     "ear":           0.0,
#     "mar":           0.0,
#     "pitch":         0.0,
#     "yaw":           0.0,
#     "roll":          0.0,
#     "fatigue_score": 0.0,
#     "fatigue_level": "LOW",
#     "is_drowsy":     False,
#     "is_yawning":    False,
#     "is_distracted": False,
#     "phone_detected": False,
#     "blink_count":   0,
#     "yawn_count":    0,
#     "head_alerts":   0,
#     "fps":           0.0,
#     "face_detected": False,
#     "alert_msg":     "",
#     "session_time":  "00:00",
# }
# _state_lock = threading.Lock()


# def update_state(**kwargs):
#     """Main loop se yeh call karo har frame pe."""
#     with _state_lock:
#         _state.update(kwargs)


# def get_state() -> dict:
#     with _state_lock:
#         return dict(_state)


# # ── SSE — Live data stream ────────────────────────────────────────────────────
# def _event_stream():
#     import time
#     while True:
#         state = get_state()
#         data  = json.dumps(state)
#         yield f"data: {data}\n\n"
#         time.sleep(0.1)   # 10 updates/sec — smooth enough


# @app.route("/stream")
# def stream():
#     return Response(
#         _event_stream(),
#         mimetype="text/event-stream",
#         headers={
#             "Cache-Control": "no-cache",
#             "X-Accel-Buffering": "no",
#         },
#     )


# # ── Pages ─────────────────────────────────────────────────────────────────────
# @app.route("/")
# def index():
#     return render_template("dashboard.html")


# @app.route("/history")
# def history():
#     sessions = _get_sessions()
#     return render_template("history.html", sessions=sessions)


# @app.route("/api/state")
# def api_state():
#     return jsonify(get_state())


# @app.route("/api/sessions")
# def api_sessions():
#     return jsonify(_get_sessions())


# # ── Graph generation ──────────────────────────────────────────────────────────
# @app.route("/api/graph/<session_id>/<metric>")
# def graph(session_id, metric):
#     """
#     CSV se graph banao aur PNG return karo.
#     metric: ear, mar, fatigue_score, pitch, yaw
#     """
#     try:
#         import matplotlib
#         matplotlib.use("Agg")
#         import matplotlib.pyplot as plt
#         import matplotlib.patches as mpatches
#         import numpy as np

#         frames_file = _find_frames_csv(session_id)
#         if not frames_file:
#             return "CSV not found", 404

#         times, values = [], []
#         with open(frames_file, newline="") as f:
#             reader = csv.DictReader(f)
#             for row in reader:
#                 try:
#                     times.append(float(row["time_sec"]))
#                     values.append(float(row[metric]))
#                 except (KeyError, ValueError):
#                     continue

#         if not times:
#             return "No data", 404

#         # ── Styling ──────────────────────────────────────────────────
#         fig, ax = plt.subplots(figsize=(10, 3.5))
#         fig.patch.set_facecolor("#0d1117")
#         ax.set_facecolor("#0d1117")

#         # Gradient fill
#         ax.fill_between(times, values, alpha=0.15, color="#00d4ff")
#         ax.plot(times, values, color="#00d4ff", linewidth=1.5, alpha=0.9)

#         # Threshold lines
#         thresholds = {
#             "ear":           (0.25, "#ff4757", "Drowsy threshold"),
#             "mar":           (0.65, "#ff6b35", "Yawn threshold"),
#             "fatigue_score": (75,   "#ff4757", "Critical threshold"),
#         }
#         if metric in thresholds:
#             val, col, lbl = thresholds[metric]
#             ax.axhline(val, color=col, linestyle="--", alpha=0.7, linewidth=1)
#             ax.text(times[-1], val + 0.01, lbl,
#                     color=col, fontsize=7, ha="right", va="bottom")

#         # Labels
#         labels = {
#             "ear":           "Eye Aspect Ratio (EAR)",
#             "mar":           "Mouth Aspect Ratio (MAR)",
#             "fatigue_score": "Fatigue Score (0–100)",
#             "pitch":         "Head Pitch (degrees)",
#             "yaw":           "Head Yaw (degrees)",
#             "roll":          "Head Roll (degrees)",
#         }
#         ax.set_title(labels.get(metric, metric),
#                      color="#e6edf3", fontsize=11, pad=10, fontweight="bold")
#         ax.set_xlabel("Time (seconds)", color="#8b949e", fontsize=9)
#         ax.tick_params(colors="#8b949e", labelsize=8)
#         for spine in ax.spines.values():
#             spine.set_edgecolor("#30363d")

#         ax.grid(True, color="#21262d", linewidth=0.5, alpha=0.8)

#         plt.tight_layout(pad=1.5)
#         buf = io.BytesIO()
#         plt.savefig(buf, format="png", dpi=120,
#                     facecolor=fig.get_facecolor())
#         plt.close(fig)
#         buf.seek(0)
#         return Response(buf.read(), mimetype="image/png")

#     except Exception as e:
#         logger.error(f"[Graph] {e}")
#         return f"Graph error: {e}", 500


# # ── Session helpers ───────────────────────────────────────────────────────────
# def _get_sessions():
#     pattern = os.path.join("reports", "sessions", "*_summary.csv")
#     files   = sorted(glob.glob(pattern), reverse=True)
#     sessions = []
#     for f in files:
#         sid = os.path.basename(f).replace("_summary.csv", "")
#         try:
#             with open(f, newline="") as cf:
#                 row = next(csv.DictReader(cf))
#                 row["session_id"] = sid
#                 sessions.append(row)
#         except Exception:
#             continue
#     return sessions


# def _find_frames_csv(session_id: str):
#     path = os.path.join("reports", "sessions", f"{session_id}_frames.csv")
#     return path if os.path.exists(path) else None


# # ── Run server ────────────────────────────────────────────────────────────────
# def start_server(host: str = "127.0.0.1", port: int = 5000):
#     """Background thread mein Flask start karo."""
#     log = logging.getLogger("werkzeug")
#     log.setLevel(logging.ERROR)   # Flask ke verbose logs suppress karo

#     t = threading.Thread(
#         target=lambda: app.run(
#             host=host, port=port,
#             debug=False, threaded=True, use_reloader=False,
#         ),
#         daemon=True,
#     )
#     t.start()
#     logger.info(f"[Web] Dashboard: http://{host}:{port}")
#     print(f"\n[WEB] Dashboard open karo: http://{host}:{port}\n")