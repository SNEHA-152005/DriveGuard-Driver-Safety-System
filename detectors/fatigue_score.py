"""
detectors/fatigue_score.py
===========================
EAR + MAR + Head pose + blink rate se ek 0-100 fatigue score calculate karo.
Higher = more fatigued/distracted.
"""


class FatigueScoreCalculator:
    """
    Weighted formula:
      - EAR low       → eyes closing     → +weight
      - MAR high      → yawning          → +weight
      - Head off       → distracted       → +weight
      - Phone detected → phone use        → +weight
      - Drowsy flag    → sustained close  → big +weight

    Score 0-100:
      0-24   = LOW
      25-49  = MODERATE
      50-74  = HIGH
      75-100 = CRITICAL
    """

    def __init__(
        self,
        ear_threshold:  float = 0.25,
        mar_threshold:  float = 0.65,
    ):
        self.ear_th = ear_threshold
        self.mar_th = mar_threshold

    def calculate(
        self,
        ear:           float,
        mar:           float,
        is_drowsy:     bool,
        is_yawning:    bool,
        is_distracted: bool,
        phone_detected: bool,
        eye_frames:    int,
        drowsy_frames: int,
    ) -> float:
        score = 0.0

        # EAR component (0-30 points)
        if ear > 0:
            ear_ratio = max(0, (self.ear_th - ear) / self.ear_th)
            score += ear_ratio * 30

        # Sustained drowsiness (0-25 points)
        if is_drowsy:
            score += 25
        elif eye_frames > 0:
            score += min(15, (eye_frames / drowsy_frames) * 15)

        # Yawning (0-20 points)
        if is_yawning:
            score += 20
        elif mar > self.mar_th:
            score += 10

        # Head distraction (0-15 points)
        if is_distracted:
            score += 15

        # Phone use (0-10 points)
        if phone_detected:
            score += 10

        return min(100.0, round(score, 1))

    @staticmethod
    def level(score: float) -> str:
        if score < 25:  return "LOW"
        if score < 50:  return "MODERATE"
        if score < 75:  return "HIGH"
        return "CRITICAL"

    @staticmethod
    def color(score: float):
        """Returns BGR color for HUD display."""
        if score < 25:  return (0, 200, 0)      # green
        if score < 50:  return (0, 200, 255)     # yellow
        if score < 75:  return (0, 140, 255)     # orange
        return (0, 0, 220)                        # red