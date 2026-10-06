import json
import subprocess
from pathlib import Path

from ...errors import SourceError

BINARY = Path(__file__).parent / "get-location-mac.app" / "Contents" / "MacOS" / "get-location-mac"


def get_location_mac() -> dict:
    try:
        result = subprocess.run([str(BINARY)], capture_output=True, text=True, check=True)
    except FileNotFoundError:
        raise SourceError("unavailable", f"helper not found: {BINARY}")
    except subprocess.CalledProcessError as e:
        # The helper reports the cause (denied permission, no fix) on stderr.
        raise SourceError("unavailable", e.stderr.strip() or f"helper exited with {e.returncode}")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        raise SourceError("internal", "helper returned invalid JSON")
