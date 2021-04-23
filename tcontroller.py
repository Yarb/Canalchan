import pyvjoy
import threading
import time

READY = 1
EXEC_UNTIL_EMPTY = 2

class tController(threading.Thread):

    
    def __init__(self, buttons : int, cmds: dict, holdtime, holdtime_long):
        if isinstance(buttons, int):
            self.buttons = ["0" for i in range(buttons)]
        else:
            raise typeError("buttons argument must be a number")
        if isinstance(cmds, dict):
            self.cmds = cmds
        else:
            raise typeError("cmdlist argument needs to be a list")
        
        threading.Thread.__init__(self)
        self.timers = list(range(buttons))
        self.joy1 = pyvjoy.VJoyDevice(1)
        self.holdtime = holdtime
        self.holdtime_long = holdtime_long
        
        self.lock = threading.Lock()
        self.condition = threading.Condition()
        
        self.status = EXEC_UNTIL_EMPTY
        self.sequence_exec = False
        self.sequences = []
        self.queue = []



    def __update_joystick(self, idx, value):
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
                

    def run(self):
        """Main loop"""
        
        execute = 0
        while(True):
            # Check status and if necessary wait for commands from queue/sequence
            with self.condition:
                if self.status == READY:
                    self.status = EXEC_UNTIL_EMPTY
                    execute = 1
                else:
                    self.condition.wait()
            
            # If execute is set, there should be data. Check and execute
            if execute:
                execute = 0
                # Always ensure that queued commands are executed first.
                while self.queue:
                    cmd = self.queue.pop(0)
                    self.__button_press(cmd)
            
                # Check if we need to execute sequences.
                if self.sequence_exec:
                    while self.sequences:
                        seq = self.sequences.pop(0)
                        for cmd in seq:
                            self.__ordered_button_press(cmd)
            
                
    def __button_press(self, cmd):
        """Presses the button matching the given command.
        Will launch a timer thread to automatically release the button.
        """
    
        if self.__press(cmd):
            idx = self.cmds[cmd]
            if len(cmd) == 1:
                holdtime = self.holdtime
            else:
                holdtime = self.holdtime_long
            self.timers[idx] = threading.Timer(holdtime, self.__release, args=(cmd,))
            self.timers[idx].start()


    def __ordered_button_press(self, cmd):
        """Executes one complete buttonpress. 
        This blocks until the press/release action is completed.
        Intended for ensuring the order of execution"""
        
        if self.__press(cmd):
            if len(cmd) == 1:
                holdtime = self.holdtime
            else:
                holdtime = self.holdtime_long
            time.sleep(holdtime)
            self.__release(cmd)
        
        
    def __press(self, cmd):
        try:
            idx = self.cmds[cmd]
        except KeyError:
            raise KeyError("Given command not listed.")
        else: 
            if self.timers[idx] != idx:
                self.timers[idx].cancel()
            self.__update_joystick(idx, 1)
            return True


    def __release(self, cmd):
        try:
            idx = self.cmds[cmd]
        except KeyError:
            raise KeyError("Given command not listed.")
        else:
            self.__update_joystick(idx, 0)
            return True


    def reset(self):
        """Resets timers and releases buttons"""

        print("tController:  Doing controller reset....")
        # Cancel all timers
        for idx, timer in enumerate(self.timers):
            if timer != idx:
                timer.cancel()
        # Release all buttons
        for command in self.cmds.keys():
            self.__release(command)
            
            
    def queue_command(self, cmd):
        """Enter the given command to execution queue"""
        
        self.queue.append(cmd)
        with self.condition:
            self.status = READY
            self.condition.notify()
        
    
    def queue_sequence(self, seq):
        """Enter the given sequence to sequence queue"""

        self.sequences.append(seq)
        with self.condition:
            self.status = READY
            self.condition.notify()
            
            
    def set_sequential_mode(self):
        self.sequence_exec = True
        
    
    def set_normal_mode(self):
        self.sequence_exec = False
        self.sequences = []
