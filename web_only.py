"""
web_only.py
===========
Sirf history aur graphs dekhne ke liye — webcam ke bina.
Session khatam hone ke baad bhi chalao.

Run: python web_only.py
     python web_only.py --port 5001
"""

import argparse
import webbrowser
import time
import threading

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DriveGuard History Viewer")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    print("\n" + "="*50)
    print("  DriveGuard — History & Report Viewer")
    print("="*50)
    print(f"\n  Dashboard : http://127.0.0.1:{args.port}")
    print(f"  History   : http://127.0.0.1:{args.port}/history")
    print("\n  Ctrl+C to stop\n")

    from web.server import start_server
    start_server(port=args.port, keep_alive=True)

    if not args.no_browser:
        def _open():
            time.sleep(1.2)
            webbrowser.open(f"http://127.0.0.1:{args.port}/history")
        threading.Thread(target=_open, daemon=True).start()

    # Keep main thread alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[INFO] Server stopped.")