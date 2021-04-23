import os
import json
import threading
import time
import random
import tcontroller as tc
import filewriter as fw
from twitchio.ext import commands

NO_CHANGE = -1
ANARCHY = 0
DEMOCRACY = 1
COMMUNISM = 2
NO_VOTE = 3

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
        self.plan_size = config["plan_size"]
        
        # Command UTF formatting for logging use
        self.cmd_utf = config["cmd_utf"]
        
        
        # Voting variables
        self.votes = config["commands"]
        self.vote_time = config["vote_time"]
        self.mode_time = config["mode_time"]
        self.vote_timer_t = threading.Timer(self.vote_time, self.process_command_votes, args=())
        self.mode_timer_t = threading.Timer(self.mode_time, self.mode_check, args=())
        
        # Democracy/Anarchy mode variables
        self.voterounds = 0
        self.mode_change = NO_CHANGE
        self.mode = ANARCHY
        self.voters = dict()
        self.cmdvoters = []
        
        # Filewriters
        self.fw_info = fw.filewriter(config["info_file"], "w")
        self.fw_vinfo = fw.filewriter(config["vote_info_file"], "w")
        self.fw_log = fw.filewriter(config["log_file"], "a")
        
        self.fw_info.daemon = True
        self.fw_vinfo.daemon = True
        self.fw_log.daemon = True
        
        self.fw_info.start()
        self.fw_vinfo.start()
        self.fw_log.start()
        
        #Locks
        self.votes_lock = threading.Lock()
        self.voters_lock = threading.Lock()
        self.thread_lock = threading.Lock()
        
        # Init and reset controller. Reset votes
        self.joy = tc.tController(self.buttons,
                                  self.commands.copy(), 
                                  config["holdtime"], 
                                  config["holdtime_long"])
        self.joy.daemon = True
        self.joy.start()
        self.joy.reset()
        
        self.init_democratic_vote()
        self.update_info()
        self.fw_vinfo.queue("Anarchy active, anything goes")



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

        content = ctx.content.replace(" ","").lower()

        if self.prefix != "":
            parts = content.split(self.prefix)
            if len(parts) == 2:
                content = parts[1]
            else:
                return

        if content in self.mode_commands:
            self.mode_vote(ctx.author.name.lower(), content)
            self.update_info()
            return
            
        if self.mode == COMMUNISM:
            content = content.split(",")

        if self.check_content(content):
            if self.mode == DEMOCRACY:
                self.vote(content, ctx.author.name.lower())
            elif self.mode == COMMUNISM:
                self.communist_vote(content, ctx.author.name.lower())
            else:
                self.execute(content)
                utf = self.get_cmd_utf(content)
                self.fw_log.queue(f"{utf}\n")
    
    
    def check_content(self, content):
        if self.mode != COMMUNISM:
            if content not in self.commands:
                return False
            return True
        else:
            for i in content:
                if i not in self.commands:
                    return False
            return True
                  

    
    def vote(self, command, user):
        """Vote for given command.
        Function verifies the command and adds a registers the vote.
        Additionally, timer thread to process the votes is started if it was not running already.
        """
        
        if user in self.cmdvoters:
            return
        if command in self.votes:
            with self.votes_lock:
                self.votes[command] += 1
                self.cmdvoters.append(user)                
            
            utf = self.get_cmd_utf(command)
            self.fw_log.queue(f"{utf} (Vote)\n")
            
            if not self.vote_timer_t.is_alive():
                self.vote_timer_t = threading.Timer(self.vote_time, self.process_command_votes, args=())
                self.vote_timer_t.start()
                print("Voting started")
                self.fw_vinfo.clear()
                self.fw_vinfo.queue(f"Democracy rules supreme\n")
                self.fw_vinfo.queue(f"Now voting next command...\n")
    
        
    def process_command_votes(self):
        """Process all the buttonpress votes.
        Will determine which command got most votes and execute it.
        Resets the voting after done.
        """
        
        if not self.mode == DEMOCRACY:
            return
            
        print("Voting concluded")
        with self.votes_lock:
            self.cmdvoters = []
            winner = max(self.votes, key = self.votes.get)
            print(f"Winner: {winner}, {self.votes[winner]}")
            if self.votes[winner] > 0:
                self.execute(str(winner))
                utf = self.get_cmd_utf(winner)
                self.fw_log.queue(f"{utf} (Executed)\n")
                self.fw_vinfo.clear()
                self.fw_vinfo.queue(f"Democracy rules supreme\n")
                self.fw_vinfo.queue(f"Voting finished, winner: {utf}\n")
        self.init_democratic_vote()
    

    def communist_vote(self, plan, user):
    
        if user in self.cmdvoters:
            return
        if len(plan) == len(self.votes):
            utf = ""
            with self.votes_lock:
                for i,vote in enumerate(plan):
                    print(f"Inserting {i}, {vote}")
                    self.votes[i][vote] += 1
                    if i != 0:
                        utf += ","
                    utf += self.get_cmd_utf(vote)
                self.cmdvoters.append(user)
                
            self.fw_log.queue(f"{utf} (Voted plan)\n")
            
            if not self.vote_timer_t.is_alive():
                self.vote_timer_t = threading.Timer(self.vote_time, self.process_plan_votes, args=())
                self.vote_timer_t.start()
                print("Plan voting started")
                self.fw_vinfo.clear()
                self.fw_vinfo.queue(f"Communist Comrades' Command Plan active\n")
                self.fw_vinfo.queue(f"Vote for next {self.plan_size} commands comrade\n")
                

    def process_plan_votes(self):
        result = []
        if not self.mode == COMMUNISM:
            return
        utf = ""
        with self.votes_lock:    
            for i,v in enumerate(self.votes):
                result.append(self.dict_rng_max(self.votes[i]))
            print(f"Result: {result}")
            self.init_communist_vote()
            self.execute(result)
            
            self.cmdvoters = []
            for i,v in enumerate(result):
                if i != 0:
                    utf += ","
                utf += self.get_cmd_utf(v)
         
        self.fw_log.queue(f"{utf} (Winning plan)\n")
        self.fw_vinfo.clear()
        self.fw_vinfo.queue(f"Communist Comrades' Command Plan active\n")
        self.fw_vinfo.queue(f"Combined winning plan: {utf}\n")

    
    def execute(self, command):
        """Executes given command"""
        
        if isinstance(command, str) :
            print(f"Executing: {command}")
            self.joy.queue_command(command)
        elif isinstance(command, list):
            print(f"Executing communist plan: {command}")
            self.joy.queue_sequence(command)
    
    
    def init_democratic_vote(self):
        """Sets the votes for democratic mode.
        Ensure that you have acquired the votes_lock as this is not done here!
        """
    
        self.votes = dict.fromkeys(self.commands)
        for k in self.votes:
            self.votes[k] = 0
    
    
    def init_communist_vote(self):
        """Sets the votes for communist mode.
        Ensure that you have acquired the votes_lock as this is not done here!
        """

        self.votes = []
        for i in range(self.plan_size):
            self.votes.append(dict.fromkeys(self.commands,0))
        
    
    def dict_rng_max(self, dct):
        """Modified max value from dictionary. 
        If multiple keys have same value, pick one at random"""
        
        if len(dct) == 0:
            return
        loop = True
        bestvalue = 0
        contenders = []
        bestvalue = dct[max(dct, key = dct.get)]
        while(loop and len(dct) > 0):
            contender = max(dct, key = dct.get)
            if dct[contender] == bestvalue:
                contenders.append(contender) 
                dct.pop(contender)
            else:
                loop = False
        return contenders[random.randint(0,len(contenders) - 1)]
    
    
    def mode_vote(self, user, vote):
        """Process the user vote for modechange
        Marks the given vote to specific user.
        Launches the mode checking timer if not already running
        """
        
        if user == self.botname.lower():
            return

        value = self.mode_commands[vote]
                
        self.voters_lock.acquire()
        # Mode must be 0,1,2 (anarchy/democracy/communism)
        if value == ANARCHY or value == DEMOCRACY or value == COMMUNISM:
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
        result, winner = self.count_voters()
        
        print("Anarchists:" + str(result[ANARCHY]))
        print("Democrats:" + str(result[DEMOCRACY]))
        print("Communists:" + str(result[COMMUNISM]))
        
        if result[winner] != result[self.mode]:
            self.set_mode(winner)
                
        self.update_info()
        self.voters_lock.release()

        self.thread_lock.acquire()
        if self.mode_change != NO_CHANGE:
            print("Creating new timed thread for mode checking...")
            self.mode_timer_t = threading.Timer(self.mode_time, self.mode_check, args=())
            self.mode_timer_t.start()
        self.thread_lock.release()
        
            
    def set_mode(self, mode):
        """Set the mode/mode_change indicator"""
        
        if self.mode_change == mode:         
            self.mode = mode
            self.fw_log.queue("Mode change\n")
            self.fw_vinfo.clear()

            if self.mode == ANARCHY:
                self.fw_vinfo.queue("Anarchy active, anything goes")
            elif self.mode == DEMOCRACY:
                self.fw_vinfo.queue("Democracy rules supreme")
            elif self.mode == COMMUNISM:
                self.fw_vinfo.queue("Welcome to communism, comrade")
                self.fw_vinfo.queue(f"Communist Comrades' Command Plan active\n")
            self.mode_change = NO_CHANGE

            if mode != COMMUNISM:
                self.joy.set_normal_mode()
                self.init_democratic_vote()
            else:
                self.joy.set_sequential_mode()
                self.init_communist_vote()

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
        elif self.mode == COMMUNISM:
            return "Communism"
        
    
    def count_voters(self):
        """Helper function to calculate numbers of anarchist/democrat voters"""
        
        result = [0,0,0]
        winner = 0
        for i in self.voters.values():
            if i == ANARCHY:
                result[ANARCHY] += 1
            elif i == DEMOCRACY:
                result[DEMOCRACY] += 1
            elif i == COMMUNISM:
                result[COMMUNISM] += 1
                
        if result[COMMUNISM] > result[winner]:
            winner = COMMUNISM
        if result[DEMOCRACY] > result[winner]:
            winner = DEMOCRACY
               
        return result, winner
        
        
    def update_info(self):
        """Update the mode status to configured file.
        """
        
        result, winner = self.count_voters()
        anarchists = str(result[ANARCHY])
        democrats = str(result[DEMOCRACY])
        communists = str(result[COMMUNISM])
        
        status1 = f"Mode: {self.get_mode()}."
        status2 = f"Democrats : {democrats} -  Anarchists : {anarchists} - Communists : {communists}"
        change = ""
        if self.mode_change == ANARCHY:
            change += "Moving to anarchy!"
        elif self.mode_change == DEMOCRACY:
            change += "Moving to democracy!"
        elif self.mode_change == COMMUNISM:
            change += "Moving to communism!"
        
        self.fw_info.clear()
        self.fw_info.queue(status1 + "\n" + status2 + "\n" + change)


    def get_cmd_utf(self, command):
        if command in self.cmd_utf:
            return self.cmd_utf[command]
        else:
            return command
        

if __name__ == "__main__":
  canalbot = CanalBot("config.json")
  canalbot.run()
