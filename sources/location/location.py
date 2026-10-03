import sys

from .src.mac import get_location_mac
from .src.windows import get_location_windows


def get_location() -> dict:
    if sys.platform == "darwin":
        return get_location_mac()
    elif sys.platform == "win32":
        return get_location_windows()
    raise NotImplementedError(f"Unsupported platform: {sys.platform}")


if __name__ == "__main__":
    print(get_location())
