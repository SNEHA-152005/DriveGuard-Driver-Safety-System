"""
debug_emergency.py
===================
Emergency alert system ko seedha test karo — main.py ke bina.
Yeh script chalao aur output copy karke batao.

Run: python debug_emergency.py
"""

import yaml
import sys

print("=" * 55)
print("  EMERGENCY ALERT DEBUG SCRIPT")
print("=" * 55)

# ── Step 1: Config load ───────────────────────────────────────────────
print("\n[1] Loading config.yaml...")
try:
    with open("config.yaml") as f:
        cfg = yaml.safe_load(f)
    em = cfg.get("emergency", {})
    print(f"    emergency.enabled                  = {em.get('enabled')}")
    print(f"    emergency.critical_fatigue_threshold= {em.get('critical_fatigue_threshold')}")
    print(f"    emergency.cooldown_minutes          = {em.get('cooldown_minutes')}")
    print(f"    gmail.enabled                      = {em.get('gmail',{}).get('enabled')}")
    print(f"    gmail.sender_email                 = {em.get('gmail',{}).get('sender_email')}")
    print(f"    gmail.receiver_email               = {em.get('gmail',{}).get('receiver_email')}")
    app_pw = em.get('gmail',{}).get('app_password','')
    print(f"    gmail.app_password length          = {len(str(app_pw).replace(' ',''))} chars")
    print(f"    telegram.enabled                   = {em.get('telegram',{}).get('enabled')}")
    print(f"    telegram.bot_token length          = {len(str(em.get('telegram',{}).get('bot_token','')))} chars")
    print(f"    telegram.chat_id                   = {em.get('telegram',{}).get('chat_id')}")
except Exception as e:
    print(f"    ERROR loading config: {e}")
    sys.exit(1)

# ── Step 2: IP Location ───────────────────────────────────────────────
print("\n[2] Testing IP location fetch...")
try:
    import requests
    resp = requests.get(
        "http://ip-api.com/json/",
        timeout=5,
        params={"fields": "city,regionName,country,lat,lon,query"}
    )
    if resp.status_code == 200:
        d = resp.json()
        print(f"    City    : {d.get('city')}")
        print(f"    Region  : {d.get('regionName')}")
        print(f"    Country : {d.get('country')}")
        print(f"    Lat/Lon : {d.get('lat')}, {d.get('lon')}")
        lat, lon = d.get('lat', 0), d.get('lon', 0)
        print(f"    Maps    : https://www.google.com/maps?q={lat},{lon}")
    else:
        print(f"    ERROR: status {resp.status_code}")
        lat, lon = 28.6, 77.2
except Exception as e:
    print(f"    ERROR: {e}")
    lat, lon = 28.6, 77.2

# ── Step 3: OSM Rest Places ───────────────────────────────────────────
print(f"\n[3] Testing OpenStreetMap rest places near ({lat}, {lon})...")
try:
    import requests, math

    query = f"""
[out:json][timeout:15];
(
  node["amenity"="fuel"](around:5000,{lat},{lon});
  node["amenity"="rest_area"](around:5000,{lat},{lon});
  node["amenity"="cafe"](around:5000,{lat},{lon});
  node["amenity"="restaurant"](around:5000,{lat},{lon});
  node["tourism"="hotel"](around:5000,{lat},{lon});
);
out body 10;
"""
    resp = requests.post(
        "https://overpass-api.de/api/interpreter",
        data={"data": query},
        timeout=20,
    )
    if resp.status_code == 200:
        elements = resp.json().get("elements", [])
        print(f"    Found {len(elements)} places")

        def haversine(la1,lo1,la2,lo2):
            R=6371000; p=math.pi/180
            a=(0.5-math.cos((la2-la1)*p)/2
               +math.cos(la1*p)*math.cos(la2*p)
               *(1-math.cos((lo2-lo1)*p))/2)
            return 2*R*math.asin(math.sqrt(a))

        places = []
        for el in elements:
            tags = el.get("tags", {})
            name = tags.get("name") or tags.get("amenity","place").title()
            plat, plon = el.get("lat",0), el.get("lon",0)
            dist = haversine(lat, lon, plat, plon)
            places.append((dist, name, plat, plon))
        places.sort()
        for dist, name, plat, plon in places[:3]:
            km = f"{dist/1000:.1f}km" if dist >= 1000 else f"{dist:.0f}m"
            print(f"    • {name} ({km}) — https://maps.google.com?q={plat},{plon}")
    else:
        print(f"    ERROR: OSM status {resp.status_code}")
except Exception as e:
    print(f"    ERROR: {e}")

# ── Step 4: Gmail test ────────────────────────────────────────────────
print("\n[4] Testing Gmail...")
g = em.get("gmail", {})
if not g.get("enabled"):
    print("    SKIPPED — gmail.enabled is false")
else:
    try:
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart

        sender   = g["sender_email"]
        password = str(g["app_password"]).replace(" ", "")
        receiver = g["receiver_email"]

        print(f"    Connecting to smtp.gmail.com:465...")
        msg = MIMEMultipart()
        msg["From"]    = sender
        msg["To"]      = receiver
        msg["Subject"] = "🚨 Driver Safety — TEST ALERT"
        msg.attach(MIMEText(
            "Yeh ek test email hai Driver Safety System se.\n"
            "Agar yeh aaya hai to Gmail alert sahi kaam kar raha hai! ✅\n\n"
            f"Location test: https://www.google.com/maps?q={lat},{lon}",
            "plain"
        ))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as srv:
            srv.login(sender, password)
            srv.sendmail(sender, receiver, msg.as_string())

        print(f"    ✅ EMAIL SENT to {receiver}!")
        print(f"    Check your inbox now.")

    except smtplib.SMTPAuthenticationError:
        print("    ❌ AUTH ERROR — App Password galat hai!")
        print("    Fix: Google Account → Security → App Passwords")
        print("    Make sure 2-Step Verification is ON")
    except smtplib.SMTPException as e:
        print(f"    ❌ SMTP ERROR: {e}")
    except KeyError as e:
        print(f"    ❌ CONFIG MISSING: {e} not found in config.yaml")
    except Exception as e:
        print(f"    ❌ ERROR: {e}")

# ── Step 5: Telegram test ─────────────────────────────────────────────
print("\n[5] Testing Telegram...")
t = em.get("telegram", {})
if not t.get("enabled"):
    print("    SKIPPED — telegram.enabled is false")
else:
    try:
        import requests
        token   = str(t["bot_token"])
        chat_id = str(t["chat_id"])

        # First check bot info
        info_resp = requests.get(
            f"https://api.telegram.org/bot{token}/getMe",
            timeout=10
        )
        if info_resp.status_code == 200:
            bot = info_resp.json().get("result", {})
            print(f"    Bot name : @{bot.get('username')}")
        else:
            print(f"    ❌ Bot token invalid! Status: {info_resp.status_code}")
            print(f"    Response: {info_resp.text[:200]}")

        # Send test message
        msg_resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data={
                "chat_id":    chat_id,
                "text": (
                    "🚨 *Driver Safety — TEST ALERT*\n\n"
                    "Yeh ek test message hai.\n"
                    "Agar aaya hai to Telegram alert kaam kar raha hai! ✅\n\n"
                    f"📍 Location test:\n"
                    f"https://www.google.com/maps?q={lat},{lon}"
                ),
                "parse_mode": "Markdown",
            },
            timeout=10
        )
        if msg_resp.status_code == 200:
            print(f"    ✅ TELEGRAM SENT to chat_id: {chat_id}!")
            print(f"    Check your Telegram now.")
        else:
            print(f"    ❌ FAILED: {msg_resp.text}")
            if "chat not found" in msg_resp.text:
                print("    FIX: Bot ko START karo — Telegram mein apne bot pe /start bhejo")
            if "Unauthorized" in msg_resp.text:
                print("    FIX: bot_token galat hai — BotFather se dobara copy karo")

    except KeyError as e:
        print(f"    ❌ CONFIG MISSING: {e}")
    except Exception as e:
        print(f"    ❌ ERROR: {e}")

print("\n" + "=" * 55)
print("  DEBUG COMPLETE — Output copy karke batao")
print("=" * 55)