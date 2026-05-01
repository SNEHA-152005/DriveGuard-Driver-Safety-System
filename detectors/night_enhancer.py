"""
detectors/night_enhancer.py  — v3 (Simple Fix)
================================================
Problem v2 mein: Bahut aggressive processing se frame blur/distorted
ho jaata tha — MediaPipe aur YOLO dono fail ho jaate the.

Fix: Sirf 2 simple operations:
  1. Brightness boost (gamma correction only)
  2. Adaptive thresholds (EAR/MAR relax)

NO denoise, NO complex CLAHE pipeline — sirf gamma.
Gamma ek simple pixel-level operation hai jo detection
ko affect nahi karta.
"""

import cv2
import numpy as np
import logging

logger = logging.getLogger(__name__)


class NightEnhancer:

    DAY_THRESHOLD  = 100
    DUSK_THRESHOLD = 60

    def __init__(self):
        self.current_mode       = "DAY"
        self.current_brightness = 255.0
        self._frame_cnt         = 0
        self._lut_cache         = {}   # gamma LUT cache

        # Adaptive thresholds — main.py inhe read karta hai
        self.ear_threshold = 0.25
        self.mar_threshold = 0.65

    # ------------------------------------------------------------------
    def enhance(self, frame: np.ndarray):
        """
        General enhancement — MediaPipe ke liye.
        Returns: (enhanced_frame, mode, brightness)
        """
        self._frame_cnt += 1

        # Brightness check har 15 frames
        if self._frame_cnt % 15 == 0:
            self.current_brightness = self._brightness(frame)
            new_mode = self._mode(self.current_brightness)
            if new_mode != self.current_mode:
                self.current_mode = new_mode
                self._update_thresholds()
                logger.info(
                    f"[Night] Mode: {self.current_mode} "
                    f"brightness={self.current_brightness:.0f} "
                    f"EAR={self.ear_threshold} MAR={self.mar_threshold}"
                )

        if self.current_mode == "DAY":
            return frame, "DAY", self.current_brightness

        # Sirf gamma — koi distortion nahi
        gamma   = 2.0 if self.current_mode == "NIGHT" else 1.5
        enhanced = self._gamma(frame, gamma)
        return enhanced, self.current_mode, self.current_brightness

    # ------------------------------------------------------------------
    def enhance_for_yolo(self, frame: np.ndarray) -> np.ndarray:
        """
        YOLO ke liye — same simple gamma, koi extra processing nahi.
        """
        if self.current_mode == "DAY":
            return frame

        gamma = 2.2 if self.current_mode == "NIGHT" else 1.6
        return self._gamma(frame, gamma)

    # ------------------------------------------------------------------
    def enhance_for_mediapipe(self, frame: np.ndarray) -> np.ndarray:
        """
        MediaPipe ke liye — gamma only.
        """
        if self.current_mode == "DAY":
            return frame

        gamma = 1.8 if self.current_mode == "NIGHT" else 1.4
        return self._gamma(frame, gamma)

    # ------------------------------------------------------------------
    def draw_mode_indicator(self, frame: np.ndarray):
        H, W = frame.shape[:2]
        colors = {
            "DAY":   (0, 210, 60),
            "DUSK":  (0, 165, 255),
            "NIGHT": (255, 120, 50),
        }
        color = colors.get(self.current_mode, (200, 200, 200))
        bx    = W - 165

        cv2.rectangle(frame, (bx, 90), (W-5, 138), (15,15,15), -1)
        cv2.rectangle(frame, (bx, 90), (W-5, 138), color, 1)
        cv2.putText(frame, self.current_mode,
                    (bx+8, 112),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.52, color, 2)
        cv2.putText(frame, f"BRT:{self.current_brightness:.0f}",
                    (bx+8, 128),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.36, (150,150,150), 1)
        if self.current_mode == "NIGHT":
            cv2.putText(frame, "NIGHT MODE",
                        (bx+8, 140),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.30, color, 1)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------
    def _gamma(self, frame: np.ndarray, gamma: float) -> np.ndarray:
        """
        Fast gamma correction using LUT.
        Sirf pixel values badalta hai — structure nahi.
        """
        key = round(gamma, 1)
        if key not in self._lut_cache:
            inv   = 1.0 / gamma
            table = np.array([
                min(255, int(((i / 255.0) ** inv) * 255))
                for i in range(256)
            ], dtype=np.uint8)
            self._lut_cache[key] = table
        return cv2.LUT(frame, self._lut_cache[key])

    @staticmethod
    def _brightness(frame: np.ndarray) -> float:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        return float(np.mean(gray))

    def _mode(self, b: float) -> str:
        if b >= self.DAY_THRESHOLD:  return "DAY"
        if b >= self.DUSK_THRESHOLD: return "DUSK"
        return "NIGHT"

    def _update_thresholds(self):
        """Night mein thresholds relax karo."""
        if self.current_mode == "NIGHT":
            self.ear_threshold = 0.22
            self.mar_threshold = 0.60
        elif self.current_mode == "DUSK":
            self.ear_threshold = 0.23
            self.mar_threshold = 0.62
        else:
            self.ear_threshold = 0.25
            self.mar_threshold = 0.65
















# """
# detectors/night_enhancer.py  — v2
# ====================================
# Night/low-light detection enhancement.
# CLAHE + Gamma correction + YOLO-specific boost.

# v2 Changes:
#   - YOLO ke liye alag aggressive enhancement
#   - Gamma correction add kiya — dark pixels specifically boost hote hain
#   - Phone detection ke liye brightness normalize karta hai
#   - Face detection aur phone detection ke liye alag frames

# Koi extra library nahi — sirf OpenCV (already installed).
# """

# import cv2
# import numpy as np
# import logging

# logger = logging.getLogger(__name__)


# class NightEnhancer:
#     """
#     Low-light frame enhancer.

#     2 enhanced frames deta hai:
#       - enhance()       → face detection ke liye (MediaPipe)
#       - enhance_yolo()  → phone detection ke liye (YOLO) — more aggressive
#     """

#     DAY_THRESHOLD   = 100
#     DUSK_THRESHOLD  = 60

#     def __init__(self):
#         # CLAHE variants
#         self._clahe_night = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
#         self._clahe_dusk  = cv2.createCLAHE(clipLimit=1.5, tileGridSize=(8, 8))
#         # YOLO ke liye zyada aggressive CLAHE
#         self._clahe_yolo  = cv2.createCLAHE(clipLimit=4.0, tileGridSize=(4, 4))

#         self.current_mode       = "DAY"
#         self.current_brightness = 255.0
#         self._frame_skip        = 0

#         # Gamma LUT precompute — fast gamma correction
#         self._gamma_lut = {}
#         for g in [1.5, 2.0, 2.5]:
#             self._gamma_lut[g] = self._build_gamma_lut(g)

#     # ------------------------------------------------------------------
#     def enhance(self, frame: np.ndarray):
#         """
#         MediaPipe face detection ke liye enhanced frame.
#         Returns: (enhanced_frame, mode, brightness)
#         """
#         self._frame_skip += 1
#         if self._frame_skip % 10 == 0:
#             self.current_brightness = self._get_brightness(frame)
#             old = self.current_mode
#             self.current_mode = self._get_mode(self.current_brightness)
#             if old != self.current_mode:
#                 logger.info(
#                     f"[Night] {old} -> {self.current_mode} "
#                     f"(brightness={self.current_brightness:.0f})"
#                 )

#         if self.current_mode == "DAY":
#             return frame, "DAY", self.current_brightness

#         enhanced = self._apply_clahe(frame, self.current_mode)
#         return enhanced, self.current_mode, self.current_brightness

#     # ------------------------------------------------------------------
#     def enhance_for_yolo(self, frame: np.ndarray) -> np.ndarray:
#         """
#         YOLO phone detection ke liye specially enhanced frame.
#         Zyada aggressive — phone edges aur colors boost karta hai.

#         Day mein bhi mild enhancement deta hai (YOLO accuracy improve hoti hai).
#         """
#         brightness = self.current_brightness

#         if brightness >= self.DAY_THRESHOLD:
#             # Day — sirf mild sharpening
#             return self._sharpen(frame)

#         elif brightness >= self.DUSK_THRESHOLD:
#             # Dusk — CLAHE + gamma 1.5
#             enhanced = self._apply_clahe(frame, "DUSK")
#             enhanced = self._apply_gamma(enhanced, 1.5)
#             return self._sharpen(enhanced)

#         else:
#             # Night — aggressive pipeline
#             # Step 1: Denoise (salt & pepper noise remove)
#             denoised = cv2.fastNlMeansDenoisingColored(
#                 frame, None, 5, 5, 7, 15
#             )
#             # Step 2: Aggressive CLAHE
#             enhanced = self._apply_clahe_yolo(denoised)
#             # Step 3: Gamma correction — dark pixels boost
#             gamma = 2.0 if brightness > 30 else 2.5
#             enhanced = self._apply_gamma(enhanced, gamma)
#             # Step 4: Sharpen edges (phone edges clear hote hain)
#             enhanced = self._sharpen(enhanced)
#             return enhanced

#     # ------------------------------------------------------------------
#     def draw_mode_indicator(self, frame: np.ndarray):
#         """OpenCV window pe mode indicator."""
#         H, W = frame.shape[:2]
#         colors = {
#             "DAY":   (0, 210, 60),
#             "DUSK":  (0, 165, 255),
#             "NIGHT": (255, 100, 50),
#         }
#         color = colors.get(self.current_mode, (200, 200, 200))
#         bx    = W - 160

#         cv2.rectangle(frame, (bx, 90), (W - 5, 132), (15, 15, 15), -1)
#         cv2.rectangle(frame, (bx, 90), (W - 5, 132), color, 1)
#         cv2.putText(frame, self.current_mode,
#                     (bx + 8, 112), cv2.FONT_HERSHEY_SIMPLEX,
#                     0.50, color, 2)
#         cv2.putText(frame, f"BRT:{self.current_brightness:.0f}",
#                     (bx + 8, 128), cv2.FONT_HERSHEY_SIMPLEX,
#                     0.35, (150, 150, 150), 1)
#         if self.current_mode == "NIGHT":
#             cv2.putText(frame, "LOW LIGHT BOOST ON",
#                         (bx - 30, 146), cv2.FONT_HERSHEY_SIMPLEX,
#                         0.35, color, 1)

#     # ------------------------------------------------------------------
#     # Private helpers
#     # ------------------------------------------------------------------
#     def _apply_clahe(self, frame: np.ndarray, mode: str) -> np.ndarray:
#         """LAB color space mein CLAHE — colors preserve karta hai."""
#         try:
#             lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
#             l, a, b = cv2.split(lab)
#             clahe = self._clahe_night if mode == "NIGHT" else self._clahe_dusk
#             l_enh = clahe.apply(l)
#             lab_enh = cv2.merge([l_enh, a, b])
#             return cv2.cvtColor(lab_enh, cv2.COLOR_LAB2BGR)
#         except Exception as e:
#             logger.warning(f"[CLAHE] {e}")
#             return frame

#     def _apply_clahe_yolo(self, frame: np.ndarray) -> np.ndarray:
#         """YOLO ke liye aggressive CLAHE."""
#         try:
#             lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
#             l, a, b = cv2.split(lab)
#             l_enh = self._clahe_yolo.apply(l)
#             return cv2.cvtColor(cv2.merge([l_enh, a, b]), cv2.COLOR_LAB2BGR)
#         except Exception as e:
#             logger.warning(f"[CLAHE YOLO] {e}")
#             return frame

#     def _apply_gamma(self, frame: np.ndarray, gamma: float) -> np.ndarray:
#         """Gamma correction — dark pixels specifically boost."""
#         lut = self._gamma_lut.get(gamma)
#         if lut is None:
#             lut = self._build_gamma_lut(gamma)
#             self._gamma_lut[gamma] = lut
#         return cv2.LUT(frame, lut)

#     def _sharpen(self, frame: np.ndarray) -> np.ndarray:
#         """Edge sharpening — phone ka rectangular shape clear karta hai."""
#         kernel = np.array([
#             [ 0, -1,  0],
#             [-1,  5, -1],
#             [ 0, -1,  0],
#         ], dtype=np.float32)
#         return cv2.filter2D(frame, -1, kernel)

#     @staticmethod
#     def _build_gamma_lut(gamma: float) -> np.ndarray:
#         """Gamma correction lookup table — fast apply ke liye."""
#         inv_gamma = 1.0 / gamma
#         table = np.array([
#             ((i / 255.0) ** inv_gamma) * 255
#             for i in range(256)
#         ], dtype=np.uint8)
#         return table

#     @staticmethod
#     def _get_brightness(frame: np.ndarray) -> float:
#         gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
#         return float(np.mean(gray))

#     def _get_mode(self, brightness: float) -> str:
#         if brightness >= self.DAY_THRESHOLD:
#             return "DAY"
#         elif brightness >= self.DUSK_THRESHOLD:
#             return "DUSK"
#         return "NIGHT"







# # working

# """
# detectors/night_enhancer.py
# ============================
# Night/low-light detection enhancement.
# CLAHE (Contrast Limited Adaptive Histogram Equalization) use karta hai.
# OpenCV built-in — koi extra library install nahi karni.

# Kya karta hai:
#   1. Frame ki brightness check karta hai
#   2. Agar dark hai → CLAHE apply karta hai
#   3. Enhanced frame detection ke liye use hota hai
#   4. Original frame display ke liye (HUD pe) — enhanced nahi dikhata

# Brightness levels:
#   > 100  → Day mode   — no enhancement
#   60-100 → Dusk mode  — light enhancement
#   < 60   → Night mode — full CLAHE enhancement
# """

# import cv2
# import numpy as np
# import logging

# logger = logging.getLogger(__name__)


# class NightEnhancer:
#     """
#     Low-light frame enhancer using CLAHE.
#     Detection ke liye enhanced frame use karo,
#     display ke liye original frame.
#     """

#     # Brightness thresholds
#     DAY_THRESHOLD   = 100   # above this = day, no enhancement
#     DUSK_THRESHOLD  = 60    # 60-100 = dusk, light enhancement
#     NIGHT_THRESHOLD = 60    # below this = night, full enhancement

#     def __init__(self):
#         # CLAHE for night — aggressive
#         self._clahe_night = cv2.createCLAHE(
#             clipLimit=3.0,
#             tileGridSize=(8, 8),
#         )
#         # CLAHE for dusk — mild
#         self._clahe_dusk = cv2.createCLAHE(
#             clipLimit=1.5,
#             tileGridSize=(8, 8),
#         )
#         self.current_mode    = "DAY"
#         self.current_brightness = 255
#         self._frame_skip = 0   # brightness check har 10 frames pe

#     # ------------------------------------------------------------------
#     def enhance(self, frame: np.ndarray):
#         """
#         Frame enhance karo agar dark ho.

#         Returns:
#             enhanced_frame — detection ke liye use karo (MediaPipe + YOLO)
#             mode           — "DAY" / "DUSK" / "NIGHT"
#             brightness     — 0-255
#         """
#         self._frame_skip += 1

#         # Brightness check har 10 frames pe — performance ke liye
#         if self._frame_skip % 10 == 0:
#             self.current_brightness = self._get_brightness(frame)
#             old_mode = self.current_mode
#             self.current_mode = self._get_mode(self.current_brightness)
#             if old_mode != self.current_mode:
#                 logger.info(
#                     f"[NightEnhancer] Mode changed: "
#                     f"{old_mode} → {self.current_mode} "
#                     f"(brightness={self.current_brightness:.0f})"
#                 )

#         # No enhancement in day mode
#         if self.current_mode == "DAY":
#             return frame, "DAY", self.current_brightness

#         # Apply CLAHE
#         enhanced = self._apply_clahe(frame, self.current_mode)
#         return enhanced, self.current_mode, self.current_brightness

#     # ------------------------------------------------------------------
#     def draw_mode_indicator(self, frame: np.ndarray):
#         """
#         OpenCV window pe mode indicator dikhao — top right corner.
#         """
#         H, W = frame.shape[:2]
#         mode   = self.current_mode
#         bright = self.current_brightness

#         colors = {
#             "DAY":   (0, 210, 60),    # green
#             "DUSK":  (0, 165, 255),   # orange
#             "NIGHT": (255, 100, 0),   # blue
#         }
#         icons = {
#             "DAY":   "DAY",
#             "DUSK":  "DUSK",
#             "NIGHT": "NIGHT",
#         }

#         color = colors.get(mode, (200, 200, 200))
#         text  = icons.get(mode, mode)

#         # Background box
#         bx = W - 160
#         cv2.rectangle(frame, (bx, 90), (W - 5, 130), (15, 15, 15), -1)
#         cv2.rectangle(frame, (bx, 90), (W - 5, 130), color, 1)

#         cv2.putText(frame, text, (bx + 8, 112),
#                     cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
#         cv2.putText(frame, f"BRT:{bright:.0f}", (bx + 8, 126),
#                     cv2.FONT_HERSHEY_SIMPLEX, 0.35, (150, 150, 150), 1)

#         # Night warning
#         if mode == "NIGHT":
#             cv2.putText(frame, "LOW LIGHT", (bx - 5, 145),
#                         cv2.FONT_HERSHEY_SIMPLEX, 0.38, color, 1)

#     # ------------------------------------------------------------------
#     def _apply_clahe(self, frame: np.ndarray, mode: str) -> np.ndarray:
#         """
#         CLAHE apply karo — LAB color space mein (best results).
#         Sirf L channel pe apply karte hain — colors natural rehte hain.
#         """
#         try:
#             # BGR → LAB
#             lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
#             l, a, b = cv2.split(lab)

#             # CLAHE sirf L (lightness) channel pe
#             clahe = (self._clahe_night
#                      if mode == "NIGHT"
#                      else self._clahe_dusk)
#             l_enhanced = clahe.apply(l)

#             # Merge back
#             lab_enhanced = cv2.merge([l_enhanced, a, b])

#             # LAB → BGR
#             enhanced = cv2.cvtColor(lab_enhanced, cv2.COLOR_LAB2BGR)
#             return enhanced

#         except Exception as e:
#             logger.warning(f"[NightEnhancer] CLAHE failed: {e}")
#             return frame   # fallback to original

#     # ------------------------------------------------------------------
#     @staticmethod
#     def _get_brightness(frame: np.ndarray) -> float:
#         """Average brightness of frame (0-255)."""
#         gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
#         return float(np.mean(gray))

#     def _get_mode(self, brightness: float) -> str:
#         if brightness >= self.DAY_THRESHOLD:
#             return "DAY"
#         elif brightness >= self.DUSK_THRESHOLD:
#             return "DUSK"
#         else:
#             return "NIGHT"