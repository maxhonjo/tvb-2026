import json
import subprocess
import sys
from pathlib import Path

MODULE_DIR = Path(__file__).parent


def get_location_mac() -> dict:
    binary = MODULE_DIR / "GetLocationMac.app" / "Contents" / "MacOS" / "get-location-mac"
    result = subprocess.run([str(binary)], capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def get_location_windows() -> dict:
    raise NotImplementedError("Windows location helper not implemented yet")


def get_location() -> dict:
    if sys.platform == "darwin":
        return get_location_mac()
    elif sys.platform == "win32":
        return get_location_windows()
    raise NotImplementedError(f"Unsupported platform: {sys.platform}")


if __name__ == "__main__":
    print(get_location())
