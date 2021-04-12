import pyvjoy
import threading
import time


class tController():


    def __init__(self, buttons : int, cmds: dict, holdtime, holdtime_long):
        if isinstance(buttons, int):
            self.buttons = ["0" for i in range(buttons)]
        else:
            raise typeError("buttons argument must be a number")
        if isinstance(cmds, dict):
            self.cmds = cmds
        else:
            raise typeError("cmdlist argument needs to be a list")

        self.timers = list(range(buttons))
        self.joy1 = pyvjoy.VJoyDevice(1)
        self.holdtime = holdtime
        self.holdtime_long = holdtime_long
        
        self.lock = threading.Lock()


    def update_joystick(self, idx, value):
        self.lock.acquire()
        
        self.buttons[idx] = str(value)
        # Copy buttons, reverse order and concatenate
        newstate = self.buttons.copy()
        newstate.reverse()
        newstate = "".join(newstate)

        # Convert the string binary representation into numeric value, set as new state
        self.joy1.data.lButtons = int(newstate, 2)
        self.joy1.update()
        
        self.lock.release()
                
                
    def press(self, cmd):
        try:
            idx = self.cmds[cmd]
        except KeyError:
            raise KeyError("Given command not listed.")
        else:
            if self.timers[idx] != idx:
                self.timers[idx].cancel()
                
            self.update_joystick(idx, 1)
            
            if len(cmd) == 1:
                holdtime = self.holdtime
            else:
                holdtime = self.holdtime_long
            self.timers[idx] = threading.Timer(holdtime, self.release, args=(cmd,))
            self.timers[idx].start()


    def release(self, cmd):
        try:
            idx = self.cmds[cmd]
            self.update_joystick(idx, 0)
        except KeyError:
            raise KeyError("Given command not listed.")


    def reset(self):
        "tController:  Doing controller reset...."
        for command in self.cmds.keys():
            self.release(command)
