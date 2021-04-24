import os
import json
import threading
import time
import random
import tcontroller as tc
import filewriter as fw
from twitchio.ext import commands
import asyncio
import concurrent.futures

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
        self.msg_queue = []
        
        # Command UTF formatting for logging use
        self.cmd_utf = config["cmd_utf"]
        
        # Voting variables
        self.votes = config["commands"]
        self.vote_time = config["vote_time"]
        self.mode_time = config["mode_time"]
        self.vote_timer = False
        self.mode_timer = False
        
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
            await self.mode_vote(ctx.author.name.lower(), content)
            return
            
        if self.mode == COMMUNISM:
            content = content.split(",")

        if self.check_content(content):
            print(f"Something valid : {content}")
            print(f"Mode : {self.mode}")
            if self.mode == DEMOCRACY:
                await self.vote(content, ctx.author.name.lower(), ctx.channel)
            elif self.mode == COMMUNISM:
                await self.communist_vote(content, ctx.author.name.lower(), ctx.channel)
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
                  

    
    async def vote(self, command, user, channel):
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
            
            if not self.vote_timer:
                self.vote_timer = True
                await channel.send(f"Voting started. Vote time {self.vote_time[0] + self.vote_time[1]} seconds")
                print("Voting started")
                self.fw_vinfo.clear()
                self.fw_vinfo.queue(f"Democracy rules supreme\n")
                self.fw_vinfo.queue(f"Now voting next command...\n")
                await asyncio.sleep(self.vote_time[0])
                await self.process_command_votes(channel)
    
        
    async def process_command_votes(self, channel):
        """Process all the buttonpress votes.
        Will determine which command got most votes and execute it.
        Resets the voting after done.
        """
        
        await channel.send(f"Voting ends in {self.vote_time[1]} seconds")
        await asyncio.sleep(self.vote_time[1])
        
        with self.votes_lock:
            self.vote_timer = False
            if not self.mode == DEMOCRACY:
                print("cancelled")
                await channel.send(f"Mode changed, vote cancelled")
                self.cmdvoters = []
                return
            
            print("Voting concluded")
            self.cmdvoters = []
            winner = max(self.votes, key = self.votes.get)
            print(f"Winner: {winner}, {self.votes[winner]}")
            if self.votes[winner] > 0:
                self.execute(str(winner))
                utf = self.get_cmd_utf(winner)
                await channel.send(f"Voting finished. Most votes for: {utf}")
                self.fw_log.queue(f"{utf} (Executed)\n")
                self.fw_vinfo.clear()
                self.fw_vinfo.queue(f"Democracy rules supreme\n")
                self.fw_vinfo.queue(f"Voting finished, winner: {utf}\n")
        self.init_democratic_vote()
    

    async def communist_vote(self, plan, user, channel):
    
        if user in self.cmdvoters:
            return
        if len(plan) == len(self.votes):
            utf = ""
            with self.votes_lock:
                for i,vote in enumerate(plan):
                    self.votes[i][vote] += 1
                    #if i != 0:
                    #    utf += ","
                    utf += self.get_cmd_utf(vote)
                self.cmdvoters.append(user)
                
            self.fw_log.queue(f"{utf} (Voted plan)\n")
            if not self.vote_timer:
                self.vote_timer = True
                await channel.send(f"Voting for next 5 command plan started. Vote time {self.vote_time[0] + self.vote_time[1]} seconds")
                self.fw_vinfo.clear()
                self.fw_vinfo.queue(f"Communist Comrades' Command Plan active\n")
                self.fw_vinfo.queue(f"Vote for next {self.plan_size} commands comrade\n")
                await asyncio.sleep(self.vote_time[0])
                await self.process_plan_votes(channel)
                

    async def process_plan_votes(self, channel):
        """Process all given communist plan votes and calculate results"""
        
        await channel.send(f"Plan voting ends in {self.vote_time[1]} seconds")
        await asyncio.sleep(self.vote_time[1])
        
        result = []
        utf = ""

        with self.votes_lock:
            self.vote_timer = False
            if not self.mode == COMMUNISM:
                self.cmdvoters = []
                return
            for i,v in enumerate(self.votes):
                result.append(self.dict_rng_max(self.votes[i]))
            print(f"Result: {result}")
            self.init_communist_vote()
            self.execute(result)
            
            self.cmdvoters = []
            for i,v in enumerate(result):
                #if i != 0:
                #    utf += ","
                utf += self.get_cmd_utf(v)
            await channel.send(f"Comrades, new 5 command plan decided: {utf}")
         
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
    
    
    async def mode_vote(self, user, vote):
        """Process the user vote for modechange
        Marks the given vote to specific user.
        Launches the mode checking timer if not already running
        """
        
        if user == self.botname.lower():
            return

        value = self.mode_commands[vote]
                
        with self.voters_lock:
            # Mode must be 0,1,2 (anarchy/democracy/communism)
            if value == ANARCHY or value == DEMOCRACY or value == COMMUNISM:
                self.voters[user] = value
                
        self.update_info()
        if not self.mode_timer:
            print("Mode change check started")
            self.mode_timer = True
            await asyncio.sleep(self.mode_time)
            await self.mode_check()
        
    async def mode_check(self):
        """Do recount on the users' mode votes and see if a change is necessary.
        
        """
            
        self.voters_lock.acquire()
        result, winner = self.count_voters()
        
        print("Anarchists:" + str(result[ANARCHY]))
        print("Democrats:" + str(result[DEMOCRACY]))
        print("Communists:" + str(result[COMMUNISM]))
        
        if result[winner] != result[self.mode]:
            self.set_mode(winner)
            self.mode_timer = False
                
        self.update_info()
        self.voters_lock.release()

        if self.mode_change != NO_CHANGE:
            self.mode_timer = True
            print("Mode rechecking timer running...")
            await asyncio.sleep(self.mode_time)
            await self.mode_check()
        else:
            self.mode_timer = False
        
            
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
