import time
import threading


class filewriter(threading.Thread):
    
    def __init__(self, file, mode):
        threading.Thread.__init__(self)
        self.filename = file
        self.file = ""
        self.mode = mode
        self.close = False
        self.condition = threading.Condition()
        self.data = []


    def run(self):
        if self.mode != "r":
            try:
                self.file = open(self.filename, self.mode, encoding="utf-8")
            except FileNotFoundError:
                print(f"Error -  File \"{self.filename}\" not found.\nExiting.")
                return
        else:
            print("Read only mode given, exiting.")
        
        while not self.close:
            with self.condition:
                while not self.data:
                    if self.close:
                        break
                    self.condition.wait()
                if type != "a":
                    if self.data:
                        self.file.write(self.data.pop())
                        self.data = []
                else:                
                    while self.data:
                        self.file.write(self.data.pop(0))
            self.file.flush()
        self.file.close()


    def clear(self):
        with self.condition:
            self.file.seek(0)
            self.file.truncate()
            self.data = []
        
    
    def queue(self, data):
        if not self.close:
            with self.condition:
                self.data.append(data)
                self.condition.notify()
        else:
            print("File already closing")
            

    def closefile(self):
        self.close = True
        with self.condition:
            self.condition.notify()
    
