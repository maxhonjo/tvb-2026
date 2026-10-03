import json
import subprocess
from pathlib import Path

SRC_DIR = Path(__file__).parent


def get_location_mac() -> dict:
    binary = SRC_DIR / "GetLocationMac.app" / "Contents" / "MacOS" / "get-location-mac"
    result = subprocess.run([str(binary)], capture_output=True, text=True, check=True)
    return json.loads(result.stdout)
