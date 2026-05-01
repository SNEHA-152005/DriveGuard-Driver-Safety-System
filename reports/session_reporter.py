"""
reports/session_reporter.py
============================
Har frame ki data CSV mein save karo.
Session khatam hone pe summary CSV aur text report banao.
"""

import csv
import os
import time
import logging
from datetime import datetime
from dataclasses import dataclass, field
from typing import List

logger = logging.getLogger(__name__)


@dataclass
class FrameRecord:
    timestamp:     float
    ear:           float
    mar:           float
    pitch:         float
    yaw:           float
    roll:          float
    is_drowsy:     bool
    is_yawning:    bool
    is_distracted: bool
    phone_detected: bool
    fatigue_score: float


class SessionReporter:
    """
    Continuously logs frame data and generates reports on session end.

    Files generated (inside reports/sessions/):
      - YYYY-MM-DD_HH-MM-SS_frames.csv   → per-frame data
      - YYYY-MM-DD_HH-MM-SS_summary.csv  → session summary
    """

    def __init__(self, output_dir: str = "reports/sessions"):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

        ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self.frames_path  = os.path.join(output_dir, f"{ts}_frames.csv")
        self.summary_path = os.path.join(output_dir, f"{ts}_summary.csv")

        self._records: List[FrameRecord] = []
        self._start_time = time.time()

        # Write header immediately
        self._write_frames_header()
        logger.info(f"[Reporter] Logging to {self.frames_path}")

    # ------------------------------------------------------------------
    def log_frame(
        self,
        ear: float, mar: float,
        pitch: float, yaw: float, roll: float,
        is_drowsy: bool, is_yawning: bool,
        is_distracted: bool, phone_detected: bool,
        fatigue_score: float,
    ):
        rec = FrameRecord(
            timestamp=round(time.time() - self._start_time, 3),
            ear=round(ear, 3),
            mar=round(mar, 3),
            pitch=round(pitch, 2),
            yaw=round(yaw, 2),
            roll=round(roll, 2),
            is_drowsy=is_drowsy,
            is_yawning=is_yawning,
            is_distracted=is_distracted,
            phone_detected=phone_detected,
            fatigue_score=round(fatigue_score, 1),
        )
        self._records.append(rec)

        # Har 30 frames pe disk pe flush karo
        if len(self._records) % 30 == 0:
            self._flush_frames()

    # ------------------------------------------------------------------
    def finalize(
        self,
        blink_count: int,
        yawn_count: int,
        head_alert_count: int,
    ) -> str:
        """
        Session khatam hone pe call karo.
        Summary CSV banata hai aur path return karta hai.
        """
        self._flush_frames()  # baaki records flush karo

        duration_sec = time.time() - self._start_time
        total_frames = len(self._records)

        drowsy_frames   = sum(1 for r in self._records if r.is_drowsy)
        yawn_frames     = sum(1 for r in self._records if r.is_yawning)
        distract_frames = sum(1 for r in self._records if r.is_distracted)
        phone_frames    = sum(1 for r in self._records if r.phone_detected)

        avg_ear     = self._avg("ear")
        avg_mar     = self._avg("mar")
        avg_fatigue = self._avg("fatigue_score")
        max_fatigue = max((r.fatigue_score for r in self._records), default=0)

        summary = {
            "session_date":         datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "duration_seconds":     round(duration_sec, 1),
            "total_frames":         total_frames,
            "avg_ear":              round(avg_ear, 3),
            "avg_mar":              round(avg_mar, 3),
            "blink_count":          blink_count,
            "yawn_count":           yawn_count,
            "head_alert_count":     head_alert_count,
            "drowsy_frames":        drowsy_frames,
            "drowsy_percent":       round(100 * drowsy_frames / max(total_frames, 1), 1),
            "yawn_frames":          yawn_frames,
            "distracted_frames":    distract_frames,
            "distracted_percent":   round(100 * distract_frames / max(total_frames, 1), 1),
            "phone_frames":         phone_frames,
            "avg_fatigue_score":    round(avg_fatigue, 1),
            "max_fatigue_score":    round(max_fatigue, 1),
            "risk_level":           self._risk_level(avg_fatigue),
        }

        with open(self.summary_path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=summary.keys())
            w.writeheader()
            w.writerow(summary)

        logger.info(f"[Reporter] Summary saved: {self.summary_path}")
        self._print_summary(summary)
        return self.summary_path

    # ------------------------------------------------------------------
    def _write_frames_header(self):
        with open(self.frames_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "time_sec", "ear", "mar", "pitch", "yaw", "roll",
                "drowsy", "yawning", "distracted", "phone", "fatigue_score"
            ])

    def _flush_frames(self):
        if not self._records:
            return
        with open(self.frames_path, "a", newline="") as f:
            writer = csv.writer(f)
            for r in self._records[-30:]:   # sirf nayi wali
                writer.writerow([
                    r.timestamp, r.ear, r.mar,
                    r.pitch, r.yaw, r.roll,
                    int(r.is_drowsy), int(r.is_yawning),
                    int(r.is_distracted), int(r.phone_detected),
                    r.fatigue_score,
                ])

    def _avg(self, field: str) -> float:
        vals = [getattr(r, field) for r in self._records]
        return sum(vals) / len(vals) if vals else 0.0

    @staticmethod
    def _risk_level(avg_fatigue: float) -> str:
        if avg_fatigue < 25:  return "LOW"
        if avg_fatigue < 50:  return "MODERATE"
        if avg_fatigue < 75:  return "HIGH"
        return "CRITICAL"

    @staticmethod
    def _print_summary(s: dict):
        print("\n" + "="*55)
        print("         SESSION REPORT SUMMARY")
        print("="*55)
        print(f"  Date/Time       : {s['session_date']}")
        print(f"  Duration        : {s['duration_seconds']}s")
        print(f"  Total Frames    : {s['total_frames']}")
        print(f"  Blinks          : {s['blink_count']}")
        print(f"  Yawns           : {s['yawn_count']}")
        print(f"  Head Alerts     : {s['head_alert_count']}")
        print(f"  Drowsy %        : {s['drowsy_percent']}%")
        print(f"  Distracted %    : {s['distracted_percent']}%")
        print(f"  Phone Frames    : {s['phone_frames']}")
        print(f"  Avg Fatigue     : {s['avg_fatigue_score']}/100")
        print(f"  Max Fatigue     : {s['max_fatigue_score']}/100")
        print(f"  Risk Level      : {s['risk_level']}")
        print("="*55)