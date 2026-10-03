import threading
from datetime import datetime

from sources.location import get_location
from sources.filetree import get_filetree

LOCATION_INTERVAL = 10
FILETREE_INTERVAL = 30 # change this back to 3600

stop = threading.Event()
print_lock = threading.Lock()


def log(name, message):
    with print_lock:
        print(datetime.now().strftime("%Y-%m-%d %H:%M:%S"), f"{name}:", message)


def format_filetree(reading):
    return f"{len(reading['paths'])} paths under {reading['root']}"


SOURCES = [
    ("location", get_location, LOCATION_INTERVAL, lambda r: r),
    ("filetree", get_filetree, FILETREE_INTERVAL, format_filetree),
]


def poll(name, collect, interval, formatter):
    while not stop.is_set():
        try:
            log(name, formatter(collect()))
        except Exception as e:
            log(name, f"error: {e}")
        stop.wait(interval)


def main():
    threads = [
        threading.Thread(target=poll, args=args, name=args[0]) for args in SOURCES
    ]
    for t in threads:
        t.start()
    try:
        while not stop.wait(0.5):
            pass
    except KeyboardInterrupt:
        stop.set()
    for t in threads:
        t.join()


if __name__ == "__main__":
    main()
