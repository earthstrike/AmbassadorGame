import asyncio
import os
import random

import numpy as np
from discord import PermissionOverwrite, ChannelType
from discord.ext.commands import Bot

PROFESSIONS = ["student", "retail salesperson", "cashier", "office clerk", "food worker", "nurse", "waiter/waitress",
               "custom service representative", "janitor", "manual laborer", "stock clerk or order filler", "manager",
               "book-keeper", "school teacher", "truck driver", "nursing aide",
               "wholesale or manufacturing sales representative", "teacher assistant", "mechanic", "repair worker",
               "retail supervisor", "administrative assistant", "accountant", "receptionist",
               "business operations specialist", "home health aide", "assembler", "restaurant cook", "maid",
               "groundskeeper", "childcare worker"]

BOT_PREFIX = "$"
TOKEN = os.environ.get('DISCORD_BOT_TOKEN')
SERVER_ID = os.environ.get('DISCORD_SERVER_ID')
PREP_TIME = 10  # 30
SESSION_TIME = 10  # 120

client = Bot(command_prefix=BOT_PREFIX)


class Canvasser(object):
    def __init__(self, server_id):
        self.server_id = server_id
        self.active_users = []
        self.matched = {}
        self.waiting = []

    async def try_match(self, author):
        """ See if we can find someone to match with, who we haven't already matched with """
        random.shuffle(self.waiting)
        for user in self.waiting:
            if user != author and (user not in self.matched or author not in self.matched[user]):
                await self.match(author, user)
                return
        self.waiting.append(author)
        await client.send_message(author, "You will be matched with someone shortly. Please wait....")

    async def match(self, a, b):
        """ Match two people with one as the random person, and the other as the trainee """
        if random.random() > .5:
            a, b = b, a

        age = random.randint(18, 58)
        profession = random.choice(PROFESSIONS)
        heard_of = np.random.choice(range(1, 11),
                                    p=[.9, .05, 0.00625, 0.00625, 0.00625, 0.00625, 0.00625, 0.00625, 0.00625, 0.00625])
        gs_probability = np.random.choice(range(1, 11),
                                          p=[.9, .05, 0.00625, 0.00625, 0.00625, 0.00625, 0.00625, 0.00625, 0.00625,
                                             0.00625])
        global_warming_concern = np.random.choice(range(1, 11),
                                                  p=[.2, .1, 0.065, 0.067, 0.067, 0.067, 0.067, 0.067, 0.1, 0.2])

        msg_a = f"""You are a {age} year old {profession}. On a scale of 1-10 (1 being none and 10 being the most), you have a strike awareness of {heard_of}.Possibility of strike succeeding {gs_probability}. Your concern about global warming is {global_warming_concern}. You will be connected in {PREP_TIME} seconds to a partner. Take a deep breath and get in character. You will give feedback after the session is over."""

        msg_b = f"""You are about to be matched with a partner playing a role. Be kind. You will have {SESSION_TIME // 60} minutes to get your partner more interested in EarthStrike. You will need to assess your partner's concerns tell them about EarthSrike if they haven't heard of it, tell them about the dangers we face from global warming, and help convince them that EarthStrike's strategy is the right approach. Take a deep breath and get ready...You will be connected in {PREP_TIME} seconds to a partner."""

        await client.send_message(a, msg_a)
        await client.send_message(b, msg_b)

        self.matched[a] = b
        self.matched[b] = a

        await asyncio.sleep(PREP_TIME)
        await self.start_voice(a, b)

    async def start_voice(self, a, b):
        """ Begin voice chat session between two people """
        everyone_perms = PermissionOverwrite(read_messages=False)
        my_perms = PermissionOverwrite(read_messages=True)
        server = client.get_server(self.server_id)
        if server is None:
            raise ConnectionError(f"Cannot connect to Server({SERVER_ID})")
        ch = await client.create_channel(server, f"canvas_game:{a.name}-{b.name}",
                                         (server.default_role, everyone_perms),
                                         (a, my_perms), (b, my_perms), type=ChannelType.voice)
        invite = await client.create_invite(destination=ch, xkcd=True, max_uses=2)
        await client.send_message(a, f"Please connect to: {invite.url}")
        await client.send_message(b, f"Please connect to: {invite.url}")

        # Force members in
        await client.move_member(a, ch)
        await client.move_member(b, ch)

        # TODO Don't start timer until both users have entered.
        await asyncio.sleep(SESSION_TIME)
        await self.end_voice(a, b, ch)

    async def end_voice(self, a, b, ch):
        """ End the voice channel message """
        await client.delete_channel(ch)
        del self.matched[a]
        del self.matched[b]

        responses = {a: [], b: []}

        def check(msg):
            """ Ensure message is a parsable integer in range 1-10"""
            try:
                return 1 <= int(msg.content) <= 10
            except:
                return False

        # Currently interviews users one-after-the-other, not concurrently. Might be blocking. 
        for u in (a, b):
            await client.send_message(u,
                                      "On a scale of 1-10 (1 being none and 10 being the most) how much would you estimate you "
                                      "know about EarthStrike after the conversation?")
            responses[u].append((await client.wait_for_message(author=u, check=check)).content)
            await client.send_message(u,
                                      "On a scale of 1-10 (1 being none and 10 being the most) how much would you estimate you are "
                                      "concerned about climate change after the conversation?")
            responses[u].append((await client.wait_for_message(author=u, check=check)).content)
            await client.send_message(u,
                                      "On a scale of 1-10 (1 being none and 10 being the most) how much do you think EarthStrike's "
                                      "strategy of a general strike is the right strategy for change?")
            responses[u].append((await client.wait_for_message(author=u, check=check)).content)
            await client.send_message(u, "What do you think your partner did well?")
            responses[u].append((await client.wait_for_message(author=u)).content)
            await client.send_message(u, "How do you think your partner could improve?")
            responses[u].append((await client.wait_for_message(author=u)).content)
            await client.send_message(u, "Your answers have been recorded. Thank you!")

        # TODO Do something with responses
        print(f"Canvas ({a}, {b}) complete!")


canv = Canvasser(SERVER_ID)


@client.event
async def on_ready():
    print("Done")


@client.command(name='join',
                description='Have user join the available member pool for canvasing partners',
                pass_context=True)
async def join(context):
    if context.message.author not in canv.active_users:
        canv.active_users.append(context.message.author)
        await canv.try_match(context.message.author)


print("Starting CanvasBot...", end='', flush=True)
client.run(TOKEN)
