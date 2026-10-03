import sys

from .src.mac import get_location_mac


def get_location() -> dict:
    if sys.platform == "darwin":
        return get_location_mac()
    raise NotImplementedError(f"Unsupported platform: {sys.platform}")


if __name__ == "__main__":
    print(get_location())
