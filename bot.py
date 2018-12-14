import asyncio
import logging
import os
import random
import sqlite3
import sys
import time
import uuid

import numpy as np
import six
from discord import PermissionOverwrite, DMChannel, FFmpegPCMAudio
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
GUILD_ID = int(os.environ.get('DISCORD_SERVER_ID'))
GAME_VOICE_QUEUE_CHANNEL = 'Ambassador Game Queue'
GAME_CATEGORY_CHANNEL = 'Ambassador Games'
SESSION_CHANNEL_PREFIX = "canvas_game:"
if os.environ.get('DISCORD_TEST_MODE') == '1':
    logging.info("TEST_MODE enabled")
    PREP_TIME = 3
    SESSION_TIME = 3
else:
    PREP_TIME = 30
    SESSION_TIME = 300


class Canvasser(object):
    def __init__(self, bot, guild_id):
        self.bot = bot
        self.guild_id = guild_id
        self.active_users = set()
        self.survey_users = set()
        self.active_channels = set()
        self.matched = {}
        self.waiting = set()
        self.db = sqlite3.connect('AmbassadorResults.db')
        self.cursor = self.db.cursor()
        self.init_db()
        self.game_channel_id = None
        self.category_channel_id = None

    async def add_user(self, user):
        if user in self.survey_users:
            return False
        self.active_users.add(user)
        return True

    async def clean_channels(self):
        """ Delete any stray 1-on-1 channels that might be leftover. """
        guild = self.bot.get_guild(self.guild_id)
        for channel in guild.channels:
            if channel.name.startswith(SESSION_CHANNEL_PREFIX):
                await channel.delete()

    async def init_channel(self):
        """ Create permanent channels for the game """
        guild = self.bot.get_guild(self.guild_id)
        for channel in guild.channels:
            if channel.name == GAME_VOICE_QUEUE_CHANNEL:
                logging.info("Found existing Channel Category")
                self.game_channel_id = channel.id
                self.category_channel_id = channel.category.id
                # Add existing users to the game
                for member in channel.members:
                    if not member.bot:
                        logging.info(f"User {member} is ACTIVE")
                        self.active_users.add(member)
                        await self.try_match(member)
        if self.game_channel_id is None:
            logging.info("No category channel found. Creating one...")
            my_perms = PermissionOverwrite(speak=False)
            cat = await guild.create_category_channel(GAME_CATEGORY_CHANNEL)
            self.category_channel_id = cat.id
            ch = await guild.create_voice_channel(GAME_VOICE_QUEUE_CHANNEL, overwrites={guild.default_role: my_perms},
                                                  category=cat)
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
                            " gs_prob INTEGER NOT NULL,"
                            " gw_concern INTEGER NOT NULL);")
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
        waiting = list(self.waiting)
        random.shuffle(waiting)
        for user in waiting:
            if user != author and (user not in self.matched or author not in self.matched[user]):
                await self.match(author, user)
                return
        self.waiting.add(author)
        await (await author.create_dm()).send("You will be matched with someone shortly. Please wait....")

    async def match(self, a, b):
        """ Match two people with one as the actor, and the other as the persuader """
        if a in self.waiting: self.waiting.remove(a)
        if b in self.waiting: self.waiting.remove(b)

        if random.random() > .5:
            a, b = b, a

        age = random.randint(18, 58)
        profession = random.choice(PROFESSIONS)
        heard_of = int(np.random.choice(range(1, 11),
                                        p=[.9, .05, 0.00625, 0.00625, 0.00625, 0.00625, 0.00625, 0.00625, 0.00625,
                                           0.00625]))
        gs_probability = int(np.random.choice(range(1, 11),
                                              p=[.9, .05, 0.00625, 0.00625, 0.00625, 0.00625, 0.00625, 0.00625, 0.00625,
                                                 0.00625]))
        global_warming_concern = int(np.random.choice(range(1, 11),
                                                      p=[.2, .1, 0.065, 0.067, 0.067, 0.067, 0.067, 0.067, 0.1, 0.2]))

        msg_a = f"""You are a {age} year old {profession}.\nOn a scale of 1-10 (1 being none and 10 being the most), you have a strike awareness of {heard_of}.\nPossibility of strike succeeding {gs_probability}.\nYour concern about global warming is {global_warming_concern}.\nYou will be connected in {PREP_TIME} seconds to a partner. Take a deep breath and get in character. You will give feedback after the session is over."""

        msg_b = f"""You are about to be matched with a partner playing a role. Be kind. You will have {SESSION_TIME // 60} minutes and {SESSION_TIME % 60} seconds to get your partner more interested in EarthStrike. You will need to assess your partner's concerns tell them about EarthSrike if they haven't heard of it, tell them about the dangers we face from global warming, and help convince them that EarthStrike's strategy is the right approach. Take a deep breath and get ready. You will be connected in {PREP_TIME} seconds to a partner."""

        session_id = str(uuid.uuid4())
        self.cursor.execute("INSERT INTO actor_persona VALUES (?,?,?,?,?,?)",
                            (session_id, a.id, age, profession, gs_probability, global_warming_concern))
        self.db.commit()

        await (await a.create_dm()).send(msg_a)
        await (await b.create_dm()).send(msg_b)

        self.matched[a] = b
        self.matched[b] = a

        logging.info(f"Created new session [{session_id}]:({a}, {b})")
        await asyncio.sleep(PREP_TIME)
        await self.start_voice(a, b, session_id)

    async def start_voice(self, a, b, session_id):
        """ Begin voice chat session between two people """
        everyone_perms = PermissionOverwrite(read_messages=False)
        my_perms = PermissionOverwrite(read_messages=True)
        guild = self.bot.get_guild(self.guild_id)
        if guild is None:
            raise ConnectionError(f"Cannot connect to Guild({GUILD_ID})")
        ch = await guild.create_voice_channel(f"{SESSION_CHANNEL_PREFIX}{a.name}-{b.name}",
                                              overwrites={guild.default_role: everyone_perms, a: my_perms, b: my_perms},
                                              category=self.bot.get_channel(self.category_channel_id))
        self.active_channels.add(ch)

        # Move members into voice channel
        a_member = guild.get_member(a.id)
        b_member = guild.get_member(b.id)
        await a_member.edit(voice_channel=ch)
        await b_member.edit(voice_channel=ch)

        logging.info(f"Waiting for users {a} and {b} to join Voice Channel...")

        async def ch_filled():
            """ Ensure both members have joined the voice chat. """
            while not len(self.bot.get_channel(ch.id).members) == 2:
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
        self.active_channels.remove(ch)
        await ch.delete()
        if a in self.active_users:
            self.active_users.remove(a)
        if b in self.active_users:
            self.active_users.remove(b)
        del self.matched[a]
        del self.matched[b]

    async def end_voice(self, a, b, ch, session_id):
        """ End the voice channel message """
        logging.info(f"Ending Session [{session_id}]({a}, {b})...")
        # Have the bot speak
        vc = await ch.connect()
        vc.play(FFmpegPCMAudio(r"res/sound/exit.mp3"), after=lambda e: logging.info(
            f"Session {session_id} audio ended{': ' + str(e) if e else ' successfully'}"))
        while vc.is_playing():
            await asyncio.sleep(.1)
        vc.stop()

        self.survey_users.add(a)
        await self.close_session(a, b, ch)

        response = []

        def check_for_pm(msg):
            """ Ensure message is in private messages """
            try:
                return not msg.author.bot and msg.content is not None and msg.guild is None and isinstance(msg.channel,
                                                                                                           DMChannel)
            except:
                return False

        def check_number(msg):
            """ Ensure message is a parsable integer in range 1-10 and in PMs"""
            try:
                return 1 <= int(msg.content) <= 10 and check_for_pm(msg)
            except:
                return False

        # Administer exit survey
        await(await a.create_dm()).send(
            "On a scale of 1-10 (1 being none and 10 being the most) how much would you estimate you "
            "know about EarthStrike after the conversation?")
        response.append((await self.bot.wait_for('message', check=check_number)).content)
        await(await a.create_dm()).send(
            "On a scale of 1-10 (1 being none and 10 being the most) how much would you estimate you are "
            "concerned about climate change after the conversation?")
        response.append((await self.bot.wait_for('message', check=check_number)).content)
        await(await a.create_dm()).send(
            "On a scale of 1-10 (1 being none and 10 being the most) how much do you think EarthStrike's "
            "strategy of a general strike is the right strategy for change?")
        response.append((await self.bot.wait_for('message', check=check_number)).content)
        await(await a.create_dm()).send("What do you think your partner did well?")
        response.append((await self.bot.wait_for('message', check=check_for_pm)).content)
        await(await a.create_dm()).send("How do you think your partner could improve?")
        response.append((await self.bot.wait_for('message', check=check_for_pm)).content)
        await(await a.create_dm()).send("Your answers have been recorded. Thank you!")

        logging.info(f"Committing Session [{session_id}]({a}, {b}) to db...")
        self.cursor.execute("INSERT INTO response VALUES (?,?,?,?,?,?,?,?)",
                            (session_id, b.id, a.id, *response))
        self.cursor.execute("INSERT INTO session VALUES (?,?,?,?,?,?)",
                            (session_id, int(time.time()), a.id, b.id, session_id, session_id))
        self.db.commit()
        logging.info(f"Session [{session_id}]({a}, {b}) complete!")
        self.survey_users.remove(a)
        await self.show_feedback(session_id)

    async def show_feedback(self, session):
        """ Show feedback to the persuader after the actor rates their performance"""
        self.cursor.execute("select age,profession,gs_prob,gw_concern FROM actor_persona WHERE uuid=?", (session,))
        actor = self.cursor.fetchall()[0]
        self.cursor.execute(
            "select knowledge, concern, strategy, partner_pro, partner_con, discord_user FROM response WHERE uuid=?",
            (session,))
        response = self.cursor.fetchall()[0]
        message = f"""Your partner was acting as a {actor[0]} year old {actor[1]}. Your conversation started with {
        actor[
            3]}/10 concern for global warming and ended with {response[1]}/10 concern. Your conversation started with {
        actor[2]}/10 belief in EarthStrike's strategy and ended with {response[
            2]}/10 belief in EarthStrike's strategy.\nWhat you did well: *{response[
            3]}*\nThings you could improve on: *{response[4]}*"""
        guild = self.bot.get_guild(self.guild_id)
        user = guild.get_member(int(response[5]))
        await (await user.create_dm()).send(message)

    async def cleanup(self):
        logging.info("Cleaning up CanvasBot")
        self.db.close()
        for channel in self.active_channels:
            logging.info(f"Deleting channel {channel}")
            await channel.delete()
        await self.clean_channels()  # Get any stray channels that somehow survived.


if __name__ == "__main__":
    bot = Bot(command_prefix=BOT_PREFIX, bot=True)
    ambassador_bot = Canvasser(bot, GUILD_ID)


    @bot.event
    async def on_ready():
        await ambassador_bot.clean_channels()
        await ambassador_bot.init_channel()
        logging.info("CanvasBot started")


    @bot.event
    async def on_error(error, *args, **kwargs):
        logging.error(f"Error created by event {error}. Cleaning up and exiting.")
        await ambassador_bot.cleanup()
        if os.environ.get('DISCORD_TEST_MODE') == '1':
            six.reraise(*sys.exc_info())
        else:
            logging.exception("Runtime error:", exc_info=sys.exc_info())
            exit()


    @bot.event
    async def on_voice_state_update(member, before, after):
        """ Determine when a user has entered or left the main game voice channel, and start them in the game if they enter the channel """
        if member.bot:
            return
        if before.channel == after.channel:
            return
        if after.channel is not None and after.channel.name == GAME_VOICE_QUEUE_CHANNEL:
            if member not in ambassador_bot.active_users:
                logging.info(f"User {member} is ACTIVE")
                # Try to add a new user. If they still have an active survey kick them.
                if await ambassador_bot.add_user(member):
                    await ambassador_bot.try_match(member)
        elif before.channel is not None and before.channel.name == GAME_VOICE_QUEUE_CHANNEL:
            if member in ambassador_bot.active_users:
                ambassador_bot.active_users.remove(member)
                logging.info(f"User {member} REMOVED(active)")
            if member in ambassador_bot.waiting:
                ambassador_bot.waiting.remove(member)
                logging.info(f"User {member} REMOVED(waiting)")


    logging.info("Starting CanvasBot...")
    bot.run(TOKEN)
