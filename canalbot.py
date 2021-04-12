import os
import json
import threading
import time
import tcontroller as tc
from twitchio.ext import commands

NO_CHANGE = -1
ANARCHY = 0
DEMOCRACY = 1
NO_VOTE = 2

class CanalBot(commands.Bot):

    
    def __init__(self, cfgfile):
        with open(cfgfile, 'r') as cfg:
            config = json.load(cfg)
        super().__init__(irc_token=config["tmi_token"], 
                         client_id=config["client_id"], 
                         nick=config["bot_nick"], 
                         prefix=config["bot_prefix"],
                         initial_channels=[config["channel"]])
                         
        # Bot config and commands                 
        self.channel = config["channel"]
        self.botname = config["bot_nick"]
        self.buttons = config["buttons"]
        self.prefix = config["bot_prefix"]
        self.commands = config["commands"]
        self.mode_commands = config["mode_commands"]
        
        
        # Voting variables
        self.votes = config["commands"]
        self.vote_time = config["vote_time"]
        self.mode_time = config["mode_time"]
        self.vote_timer_t = threading.Timer(self.vote_time, self.process_votes, args=())
        self.mode_timer_t = threading.Timer(self.mode_time, self.mode_check, args=())
        
        # Democracy/Anarchy mode variables
        self.voterounds = 0
        self.mode_change = NO_CHANGE
        self.mode = ANARCHY
        self.voters = dict()
        
        # Files to update
        self.info_file = config["info_file"]
        self.vote_info_file = config["vote_info_file"]
        
        #Locks
        self.votes_lock = threading.Lock()
        self.voters_lock = threading.Lock()
        self.thread_lock = threading.Lock()
        
        # Init and reset controller. Reset votes
        self.joy = tc.tController(self.buttons,
                                  self.commands.copy(), 
                                  config["holdtime"], 
                                  config["holdtime_long"])
        self.joy.reset()
        self.reset_votes()
        self.update_info()



    async def event_ready(self):
        """Bot ready event - Simply prints message to show that bot activated"""
        
        print(f"{self.botname} is online!")


    async def event_join(self, user):
        """Bot function to handle joining users.
        Adds new users to the voters dictionary.
        """
        
        # Do not put bot in the voter list
        if user.name.rstrip().lower() == self.botname.lower():
            return
        
        print("User joined: " + user.name)
        
        self.voters_lock.acquire()
        if not user.name in self.voters:
            self.voters[user.name.lower()] = NO_VOTE
        self.voters_lock.release()
        
        
    async def event_part(self, user):
        """Bot function to handle parting users.
        Changes the voters dictionary to match users in chat
        """
        
        self.voters_lock.acquire()
        if user.name.lower() in self.voters:
            self.voters.pop(user.name.lower())
        self.update_info()
        self.voters_lock.release()
        

    async def event_message(self, ctx):
        """Bot function to capture and process messages.
        Parses the context, verifies possible commands and forwards them accordingly.
        """
        
        # make sure the bot ignores itself and the streamer
        if ctx.author.name.lower() == self.botname.lower():
            return

        content = ctx.content.lower()

        if self.prefix != "":
            parts = content.split(self.prefix)
            if len(parts) == 2:
                content = parts[1]
            else:
                return

        if content in self.commands:
            if self.mode == DEMOCRACY:
                self.vote(content)
            else:
                self.execute(content)
        elif content in self.mode_commands:
            self.mode_vote(ctx.author.name.lower(), content)
        self.update_info()
    
    
    def vote(self, command):
        """Vote for given command.
        Function verifies the command and adds a registers the vote.
        Additionally, timer thread to process the votes is started if it was not running already.
        """
        
        if command in self.votes:
            self.votes_lock.acquire()
            self.votes[command] += 1
            self.votes_lock.release()
            if not self.vote_timer_t.is_alive():
                self.vote_timer_t = threading.Timer(self.vote_time, self.process_votes, args=())
                self.vote_timer_t.start()
                print("Voting started")
                with open(self.vote_info_file, 'w+') as outfile:
                    outfile.write(f"\nNow voting next command..." )
                    outfile.flush()
    
        
    def process_votes(self):
        """Process all the buttonpress votes.
        Will determine which command got most votes and execute it.
        Resets the voting after done.
        """
        
        if not self.mode == DEMOCRACY:
            return
            
        print("Voting concluded")
        self.votes_lock.acquire()
        winner = max(self.votes, key = self.votes.get)
        with open(self.vote_info_file, 'w+') as outfile:
            outfile.write(f"Executed command: {winner}\nNow voting next command..." )
            outfile.flush()
        if self.votes[winner] > 0:
            self.execute(str(winner))
        self.reset_votes()
        self.votes_lock.release()
    
    
    def execute(self, command):
        """Executes given command"""
        
        print(f"Executing: {command}")
        self.joy.press(command)
    
    
    def reset_votes(self):
        """Resets the votes for buttonpresses.
        Ensure that you have acquired the votes_lock as this is not done here!
        """
        
        for k in self.votes:
            self.votes[k] = 0
    
    
    def mode_vote(self, user, vote):
        """Process the user vote for modechange
        Marks the given vote to specific user.
        Launches the mode checking timer if not already running
        """
        
        if user == self.botname.lower():
            return

        value = self.mode_commands[vote]
                
        self.voters_lock.acquire()
        # Mode must be 0 or 1 (anarchy/democracy)
        if value == ANARCHY or value == DEMOCRACY:
            self.voters[user] = value
            
        self.thread_lock.acquire()
        if not self.mode_timer_t.is_alive():
            self.mode_timer_t = threading.Timer(self.mode_time, self.mode_check, args=())
            self.mode_timer_t.start()
            print("Mode change check started")
        self.update_info()
        self.thread_lock.release()
        self.voters_lock.release()

        
    def mode_check(self):
        """Do recount on the users' mode votes and see if a change is necessary.
        
        """
            
        self.voters_lock.acquire()
        anarchists, democrats = self.count_voters()
        
        print("Anarchists:" + str(anarchists))
        print("Democrats:" + str(democrats))
        
        # Check which side is winning. Ties keep system as is
        if anarchists < democrats:
            self.set_mode(DEMOCRACY)
        elif anarchists > democrats:
            self.set_mode(ANARCHY)
            
        self.update_info()
        self.voters_lock.release()

        self.thread_lock.acquire()
        if self.mode_change != NO_CHANGE:
            print("creating new timed thread for mode checking...")
            self.mode_timer_t = threading.Timer(self.mode_time, self.mode_check, args=())
            self.mode_timer_t.start()
        self.thread_lock.release()
        
            
    def set_mode(self, mode):
        """Set the mode/mode_change indicator"""
        
        if self.mode_change == mode:         
            self.mode = mode
            self.mode_change = NO_CHANGE
        else:
            if self.mode == mode:
                self.mode_change = NO_CHANGE
            else:
                self.mode_change = mode
            
    
    def get_mode(self):
        """Return current mode in string"""
        
        if self.mode == DEMOCRACY:
            return "Democracy"
        elif self.mode == ANARCHY:
            return "Anarchy"
        
    
    def count_voters(self):
        """Helper function to calculate numbers of anarchist/democrat voters"""
        
        anarchists = 0
        democrats = 0
        for i in self.voters.values():
            if i == ANARCHY:
                anarchists += 1
            elif i == DEMOCRACY:
                democrats += 1
        return anarchists, democrats
        
        
    def update_info(self):
        """Update the mode status to configured file.
        """
        
        a,d = self.count_voters()
        anarchists = str(a)
        democrats = str(d)
        
        status1 = f"Mode: {self.get_mode()}."
        status2 = f"Democrats : {democrats} - {anarchists} : Anarchists"
        change = ""
        if self.mode_change == ANARCHY:
            change += "Moving to anarchy!"
        elif self.mode_change == DEMOCRACY:
            change += "Moving to democracy!"
        
        with open(self.info_file, 'w+') as info_file:
            info_file.write(status1 + "\n" + status2 + "\n" + change)
            info_file.flush()



if __name__ == "__main__":
  canalbot = CanalBot("config.json")
  canalbot.run()
