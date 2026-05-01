"""
safety/critical_state_monitor.py  — v4
========================================
Changes:
  - Drowsy + Head tilt threshold: 10s → 20s
  - Rest places ab driver ki OpenCV screen pe bhi dikhte hain
  - Telegram naya token/chat_id se kaam karega
  - Rest places fetch improved — agar OSM fail ho to fallback message

Critical conditions (OR logic):
  A: Drowsy + Head tilt DONO 20+ seconds
  B: Fatigue 75+ for 10+ seconds
"""

import time
import logging
import threading
import math
from dataclasses import dataclass, field
from typing import List, Optional

import cv2
import numpy as np

logger = logging.getLogger(__name__)

SEARCH_RADIUS     = 5000    # meters
COND_A_SECS       = 20.0   # Drowsy + Head tilt threshold
COND_B_SECS       = 10.0   # High fatigue threshold


@dataclass
class RestPlace:
    name:       str
    lat:        float
    lon:        float
    place_type: str
    distance_m: float = 0.0

    @property
    def maps_link(self) -> str:
        return f"https://www.google.com/maps?q={self.lat},{self.lon}"

    @property
    def distance_str(self) -> str:
        if self.distance_m < 1000:
            return f"{self.distance_m:.0f}m"
        return f"{self.distance_m/1000:.1f}km"


class CriticalStateMonitor:

    def __init__(
        self,
        alert_manager,
        emergency_system,
        rest_cooldown: float = 120.0,
    ):
        self.alert_manager = alert_manager
        self.emergency     = emergency_system
        self.rest_cooldown = rest_cooldown

        # Condition A: Drowsy + Head tilt together (20s)
        self._cond_a_start: Optional[float] = None

        # Condition B: Fatigue 75+ sustained (10s)
        self._cond_b_start: Optional[float] = None

        self._last_stop_alert:  float = 0.0
        self._alerted_episode:  bool  = False

        self._rest_places:  List[RestPlace] = []
        self._fetching:     bool  = False
        self._location:     dict  = {}

        # Show rest places on screen for N seconds after alert
        self._show_rest_until: float = 0.0

        # Pre-fetch location + rest places on startup
        threading.Thread(target=self._prefetch_all, daemon=True).start()

    # ------------------------------------------------------------------
    def update(
        self,
        fatigue_score: float,
        is_drowsy:     bool,
        is_distracted: bool,
        location:      dict,
    ) -> Optional[str]:
        now = time.time()
        if location:
            self._location = location

        # ── Condition A: Drowsy AND head distracted ───────────────────
        cond_a_active = is_drowsy and is_distracted
        if cond_a_active:
            if self._cond_a_start is None:
                self._cond_a_start = now
                logger.info("[Critical-A] Drowsy+HeadTilt started")
                self._maybe_fetch_rest_places()
        else:
            self._cond_a_start = None

        # ── Condition B: Fatigue 75+ ──────────────────────────────────
        cond_b_active = fatigue_score >= 75
        if cond_b_active:
            if self._cond_b_start is None:
                self._cond_b_start = now
                logger.info(f"[Critical-B] High fatigue started: {fatigue_score:.1f}")
                self._maybe_fetch_rest_places()
        else:
            self._cond_b_start    = None
            self._alerted_episode = False

        # ── Check thresholds ──────────────────────────────────────────
        elapsed_a = (now - self._cond_a_start) if self._cond_a_start else 0.0
        elapsed_b = (now - self._cond_b_start) if self._cond_b_start else 0.0

        a_triggered = elapsed_a >= COND_A_SECS
        b_triggered = elapsed_b >= COND_B_SECS

        if (a_triggered or b_triggered) and not self._alerted_episode:
            if (now - self._last_stop_alert) >= self.rest_cooldown:
                self._alerted_episode = True
                self._last_stop_alert = now
                reason = self._build_reason(
                    a_triggered, b_triggered,
                    elapsed_a, elapsed_b, fatigue_score
                )
                self._fire_stop_alert(fatigue_score, reason)
                # Show rest places on screen for 30 seconds
                self._show_rest_until = now + 30.0
                return "STOP VEHICLE NOW!"

        # Reset when both clear
        if not cond_a_active and not cond_b_active:
            self._alerted_episode = False

        return None

    # ------------------------------------------------------------------
    def draw_on_frame(self, frame):
        """
        Screen pe rest places dikhao jab alert fire ho.
        Driver clearly dekh sake — large text, dark background.
        """
        now = time.time()

        # Critical timer banner (bottom)
        elapsed   = self.get_elapsed()
        condition = self.get_active_condition()
        if elapsed > 0:
            self._draw_critical_banner(frame, elapsed, condition)

        # Rest places panel (center-right) — 30 seconds tak dikhao
        if now < self._show_rest_until and self._rest_places:
            self._draw_rest_places_panel(frame)

    # ------------------------------------------------------------------
    def _draw_critical_banner(self, frame, elapsed: float, condition: str):
        H, W = frame.shape[:2]
        alpha = 0.3 + 0.15 * abs((elapsed % 1.0) - 0.5)
        overlay = frame.copy()
        cv2.rectangle(overlay, (0, H-100), (W, H), (0, 0, 180), -1)
        cv2.addWeighted(overlay, alpha, frame, 1-alpha, 0, frame)

        cv2.putText(frame,
                    f"CRITICAL {elapsed:.0f}s — {condition}",
                    (10, H-68),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.58, (255, 80, 80), 2)
        cv2.putText(frame,
                    "STOP THE VEHICLE SAFELY & TAKE REST",
                    (10, H-35),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.62, (255, 255, 255), 2)

    # ------------------------------------------------------------------
    def _draw_rest_places_panel(self, frame):
        """
        Driver ki screen pe rest places dikhao — large, readable panel.
        """
        H, W = frame.shape[:2]

        places = self._rest_places[:3]
        panel_h = 40 + len(places) * 70 + 20
        panel_w = min(W - 40, 520)
        px      = (W - panel_w) // 2   # center horizontally
        py      = (H - 100 - panel_h) - 10  # just above critical banner

        # Dark background
        overlay = frame.copy()
        cv2.rectangle(overlay, (px-10, py-10),
                      (px+panel_w+10, py+panel_h+10),
                      (10, 10, 10), -1)
        cv2.addWeighted(overlay, 0.88, frame, 0.12, 0, frame)

        # Border
        cv2.rectangle(frame, (px-10, py-10),
                      (px+panel_w+10, py+panel_h+10),
                      (0, 100, 255), 2)

        # Title
        cv2.putText(frame, "NEAREST REST PLACES",
                    (px, py+28),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 180, 255), 2)
        cv2.line(frame, (px, py+36), (px+panel_w, py+36), (0,100,255), 1)

        # Each place
        for i, p in enumerate(places):
            base_y = py + 50 + i * 70

            # Number circle
            cv2.circle(frame, (px+14, base_y+8), 14, (0,100,255), -1)
            cv2.putText(frame, str(i+1),
                        (px+8, base_y+14),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255,255,255), 2)

            # Name
            name_display = p.name[:38] + ".." if len(p.name) > 38 else p.name
            cv2.putText(frame, name_display,
                        (px+36, base_y+14),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.58, (255,255,255), 2)

            # Distance + type
            info = f"{p.distance_str}  |  {p.place_type.replace('_',' ').title()}"
            cv2.putText(frame, info,
                        (px+36, base_y+36),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (150,200,255), 1)

            # Maps link (short)
            short_link = f"maps.google.com?q={p.lat:.3f},{p.lon:.3f}"
            cv2.putText(frame, short_link,
                        (px+36, base_y+54),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.38, (100,150,200), 1)

    # ------------------------------------------------------------------
    def get_elapsed(self) -> float:
        now = time.time()
        a = (now - self._cond_a_start) if self._cond_a_start else 0.0
        b = (now - self._cond_b_start) if self._cond_b_start else 0.0
        return max(a, b)

    def get_active_condition(self) -> str:
        a = self._cond_a_start is not None
        b = self._cond_b_start is not None
        if a and b: return "DROWSY+HEAD+HIGH FATIGUE"
        if a:       return "DROWSY + HEAD TILT"
        if b:       return "HIGH FATIGUE 75+"
        return ""

    # ------------------------------------------------------------------
    def _build_reason(self, a, b, ela, elb, score) -> str:
        parts = []
        if a: parts.append(f"Drowsy+HeadTilt {ela:.0f}s")
        if b: parts.append(f"Fatigue {score:.0f}/100 for {elb:.0f}s")
        return " | ".join(parts)

    def _fire_stop_alert(self, score: float, reason: str):
        elapsed = self.get_elapsed()
        logger.warning(f"[STOP ALERT] {reason}")

        self.alert_manager.trigger(
            "stop_now",
            beep_freq=1500, beep_dur=1500,
            speech=(
                f"Danger! Critical condition for {elapsed:.0f} seconds. "
                "Stop the vehicle immediately and take rest. "
                "Nearest rest places are shown on screen."
            ),
            force=True,
        )

        # Terminal
        print("\n" + "!"*60)
        print("  CRITICAL ALERT — STOP THE VEHICLE NOW!")
        print(f"  {reason}")
        if self._rest_places:
            print("\n  NEAREST REST PLACES:")
            for i, p in enumerate(self._rest_places[:3], 1):
                print(f"  {i}. {p.name} ({p.distance_str})")
                print(f"     {p.maps_link}")
        print("!"*60 + "\n")

        if self.emergency.enabled:
            threading.Thread(
                target=self._send_emergency,
                args=(score, reason, elapsed),
                daemon=True,
            ).start()

    # ------------------------------------------------------------------
    def _send_emergency(self, score, reason, elapsed):
        from datetime import datetime
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart

        loc     = self._location
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        rest_txt = "\nNEAREST REST PLACES:\n"
        rest_tg  = "\n\n[STOP] *Nearest Rest Places:*\n"
        if self._rest_places:
            for i, p in enumerate(self._rest_places[:3], 1):
                rest_txt += f"  {i}. {p.name} ({p.distance_str})\n     {p.maps_link}\n"
                rest_tg  += f"{i}. *{p.name}* ({p.distance_str})\n   {p.maps_link}\n"
        else:
            rest_txt += "  Rest places unavailable — stop safely.\n"
            rest_tg  += "_Unavailable — stop safely._"

        # Gmail
        if self.emergency.gmail_enabled:
            try:
                g       = self.emergency.gmail_cfg
                subject = f"🚨 STOP VEHICLE — Critical {elapsed:.0f}s | {score:.0f}/100"
                body    = (
                    f"STOP VEHICLE ALERT\n{'='*50}\n"
                    f"Time     : {now_str}\n"
                    f"Score    : {score:.0f}/100\n"
                    f"Duration : {elapsed:.0f}s\n"
                    f"Reason   : {reason}\n"
                    f"{'='*50}\n\n"
                    f"[LOC] LOCATION:\n"
                    f"   {loc.get('display','Unknown')}\n"
                    f"   {loc.get('maps_link','')}\n"
                    f"{rest_txt}\n"
                    f"Contact driver IMMEDIATELY!\n"
                    f"— Driver Safety System"
                )
                msg = MIMEMultipart()
                msg["From"]    = g["sender_email"]
                msg["To"]      = g["receiver_email"]
                msg["Subject"] = subject
                msg.attach(MIMEText(body, "plain"))
                with smtplib.SMTP_SSL("smtp.gmail.com", 465) as srv:
                    srv.login(g["sender_email"],
                              str(g["app_password"]).replace(" ",""))
                    srv.sendmail(g["sender_email"],
                                 g["receiver_email"], msg.as_string())
                print("[EMERGENCY] Email sent OK")
            except Exception as e:
                logger.error(f"[Email] {e}")

        # Telegram
        if self.emergency.telegram_enabled:
            try:
                import requests
                t = self.emergency.telegram_cfg
                msg = (
                    f"🚨 *STOP VEHICLE NOW!* 🚨\n\n"
                    f"⏰ *Time:* {now_str}\n"
                    f"😴 *Score:* `{score:.0f}/100`\n"
                    f"⏱️ *Duration:* `{elapsed:.0f}s`\n"
                    f"WARNING️ *Reason:* {reason}\n\n"
                    f"[LOC] *Location:*\n"
                    f"{loc.get('display','Unknown')}\n"
                    f"{loc.get('maps_link','')}"
                    f"{rest_tg}\n\n"
                    f"*Contact driver IMMEDIATELY!*"
                )
                resp = requests.post(
                    f"https://api.telegram.org/bot{t['bot_token']}/sendMessage",
                    data={
                        "chat_id":    str(t["chat_id"]),
                        "text":       msg,
                        "parse_mode": "Markdown",
                    },
                    timeout=10,
                )
                if resp.status_code == 200:
                    print("[EMERGENCY] Telegram sent OK")
                else:
                    print(f"[EMERGENCY TELEGRAM ERROR] {resp.text}")
            except Exception as e:
                logger.error(f"[Telegram] {e}")

    # ------------------------------------------------------------------
    def _prefetch_all(self):
        """Startup pe location + rest places dono fetch karo."""
        try:
            import requests
            resp = requests.get(
                "http://ip-api.com/json/", timeout=5,
                params={"fields": "city,regionName,country,lat,lon"},
            )
            if resp.status_code == 200:
                d   = resp.json()
                lat = d.get("lat", 0)
                lon = d.get("lon", 0)
                self._location = {
                    "city":     d.get("city",""),
                    "region":   d.get("regionName",""),
                    "country":  d.get("country",""),
                    "lat":      lat, "lon": lon,
                    "maps_link": f"https://www.google.com/maps?q={lat},{lon}",
                    "display":  f"{d.get('city','')}, {d.get('regionName','')}, {d.get('country','')}",
                }
                logger.info(f"[Location] {self._location['display']}")
                # Immediately fetch rest places
                self._fetch_rest_places()
        except Exception as e:
            logger.warning(f"[Prefetch] {e}")

    def _maybe_fetch_rest_places(self):
        if not self._fetching and not self._rest_places:
            self._fetching = True
            threading.Thread(target=self._fetch_rest_places, daemon=True).start()

    def _fetch_rest_places(self):
        try:
            import requests
            lat = self._location.get("lat", 0)
            lon = self._location.get("lon", 0)
            if lat == 0 and lon == 0:
                return

            query = f"""
[out:json][timeout:15];
(
  node["amenity"="fuel"](around:{SEARCH_RADIUS},{lat},{lon});
  node["amenity"="rest_area"](around:{SEARCH_RADIUS},{lat},{lon});
  node["amenity"="cafe"](around:{SEARCH_RADIUS},{lat},{lon});
  node["amenity"="restaurant"](around:{SEARCH_RADIUS},{lat},{lon});
  node["tourism"="hotel"](around:{SEARCH_RADIUS},{lat},{lon});
  node["highway"="services"](around:{SEARCH_RADIUS},{lat},{lon});
);
out body 20;
"""
            resp = requests.post(
                "https://overpass-api.de/api/interpreter",
                data={"data": query}, timeout=20,
            )
            if resp.status_code != 200:
                return

            places = []
            for el in resp.json().get("elements", []):
                tags  = el.get("tags", {})
                name  = (tags.get("name")
                         or tags.get("amenity","place").replace("_"," ").title())
                plat  = el.get("lat", 0)
                plon  = el.get("lon", 0)
                ptype = tags.get("amenity") or tags.get("tourism","place")
                dist  = _haversine(lat, lon, plat, plon)
                places.append(RestPlace(name, plat, plon, ptype, dist))

            places.sort(key=lambda p: p.distance_m)
            self._rest_places = places[:10]

            if self._rest_places:
                logger.info(f"[RestPlace] {len(self._rest_places)} places ready")
                print(f"\n[INFO] Rest places loaded ({len(self._rest_places)} nearby):")
                for i, p in enumerate(self._rest_places[:3], 1):
                    print(f"  {i}. {p.name} ({p.distance_str})")
            else:
                logger.info("[RestPlace] No places found in 5km")
        except Exception as e:
            logger.error(f"[RestPlace] {e}")
        finally:
            self._fetching = False


def _haversine(lat1, lon1, lat2, lon2) -> float:
    R = 6371000
    p = math.pi / 180
    a = (0.5 - math.cos((lat2-lat1)*p)/2
         + math.cos(lat1*p)*math.cos(lat2*p)
         *(1-math.cos((lon2-lon1)*p))/2)
    return 2 * R * math.asin(math.sqrt(a))