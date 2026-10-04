import json
import subprocess
from pathlib import Path

BINARY = Path(__file__).parent / "get-location-mac.app" / "Contents" / "MacOS" / "get-location-mac"


def get_location_mac() -> dict:
    result = subprocess.run([str(BINARY)], capture_output=True, text=True, check=True)
    return json.loads(result.stdout)
