"""
detectors/face_detectors.py
============================
EAR, MAR, and Head Pose detectors — clean classes, no global state.
"""

import math
import logging
from dataclasses import dataclass, field

import cv2
import numpy as np
from scipy.spatial import distance as dist

logger = logging.getLogger(__name__)

# ── MediaPipe landmark indices ────────────────────────────────────────────────
LEFT_EYE  = [33, 160, 158, 133, 153, 144]
RIGHT_EYE = [362, 385, 387, 263, 373, 380]
MOUTH_V   = [(82, 87), (13, 14), (312, 317)]   # vertical mouth pairs
MOUTH_H   = (78, 308)

# Head-pose landmark IDs + canonical 3-D points (mm, X-right, Y-down, Z-fwd)
HP_IDS = [1, 152, 263, 33, 287, 57]
HP_3D  = np.array([
    [  0.000,   0.000,   0.000],   #  1  nose tip
    [  0.000, -63.600, -12.560],   # 152 chin
    [-43.300,  32.700, -26.000],   # 263 right eye outer
    [ 43.300,  32.700, -26.000],   #  33 left eye outer
    [-28.900, -28.900, -24.200],   # 287 right mouth corner
    [ 28.900, -28.900, -24.200],   #  57 left mouth corner
], dtype=np.float64)


# ── EAR ──────────────────────────────────────────────────────────────────────
def _ear(pts) -> float:
    A = dist.euclidean(pts[1], pts[5])
    B = dist.euclidean(pts[2], pts[4])
    C = dist.euclidean(pts[0], pts[3])
    return (A + B) / (2.0 * C) if C else 0.0


@dataclass
class EARDetector:
    """Eye Aspect Ratio — tracks blinks and drowsiness."""
    threshold: float   = 0.25
    blink_min_frames: int = 3
    drowsy_frames: int = 20

    # runtime state
    eye_frames:  int   = field(default=0, init=False)
    blink_count: int   = field(default=0, init=False)
    _blink_open: bool  = field(default=True, init=False)
    is_drowsy:   bool  = field(default=False, init=False)

    def update(self, lm, w: int, h: int) -> float:
        """Returns current EAR value."""
        def pts(ids):
            return [(int(lm[i].x * w), int(lm[i].y * h)) for i in ids]

        ear = (_ear(pts(LEFT_EYE)) + _ear(pts(RIGHT_EYE))) / 2.0
        closed = ear < self.threshold

        if closed:
            self.eye_frames += 1
        else:
            if not self._blink_open and self.blink_min_frames <= self.eye_frames < self.drowsy_frames:
                self.blink_count += 1
            self.eye_frames = 0
            self.is_drowsy  = False

        self._blink_open = not closed

        if self.eye_frames > self.drowsy_frames:
            self.is_drowsy = True

        return ear

    def reset(self):
        self.eye_frames = self.blink_count = 0
        self._blink_open = True
        self.is_drowsy   = False


# ── MAR ──────────────────────────────────────────────────────────────────────
def _mar(lm, w: int, h: int) -> float:
    def p(i):
        return np.array([lm[i].x * w, lm[i].y * h])

    vert  = sum(dist.euclidean(p(a), p(b)) for a, b in MOUTH_V)
    horiz = dist.euclidean(p(MOUTH_H[0]), p(MOUTH_H[1]))
    return vert / (2.0 * horiz) if horiz else 0.0


@dataclass
class MARDetector:
    """Mouth Aspect Ratio — tracks yawns."""
    threshold:       float = 0.65
    yawn_min_frames: int   = 18

    yawn_frames: int  = field(default=0, init=False)
    yawn_count:  int  = field(default=0, init=False)
    is_yawning:  bool = field(default=False, init=False)

    def update(self, lm, w: int, h: int) -> float:
        mar = _mar(lm, w, h)

        if mar > self.threshold:
            self.yawn_frames += 1
        else:
            if self.is_yawning and self.yawn_frames >= self.yawn_min_frames:
                self.yawn_count += 1
            self.is_yawning  = False
            self.yawn_frames = 0

        if self.yawn_frames >= self.yawn_min_frames:
            self.is_yawning = True

        return mar

    def reset(self):
        self.yawn_frames = self.yawn_count = 0
        self.is_yawning  = False


# ── Head Pose ─────────────────────────────────────────────────────────────────
@dataclass
class HeadPoseDetector:
    """
    Calculates pitch / yaw / roll using solvePnP.
    Tracks sustained off-road head direction.
    """
    pitch_low:    float = -20.0
    pitch_high:   float =  20.0
    yaw_limit:    float =  30.0
    roll_limit:   float =  20.0
    alert_frames: int   =  35

    head_frames:  int  = field(default=0, init=False)
    alert_count:  int  = field(default=0, init=False)
    is_distracted: bool = field(default=False, init=False)

    # last computed angles
    pitch: float = field(default=0.0, init=False)
    yaw:   float = field(default=0.0, init=False)
    roll:  float = field(default=0.0, init=False)

    def update(self, lm, w: int, h: int):
        """Returns (pitch, yaw, roll) in degrees."""
        self.pitch, self.yaw, self.roll = self._solve(lm, w, h)

        off = (
            self.pitch < self.pitch_low
            or self.pitch > self.pitch_high
            or abs(self.yaw)  > self.yaw_limit
            or abs(self.roll) > self.roll_limit
        )

        if off:
            self.head_frames += 1
        else:
            self.head_frames = max(0, self.head_frames - 2)
            if self.head_frames == 0:
                self.is_distracted = False

        if self.head_frames > self.alert_frames:
            if not self.is_distracted:
                self.alert_count += 1
            self.is_distracted = True

        return self.pitch, self.yaw, self.roll

    def reset(self):
        self.head_frames = self.alert_count = 0
        self.is_distracted = False
        self.pitch = self.yaw = self.roll = 0.0

    # ------------------------------------------------------------------
    @staticmethod
    def _solve(lm, w: int, h: int):
        img_pts = np.array(
            [[lm[i].x * w, lm[i].y * h] for i in HP_IDS],
            dtype=np.float64,
        )
        focal = w * 0.8
        cx, cy = w / 2.0, h / 2.0
        cam = np.array(
            [[focal, 0, cx], [0, focal, cy], [0, 0, 1]],
            dtype=np.float64,
        )
        ok, rvec, _ = cv2.solvePnP(
            HP_3D, img_pts, cam,
            np.zeros((4, 1), dtype=np.float64),
            flags=cv2.SOLVEPNP_ITERATIVE,
        )
        if not ok:
            return 0.0, 0.0, 0.0

        R, _ = cv2.Rodrigues(rvec)

        sy       = math.sqrt(R[0, 0] ** 2 + R[1, 0] ** 2)
        singular = sy < 1e-6

        if not singular:
            pitch = math.degrees(math.atan2(-R[2, 0], sy))
            yaw   = math.degrees(math.atan2( R[1, 0], R[0, 0]))
            roll  = math.degrees(math.atan2( R[2, 1], R[2, 2]))
        else:
            pitch = math.degrees(math.atan2(-R[2, 0], sy))
            yaw   = 0.0
            roll  = math.degrees(math.atan2(-R[1, 2], R[1, 1]))

        # Fix yaw-flip (frontal face can wrap ±180)
        if abs(yaw) > 90:
            yaw   = yaw - math.copysign(180, yaw)
            pitch = -pitch
            roll  = roll - math.copysign(180, roll)

        # Keep roll in (-90, 90)
        if   roll >  90: roll -= 180
        elif roll < -90: roll += 180

        return pitch, yaw, roll
