"""
ui/hud.py
==========
All OpenCV drawing logic — completely separated from detection logic.
"""

import cv2
import numpy as np


# ── Colors (BGR) ─────────────────────────────────────────────────────────────
GREEN  = (0,  210,  60)
RED    = (40,  40, 220)
WHITE  = (230, 230, 230)
YELLOW = (0,  215, 215)
ORANGE = (0,  140, 255)
BLUE   = (255, 100,  0)
DIM    = (150, 150, 150)
DARK   = (70,   70,  70)


class HUDRenderer:
    """Draws the semi-transparent overlay, bars, and alert banners."""

    # ------------------------------------------------------------------
    def draw_panel(self, frame, ear, mar, pitch, yaw, roll,
                   blink_n, yawn_n, head_n,
                   ear_th, mar_th, pitch_lo, pitch_hi, yaw_lim, roll_lim):
        """Main stats panel — top-left corner."""
        ov = frame.copy()
        cv2.rectangle(ov, (0, 0), (265, 275), (15, 15, 15), -1)
        cv2.addWeighted(ov, 0.55, frame, 0.45, 0, frame)

        def row(label, val, ry, color=WHITE):
            cv2.putText(frame, label, (8, ry),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.50, DIM, 1)
            cv2.putText(frame, val, (160, ry),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)

        cv2.putText(frame, "DRIVER MONITOR", (8, 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.58, YELLOW, 2)
        cv2.line(frame, (8, 28), (258, 28), DARK, 1)

        row("EAR",  f"{ear:.2f}",  50,  RED if ear < ear_th else GREEN)
        row("MAR",  f"{mar:.2f}",  76,  RED if mar > mar_th  else GREEN)

        pb = pitch < pitch_lo or pitch > pitch_hi
        row("Pitch", f"{pitch:+.1f}°", 102, RED if pb else GREEN)
        row("Yaw",   f"{yaw:+.1f}°",  128, RED if abs(yaw)  > yaw_lim  else GREEN)
        row("Roll",  f"{roll:+.1f}°", 154, RED if abs(roll) > roll_lim else GREEN)

        cv2.line(frame, (8, 162), (258, 162), DARK, 1)
        row("Blinks",      str(blink_n), 182)
        row("Yawns",       str(yawn_n),  206)
        row("Head Alerts", str(head_n),  230)

        cv2.putText(frame, "R=reset  ESC=quit", (8, 258),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.38, (100, 100, 100), 1)

    # ------------------------------------------------------------------
    def draw_bar(self, frame, val, maxv, x, y, bw, bh, label):
        pct = min(val / maxv, 1.0)
        fw  = int(bw * pct)
        rc  = int(255 * pct)
        gc  = int(255 * (1 - pct))
        cv2.rectangle(frame, (x, y), (x + bw, y + bh), (45, 45, 45), -1)
        cv2.rectangle(frame, (x, y), (x + fw, y + bh), (0, gc, rc), -1)
        cv2.putText(frame, label, (x, y - 4),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.40, (180, 180, 180), 1)

    # ------------------------------------------------------------------
    def draw_alert(self, frame, text, y, color=RED):
        cv2.putText(frame, text, (31, y + 2),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 4)
        cv2.putText(frame, text, (30, y),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, color, 3)

    # ------------------------------------------------------------------
    def draw_nose_arrow(self, frame, lm, w, h, yaw, pitch):
        nx = int(lm[1].x * w)
        ny = int(lm[1].y * h)
        cv2.arrowedLine(
            frame, (nx, ny),
            (int(nx + yaw * 1.5), int(ny - pitch * 1.5)),
            (0, 230, 230), 2, tipLength=0.3,
        )

    # ------------------------------------------------------------------
    def draw_eye_landmarks(self, frame, lm, w, h, left_ids, right_ids):
        for ids in (left_ids, right_ids):
            for i in ids:
                pt = (int(lm[i].x * w), int(lm[i].y * h))
                cv2.circle(frame, pt, 2, GREEN, -1)

    # ------------------------------------------------------------------
    def draw_mouth_landmarks(self, frame, lm, w, h, indices):
        for i in indices:
            pt = (int(lm[i].x * w), int(lm[i].y * h))
            cv2.circle(frame, pt, 2, (255, 190, 0), -1)

    # ------------------------------------------------------------------
    def draw_fps(self, frame, fps: float):
        cv2.putText(frame, f"FPS: {fps:.1f}", (270, 110),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (180, 180, 180), 1)
