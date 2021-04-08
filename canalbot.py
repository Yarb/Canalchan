import os
import json
import tcontroller as tc
from twitchio.ext import commands


class CanalBot(commands.Bot):


    def __init__(self, cfgfile):
        with open(cfgfile, 'r') as cfg:
            config = json.load(cfg)
        super().__init__(irc_token=config["tmi_token"], 
                         client_id=config["client_id"], 
                         nick=config["bot_nick"], 
                         prefix=config["bot_prefix"],
                         initial_channels=[config["channel"]])
        self.channel = config["channel"]
        self.botname = config["bot_nick"]
        self.buttons = config["buttons"]
        self.commands = config["commands"]
        self.joy = tc.tController(self.buttons, self.commands)


    async def event_ready(self):
        print(f"{self.botname} is online!")


    async def event_message(self, ctx):
        # make sure the bot ignores itself and the streamer
        if ctx.author.name.lower() == self.botname.lower():
            return

        parts = ctx.content.split("!")
        if len(parts) == 2:
            if parts[1] in self.commands:
                self.joy.press(parts[1])
            

if __name__ == "__main__":
  canalbot = CanalBot("config.json")
  canalbot.run()
