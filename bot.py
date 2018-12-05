import asyncio
import logging
import os
import random
import sqlite3
import time
import uuid

import numpy as np
from discord import PermissionOverwrite, ChannelType
from discord.ext.commands import Bot

# Initialize default logger to write to file AND stdout
logging.basicConfig(level=logging.INFO, filename="CanvasBot.log", filemode="a+",
                    format="%(asctime)-15s %(levelname)-8s %(message)s")
logging.getLogger().addHandler(logging.StreamHandler())

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
GAME_CHANNEL = 'AmbassadorGame'
if os.environ.get('DISCORD_TEST_MODE') == '1':
    logging.info("TEST_MODE enabled")
    PREP_TIME = 10
    SESSION_TIME = 10
else:
    PREP_TIME = 30
    SESSION_TIME = 120

client = Bot(command_prefix=BOT_PREFIX)


class Canvasser(object):
    def __init__(self, server_id):
        self.server_id = server_id
        self.active_users = []
        self.matched = {}
        self.waiting = []
        self.db = sqlite3.connect('AmbassadorResults.db')
        self.cursor = self.db.cursor()
        self.init_db()
        self.game_channel_id = -1


    async def init_channel(self):
        """ Create the voice channel, that is used for matching users """
        server = client.get_server(self.server_id)
        for channel in server.channels:
            if channel.name == GAME_CHANNEL:
                self.game_channel_id = channel.id
        if self.game_channel_id == -1:
            my_perms = PermissionOverwrite(speak=False)
            ch = await client.create_channel(server, GAME_CHANNEL, (server.default_role, my_perms), type=ChannelType.voice)
            self.game_channel_id = ch.id

    def init_db(self):
        self.cursor.execute("CREATE TABLE IF NOT EXISTS session "
                            "(uuid TEXT NOT NULL PRIMARY KEY,"
                            " datetime INTEGER NOT NULL,"
                            " personA TEXT NOT NULL,"
                            " personB TEXT NOT NULL,"
                            " actor_persona INTEGER NOT NULL,"
                            " personB_response TEXT NOT NULL,"
                            "   FOREIGN KEY (actor_persona) REFERENCES actor_persona(uuid),"
                            "   FOREIGN KEY (personB_response) REFERENCES response(uuid));")
        self.cursor.execute("CREATE TABLE IF NOT EXISTS actor_persona"
                            "(uuid TEXT NOT NULL PRIMARY KEY,"
                            " discord_user INTEGER NOT NULL,"
                            " age INTEGER NOT NULL,"
                            " profession TEXT NOT NULL,"
                            " gs_prob REAL NOT NULL,"
                            " gw_concern REAL NOT NULL);")
        self.cursor.execute("CREATE TABLE IF NOT EXISTS response"
                            "(uuid TEXT NOT NULL PRIMARY KEY,"
                            " discord_user INTEGER NOT NULL,"
                            " discord_partner INTEGER NOT NULL,"
                            " knowledge INTEGER NOT NULL,"
                            " concern INTEGER NOT NULL,"
                            " strategy INTEGER NOT NULL,"
                            " partner_pro TEXT NOT NULL, "
                            " partner_con TEXT NOT NULL );")
        self.db.commit()

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
        """ Match two people with one as the actor, and the other as the persuader """
        if a in self.waiting: self.waiting.remove(a)
        if b in self.waiting: self.waiting.remove(b)

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

        msg_a = f"""You are a {age} year old {profession}. On a scale of 1-10 (1 being none and 10 being the most), you have a strike awareness of {heard_of}. Possibility of strike succeeding {gs_probability}. Your concern about global warming is {global_warming_concern}. You will be connected in {PREP_TIME} seconds to a partner. Take a deep breath and get in character. You will give feedback after the session is over."""

        msg_b = f"""You are about to be matched with a partner playing a role. Be kind. You will have {SESSION_TIME // 60} minutes to get your partner more interested in EarthStrike. You will need to assess your partner's concerns tell them about EarthSrike if they haven't heard of it, tell them about the dangers we face from global warming, and help convince them that EarthStrike's strategy is the right approach. Take a deep breath and get ready. You will be connected in {PREP_TIME} seconds to a partner."""

        session_id = str(uuid.uuid4())
        self.cursor.execute("INSERT INTO actor_persona VALUES (?,?,?,?,?,?)",
                            (session_id, a.id, age, profession, gs_probability, global_warming_concern))
        self.db.commit()

        await client.send_message(a, msg_a)
        await client.send_message(b, msg_b)

        self.matched[a] = b
        self.matched[b] = a

        logging.info(f"Created new session [{session_id}]:({a}, {b})")
        await asyncio.sleep(PREP_TIME)
        await self.start_voice(a, b, session_id)

    async def start_voice(self, a, b, session_id):
        """ Begin voice chat session between two people """
        everyone_perms = PermissionOverwrite(read_messages=False)
        my_perms = PermissionOverwrite(read_messages=True)
        server = client.get_server(self.server_id)
        if server is None:
            raise ConnectionError(f"Cannot connect to Server({SERVER_ID})")
        ch = await client.create_channel(server, f"canvas_game:{a.name}-{b.name}",
                                         (server.default_role, everyone_perms),
                                         (a, my_perms), (b, my_perms), type=ChannelType.voice)

        # Move members into voice channel
        a_member = server.get_member(a.id)
        b_member = server.get_member(b.id)
        await client.move_member(a_member, ch)
        await client.move_member(b_member, ch)

        logging.info(f"Waiting for users {a} and {b} to join Voice Channel...")

        async def ch_filled():
            """ Ensure both members have joined the voice chat. """
            while not len(client.get_channel(ch.id).voice_members) == 2:
                await asyncio.sleep(.1)

        try:
            await asyncio.wait_for(ch_filled(), PREP_TIME)
        except asyncio.TimeoutError:
            logging.info(f"Members didn't connect. Closing session {session_id}...")
            await self.close_session(a, b, ch)
        else:
            logging.info(f"Beginning Session [{session_id}]({a}, {b})...")
            await asyncio.sleep(SESSION_TIME)
            await self.end_voice(a, b, ch, session_id)

    async def close_session(self, a, b, ch):
        logging.info(f"Deleting channel {ch}...")
        await client.delete_channel(ch)
        self.active_users.remove(a)
        self.active_users.remove(b)
        del self.matched[a]
        del self.matched[b]

    async def end_voice(self, a, b, ch, session_id):
        """ End the voice channel message """
        logging.info(f"Ending Session [{session_id}]({a}, {b})...")
        await self.close_session(a, b, ch)

        response = []

        def check(msg):
            """ Ensure message is a parsable integer in range 1-10"""
            try:
                return 1 <= int(msg.content) <= 10
            except:
                return False

        # Administer exit survey
        await client.send_message(a,
                                  "On a scale of 1-10 (1 being none and 10 being the most) how much would you estimate you "
                                  "know about EarthStrike after the conversation?")
        response.append((await client.wait_for_message(author=a, check=check)).content)
        await client.send_message(a,
                                  "On a scale of 1-10 (1 being none and 10 being the most) how much would you estimate you are "
                                  "concerned about climate change after the conversation?")
        response.append((await client.wait_for_message(author=a, check=check)).content)
        await client.send_message(a,
                                  "On a scale of 1-10 (1 being none and 10 being the most) how much do you think EarthStrike's "
                                  "strategy of a general strike is the right strategy for change?")
        response.append((await client.wait_for_message(author=a, check=check)).content)
        await client.send_message(a, "What do you think your partner did well?")
        response.append((await client.wait_for_message(author=a)).content)
        await client.send_message(a, "How do you think your partner could improve?")
        response.append((await client.wait_for_message(author=a)).content)
        await client.send_message(a, "Your answers have been recorded. Thank you!")

        logging.info(f"Committing Session [{session_id}]({a}, {b}) to db...")
        self.cursor.execute("INSERT INTO response VALUES (?,?,?,?,?,?,?,?)",
                            (session_id, b.id, a.id, *response))
        self.cursor.execute("INSERT INTO session VALUES (?,?,?,?,?,?)",
                            (session_id, int(time.time()), a.id, b.id, session_id, session_id))
        self.db.commit()
        logging.info(f"Session [{session_id}]({a}, {b}) complete!")


canv = Canvasser(SERVER_ID)


@client.event
async def on_ready():
    await canv.init_channel()
    print("Done")
    logging.info("CanvasBot started")


@client.event
async def on_voice_state_update(before, after):
    """ Determine when a user has entered or left the main game voice channel, and start them in the game if they enter the channel """
    if before.voice.voice_channel == after.voice.voice_channel:
        return
    if not after.voice.voice_channel is None and after.voice.voice_channel.name == GAME_CHANNEL:
        if after not in canv.active_users:
            canv.active_users.append(after)
            await canv.try_match(after)
    elif not before.voice.voice_channel is None and before.voice.voice_channel.name == GAME_CHANNEL:
        if after not in canv.active_users:
           canv.active_users.remove(after) 

logging.info("Starting CanvasBot...")
try:
    client.run(TOKEN)
finally:
    logging.info("Closing database...")
    canv.db.close()
    logging.info("Done")
