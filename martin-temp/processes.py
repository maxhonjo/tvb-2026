import time
import psutil
import win32gui
import win32process
import threading
import json

class ProcessLog():
    def __init__(self):
        self.current_process = None
        self.buffer = []

    def _current(self):
        hwnd = win32gui.GetForegroundWindow()

        if not hwnd:
            return None

        _, pid = win32process.GetWindowThreadProcessId(hwnd)

        try:
            name = psutil.Process(pid).name()
        except psutil.Error:
            name = f"<pid {pid}"

        return name, win32gui.GetWindowText(hwnd)   
    
    def _loop(self):

        last_process = None

        while self.running:
            active = self._current()

            if active is None:
                time.sleep(0.1)
                continue

            if active[0] != last_process:
                last_process = active[0]
            
                self.buffer.append({
                "tstamp": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time())),
                "process": active[0],
                "title": [],
                })      

            titles = self.buffer[-1]["title"]
            if not titles or titles[-1] != active[1]:
                titles.append(active[1])

            time.sleep(0.1)

    def start(self):
        self.running = True
        self.thread = threading.Thread(target = self._loop, daemon = True)
        self.thread.start()

    def stop(self):
        self.running = False 
        self.thread.join()
    
    def drain(self):
        temp, self.buffer = self.buffer, []
        return temp

# log1 = ProcessLog()
# log1.start()
# time.sleep(10)
# log1.stop()
# data = log1.drain()