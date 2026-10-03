import sys

from .src.mac import get_filetree_mac


def get_filetree() -> dict:
    if sys.platform == "darwin":
        return get_filetree_mac()
    raise NotImplementedError(f"Unsupported platform: {sys.platform}")


if __name__ == "__main__":
    print(get_filetree())
