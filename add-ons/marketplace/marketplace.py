"""Boku data marketplace (prototype).

A local web app where a person opts in which of their data to sell, sees a
mock market value that rises as they share more (and more sensitive) data, and
browses data bounties posted by companies. Everything here is mock: no real
Boku data is read, nothing is written, nothing leaves the machine.

Run:
    uv run python add-ons/marketplace/marketplace.py

Then open http://127.0.0.1:8777 (opens automatically).
"""

import http.server
import json
import socketserver
import webbrowser
from pathlib import Path

HOST = "127.0.0.1"
PORT = 8777
HERE = Path(__file__).resolve().parent

# The signed-in person, for the demo. A real app would verify these.
USER = {
    "name": "Max",
    "verified": ["ie-student"],  # badges the user already holds
}

# Data types the user can opt into selling. value_usd is a mock monthly price
# per user (realistic: fractions of a dollar; only the most sensitive data
# clears 50c). users is a mock count of people opted into that type.
# `prod_disabled` types are shown but flagged as not active in production.
DATA_TYPES = [
    {
        "id": "location",
        "label": "Location",
        "blurb": "Where your devices go, through the day.",
        "value_usd": 0.12,
        "users": 8420,
    },
    {
        "id": "app_activity",
        "label": "App activity",
        "blurb": "Which apps you open, switch to and close.",
        "value_usd": 0.06,
        "users": 6150,
    },
    {
        "id": "filetree",
        "label": "File tree",
        "blurb": "The names and shape of files on your devices.",
        "value_usd": 0.02,
        "users": 2310,
    },
    {
        "id": "browsing",
        "label": "Browsing history",
        "blurb": "Sites you visit and searches you run.",
        "value_usd": 0.18,
        "users": 4980,
    },
    {
        "id": "contacts",
        "label": "Contacts",
        "blurb": "Your address book and who you talk to.",
        "value_usd": 0.05,
        "users": 3760,
    },
    {
        "id": "health",
        "label": "Health & fitness",
        "blurb": "Steps, heart rate, sleep and workouts.",
        "value_usd": 0.60,
        "users": 1540,
    },
    {
        "id": "keystrokes",
        "label": "Keystrokes (keylogging)",
        "blurb": "Everything you type, as you type it.",
        "value_usd": 0.95,
        "users": 210,
        "prod_disabled": True,
    },
]

# Data bounties posted by companies. `requires_verified` matches USER.verified.
BOUNTIES = [
    {
        "id": "ie-location",
        "company": "IE University",
        "reward_usd": 5,
        "title": "$5 promo for IE students",
        "ask": "Share location data and verify as an IE student.",
        "needs": ["location"],
        "requires_verified": "ie-student",
    },
    {
        "id": "fit-health",
        "company": "PulseFit",
        "reward_usd": 8,
        "title": "$8 for 30 days of health data",
        "ask": "Share health & fitness data to train our coaching model.",
        "needs": ["health"],
    },
]


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(HERE), **kwargs)

    def do_GET(self):
        if self.path.split("?")[0] == "/api/catalog":
            self._send_json(
                {"user": USER, "data_types": DATA_TYPES, "bounties": BOUNTIES}
            )
            return
        if self.path in ("/", ""):
            self.path = "/marketplace.html"
        elif self.path.split("?")[0] == "/overview":
            self.path = "/overview.html"
        super().do_GET()

    def _send_json(self, obj):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass  # quiet


def main():
    with socketserver.TCPServer((HOST, PORT), Handler) as httpd:
        url = f"http://{HOST}:{PORT}"
        print(f"Boku marketplace (prototype) — {url}")
        print("All data is mock. Ctrl-C to stop.")
        try:
            webbrowser.open(url)
        except Exception:
            pass
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nstopped.")


if __name__ == "__main__":
    main()
