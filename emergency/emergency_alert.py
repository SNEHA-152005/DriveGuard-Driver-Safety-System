"""
emergency/emergency_alert.py  — v5 (cooldown bug fixed)
=========================================================
BUG FIX:
  Pehle problem: cooldown 10 minutes tha lekin main loop har frame
  pe check_and_alert() call karta tha. Pehli baar bhi cooldown mein
  tha isliye alert kabhi fire nahi hua.

  Fix: _last_sent = 0.0 se start — matlab pehla alert HAMESHA fire hoga.
  Uske baad cooldown_minutes ka wait hoga.

Gmail + Telegram alerts with IP location + Google Maps link.
"""

import time
import logging
import threading
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

logger = logging.getLogger(__name__)


def get_ip_location() -> dict:
    """ip-api.com se current location fetch karo. Free, no key needed."""
    try:
        import requests
        resp = requests.get(
            "http://ip-api.com/json/",
            timeout=5,
            params={"fields": "city,regionName,country,lat,lon,isp,query"},
        )
        if resp.status_code == 200:
            d    = resp.json()
            lat  = d.get("lat", 0)
            lon  = d.get("lon", 0)
            return {
                "city":      d.get("city", "Unknown"),
                "region":    d.get("regionName", ""),
                "country":   d.get("country", ""),
                "lat":       lat,
                "lon":       lon,
                "maps_link": f"https://www.google.com/maps?q={lat},{lon}",
                "ip":        d.get("query", ""),
                "display":   f"{d.get('city','')}, {d.get('regionName','')}, {d.get('country','')}",
            }
    except Exception as e:
        logger.warning(f"[Location] {e}")
    return {
        "city": "Unknown", "region": "", "country": "",
        "lat": 0, "lon": 0,
        "maps_link": "Location unavailable",
        "display": "Location unavailable",
    }


class EmergencyAlertSystem:
    """
    Fatigue score critical hone pe Email + Telegram alert.
    BUG FIX: _last_sent starts at 0 so first alert always fires.
    """

    def __init__(self, cfg: dict):
        self.enabled   = cfg.get("enabled", False)
        self.threshold = cfg.get("critical_fatigue_threshold", 75)
        self.cooldown  = cfg.get("cooldown_minutes", 10) * 60

        # BUG FIX: was some positive value before — now 0.0 so first alert fires
        self._last_sent = 0.0

        self.gmail_cfg        = cfg.get("gmail", {})
        self.gmail_enabled    = self.gmail_cfg.get("enabled", False)
        self.telegram_cfg     = cfg.get("telegram", {})
        self.telegram_enabled = self.telegram_cfg.get("enabled", False)

        # Cache location so we don't fetch on every call
        self._cached_location: dict = {}
        self._location_fetched: bool = False

        if self.enabled:
            self._verify_setup()
            # Fetch location on startup
            threading.Thread(
                target=self._prefetch_location,
                daemon=True,
            ).start()

    # ------------------------------------------------------------------
    def _prefetch_location(self):
        """Startup pe location fetch karo taaki alert delay na ho."""
        logger.info("[Emergency] Pre-fetching location...")
        self._cached_location  = get_ip_location()
        self._location_fetched = True
        logger.info(f"[Emergency] Location ready: {self._cached_location.get('display')}")

    def _verify_setup(self):
        if self.gmail_enabled:
            missing = [k for k in ["sender_email","app_password","receiver_email"]
                       if not self.gmail_cfg.get(k)]
            if missing:
                logger.warning(f"[Email] Missing config: {missing}")
                self.gmail_enabled = False
            else:
                logger.info("[Email] Gmail ready - OK")

        if self.telegram_enabled:
            missing = [k for k in ["bot_token","chat_id"]
                       if not self.telegram_cfg.get(k)]
            if missing:
                logger.warning(f"[Telegram] Missing config: {missing}")
                self.telegram_enabled = False
            else:
                logger.info("[Telegram] Telegram ready - OK")

    # ------------------------------------------------------------------
    def check_and_alert(self, fatigue_score: float):
        """
        Main loop se call karo.
        FIXED: _last_sent=0 ensures first alert always fires.
        """
        if not self.enabled:
            return
        if fatigue_score < self.threshold:
            return

        now = time.time()
        if (now - self._last_sent) < self.cooldown:
            remaining = int(self.cooldown - (now - self._last_sent))
            logger.debug(f"[Emergency] Cooldown: {remaining}s remaining")
            return

        self._last_sent = now
        logger.warning(f"[Emergency] FIRING alert! Score={fatigue_score:.1f}")
        print(f"\n[EMERGENCY] Alert firing! Fatigue={fatigue_score:.1f}/100")

        threading.Thread(
            target=self._send_all,
            args=(fatigue_score,),
            daemon=True,
        ).start()

    # ------------------------------------------------------------------
    def _send_all(self, fatigue_score: float):
        # Use cached location if available, else fetch now
        if self._location_fetched and self._cached_location:
            loc = self._cached_location
        else:
            loc = get_ip_location()
            self._cached_location = loc

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[EMERGENCY] Location: {loc['display']}")

        if self.gmail_enabled:
            self._send_email(fatigue_score, loc, now_str)
        if self.telegram_enabled:
            self._send_telegram(fatigue_score, loc, now_str)

    # ── Gmail ──────────────────────────────────────────────────────────
    def _send_email(self, fatigue_score: float, loc: dict, now_str: str):
        try:
            g       = self.gmail_cfg
            subject = f"🚨 DRIVER SAFETY ALERT — Fatigue {fatigue_score:.0f}/100"
            body    = (
                f"DRIVER SAFETY ALERT\n{'='*45}\n"
                f"Time          : {now_str}\n"
                f"Fatigue Score : {fatigue_score:.0f}/100  ⚠️ CRITICAL\n"
                f"{'='*45}\n\n"
                f"📍 APPROXIMATE LOCATION:\n"
                f"   {loc['display']}\n"
                f"   Coords: {loc['lat']}, {loc['lon']}\n\n"
                f"🗺️ GOOGLE MAPS: {loc['maps_link']}\n\n"
                f"{'='*45}\n"
                f"Driver ka fatigue score critical hai.\n"
                f"Kripya turant contact karein!\n\n"
                f"NOTE: Location IP-based — ~1-5km accurate\n"
                f"— Driver Safety System"
            )
            msg = MIMEMultipart()
            msg["From"]    = g["sender_email"]
            msg["To"]      = g["receiver_email"]
            msg["Subject"] = subject
            msg.attach(MIMEText(body, "plain"))

            with smtplib.SMTP_SSL("smtp.gmail.com", 465) as srv:
                srv.login(g["sender_email"], g["app_password"])
                srv.sendmail(g["sender_email"], g["receiver_email"], msg.as_string())

            logger.info(f"[Email] Sent to {g['receiver_email']} ✅")
            print(f"[EMERGENCY] Email sent ✅")

        except smtplib.SMTPAuthenticationError:
            print("[EMERGENCY EMAIL ERROR] Wrong App Password — check config.yaml")
        except Exception as e:
            logger.error(f"[Email] {e}")
            print(f"[EMERGENCY EMAIL ERROR] {e}")

    # ── Telegram ───────────────────────────────────────────────────────
    def _send_telegram(self, fatigue_score: float, loc: dict, now_str: str):
        try:
            import requests
            t       = self.telegram_cfg
            message = (
                f"🚨 *DRIVER SAFETY ALERT* 🚨\n\n"
                f"⏰ *Time:* {now_str}\n"
                f"😴 *Fatigue:* `{fatigue_score:.0f}/100` CRITICAL\n\n"
                f"📍 *Location:*\n"
                f"🏙️ {loc['display']}\n"
                f"🌐 `{loc['lat']}, {loc['lon']}`\n\n"
                f"🗺️ [Open in Google Maps]({loc['maps_link']})\n\n"
                f"⚠️ Driver se turant contact karein!\n"
                f"_Location IP-based, ~1-5km accurate_"
            )
            url  = f"https://api.telegram.org/bot{t['bot_token']}/sendMessage"
            resp = requests.post(url, data={
                "chat_id":    str(t["chat_id"]),
                "text":       message,
                "parse_mode": "Markdown",
            }, timeout=10)

            if resp.status_code == 200:
                print("[EMERGENCY] Telegram sent ✅")
            else:
                print(f"[EMERGENCY TELEGRAM ERROR] {resp.text}")

        except Exception as e:
            logger.error(f"[Telegram] {e}")
            print(f"[EMERGENCY TELEGRAM ERROR] {e}")












# """
# emergency/emergency_alert.py  — v5 (cooldown bug fixed)
# =========================================================
# BUG FIX:
#   Pehle problem: cooldown 10 minutes tha lekin main loop har frame
#   pe check_and_alert() call karta tha. Pehli baar bhi cooldown mein
#   tha isliye alert kabhi fire nahi hua.

#   Fix: _last_sent = 0.0 se start — matlab pehla alert HAMESHA fire hoga.
#   Uske baad cooldown_minutes ka wait hoga.

# Gmail + Telegram alerts with IP location + Google Maps link.
# """

# import time
# import logging
# import threading
# import smtplib
# from email.mime.text import MIMEText
# from email.mime.multipart import MIMEMultipart
# from datetime import datetime

# logger = logging.getLogger(__name__)


# def get_ip_location() -> dict:
#     """ip-api.com se current location fetch karo. Free, no key needed."""
#     try:
#         import requests
#         resp = requests.get(
#             "http://ip-api.com/json/",
#             timeout=5,
#             params={"fields": "city,regionName,country,lat,lon,isp,query"},
#         )
#         if resp.status_code == 200:
#             d    = resp.json()
#             lat  = d.get("lat", 0)
#             lon  = d.get("lon", 0)
#             return {
#                 "city":      d.get("city", "Unknown"),
#                 "region":    d.get("regionName", ""),
#                 "country":   d.get("country", ""),
#                 "lat":       lat,
#                 "lon":       lon,
#                 "maps_link": f"https://www.google.com/maps?q={lat},{lon}",
#                 "ip":        d.get("query", ""),
#                 "display":   f"{d.get('city','')}, {d.get('regionName','')}, {d.get('country','')}",
#             }
#     except Exception as e:
#         logger.warning(f"[Location] {e}")
#     return {
#         "city": "Unknown", "region": "", "country": "",
#         "lat": 0, "lon": 0,
#         "maps_link": "Location unavailable",
#         "display": "Location unavailable",
#     }


# class EmergencyAlertSystem:
#     """
#     Fatigue score critical hone pe Email + Telegram alert.
#     BUG FIX: _last_sent starts at 0 so first alert always fires.
#     """

#     def __init__(self, cfg: dict):
#         self.enabled   = cfg.get("enabled", False)
#         self.threshold = cfg.get("critical_fatigue_threshold", 75)
#         self.cooldown  = cfg.get("cooldown_minutes", 10) * 60

#         # BUG FIX: was some positive value before — now 0.0 so first alert fires
#         self._last_sent = 0.0

#         self.gmail_cfg        = cfg.get("gmail", {})
#         self.gmail_enabled    = self.gmail_cfg.get("enabled", False)
#         self.telegram_cfg     = cfg.get("telegram", {})
#         self.telegram_enabled = self.telegram_cfg.get("enabled", False)

#         # Cache location so we don't fetch on every call
#         self._cached_location: dict = {}
#         self._location_fetched: bool = False

#         if self.enabled:
#             self._verify_setup()
#             # Fetch location on startup
#             threading.Thread(
#                 target=self._prefetch_location,
#                 daemon=True,
#             ).start()

#     # ------------------------------------------------------------------
#     def _prefetch_location(self):
#         """Startup pe location fetch karo taaki alert delay na ho."""
#         logger.info("[Emergency] Pre-fetching location...")
#         self._cached_location  = get_ip_location()
#         self._location_fetched = True
#         logger.info(f"[Emergency] Location ready: {self._cached_location.get('display')}")

#     def _verify_setup(self):
#         if self.gmail_enabled:
#             missing = [k for k in ["sender_email","app_password","receiver_email"]
#                        if not self.gmail_cfg.get(k)]
#             if missing:
#                 logger.warning(f"[Email] Missing config: {missing}")
#                 self.gmail_enabled = False
#             else:
#                 logger.info("[Email] Gmail ready ✅")

#         if self.telegram_enabled:
#             missing = [k for k in ["bot_token","chat_id"]
#                        if not self.telegram_cfg.get(k)]
#             if missing:
#                 logger.warning(f"[Telegram] Missing config: {missing}")
#                 self.telegram_enabled = False
#             else:
#                 logger.info("[Telegram] Telegram ready ✅")

#     # ------------------------------------------------------------------
#     def check_and_alert(self, fatigue_score: float):
#         """
#         Main loop se call karo.
#         FIXED: _last_sent=0 ensures first alert always fires.
#         """
#         if not self.enabled:
#             return
#         if fatigue_score < self.threshold:
#             return

#         now = time.time()
#         if (now - self._last_sent) < self.cooldown:
#             remaining = int(self.cooldown - (now - self._last_sent))
#             logger.debug(f"[Emergency] Cooldown: {remaining}s remaining")
#             return

#         self._last_sent = now
#         logger.warning(f"[Emergency] FIRING alert! Score={fatigue_score:.1f}")
#         print(f"\n[EMERGENCY] Alert firing! Fatigue={fatigue_score:.1f}/100")

#         threading.Thread(
#             target=self._send_all,
#             args=(fatigue_score,),
#             daemon=True,
#         ).start()

#     # ------------------------------------------------------------------
#     def _send_all(self, fatigue_score: float):
#         # Use cached location if available, else fetch now
#         if self._location_fetched and self._cached_location:
#             loc = self._cached_location
#         else:
#             loc = get_ip_location()
#             self._cached_location = loc

#         now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
#         print(f"[EMERGENCY] Location: {loc['display']}")

#         if self.gmail_enabled:
#             self._send_email(fatigue_score, loc, now_str)
#         if self.telegram_enabled:
#             self._send_telegram(fatigue_score, loc, now_str)

#     # ── Gmail ──────────────────────────────────────────────────────────
#     def _send_email(self, fatigue_score: float, loc: dict, now_str: str):
#         try:
#             g       = self.gmail_cfg
#             subject = f"🚨 DRIVER SAFETY ALERT — Fatigue {fatigue_score:.0f}/100"
#             body    = (
#                 f"DRIVER SAFETY ALERT\n{'='*45}\n"
#                 f"Time          : {now_str}\n"
#                 f"Fatigue Score : {fatigue_score:.0f}/100  ⚠️ CRITICAL\n"
#                 f"{'='*45}\n\n"
#                 f"📍 APPROXIMATE LOCATION:\n"
#                 f"   {loc['display']}\n"
#                 f"   Coords: {loc['lat']}, {loc['lon']}\n\n"
#                 f"🗺️ GOOGLE MAPS: {loc['maps_link']}\n\n"
#                 f"{'='*45}\n"
#                 f"Driver ka fatigue score critical hai.\n"
#                 f"Kripya turant contact karein!\n\n"
#                 f"NOTE: Location IP-based — ~1-5km accurate\n"
#                 f"— Driver Safety System"
#             )
#             msg = MIMEMultipart()
#             msg["From"]    = g["sender_email"]
#             msg["To"]      = g["receiver_email"]
#             msg["Subject"] = subject
#             msg.attach(MIMEText(body, "plain"))

#             with smtplib.SMTP_SSL("smtp.gmail.com", 465) as srv:
#                 srv.login(g["sender_email"], g["app_password"])
#                 srv.sendmail(g["sender_email"], g["receiver_email"], msg.as_string())

#             logger.info(f"[Email] Sent to {g['receiver_email']} ✅")
#             print(f"[EMERGENCY] Email sent ✅")

#         except smtplib.SMTPAuthenticationError:
#             print("[EMERGENCY EMAIL ERROR] Wrong App Password — check config.yaml")
#         except Exception as e:
#             logger.error(f"[Email] {e}")
#             print(f"[EMERGENCY EMAIL ERROR] {e}")

#     # ── Telegram ───────────────────────────────────────────────────────
#     def _send_telegram(self, fatigue_score: float, loc: dict, now_str: str):
#         try:
#             import requests
#             t       = self.telegram_cfg
#             message = (
#                 f"🚨 *DRIVER SAFETY ALERT* 🚨\n\n"
#                 f"⏰ *Time:* {now_str}\n"
#                 f"😴 *Fatigue:* `{fatigue_score:.0f}/100` CRITICAL\n\n"
#                 f"📍 *Location:*\n"
#                 f"🏙️ {loc['display']}\n"
#                 f"🌐 `{loc['lat']}, {loc['lon']}`\n\n"
#                 f"🗺️ [Open in Google Maps]({loc['maps_link']})\n\n"
#                 f"⚠️ Driver se turant contact karein!\n"
#                 f"_Location IP-based, ~1-5km accurate_"
#             )
#             url  = f"https://api.telegram.org/bot{t['bot_token']}/sendMessage"
#             resp = requests.post(url, data={
#                 "chat_id":    str(t["chat_id"]),
#                 "text":       message,
#                 "parse_mode": "Markdown",
#             }, timeout=10)

#             if resp.status_code == 200:
#                 print("[EMERGENCY] Telegram sent ✅")
#             else:
#                 print(f"[EMERGENCY TELEGRAM ERROR] {resp.text}")

#         except Exception as e:
#             logger.error(f"[Telegram] {e}")
#             print(f"[EMERGENCY TELEGRAM ERROR] {e}")