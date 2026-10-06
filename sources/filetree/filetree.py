import sys

from ..errors import SourceError
from .src.mac import get_filetree_mac


def get_filetree() -> dict:
    if sys.platform == "darwin":
        return get_filetree_mac()
    raise SourceError("unsupported_platform", f"Unsupported platform: {sys.platform}")


if __name__ == "__main__":
    print(get_filetree())
