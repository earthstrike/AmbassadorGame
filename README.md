# AmbassadorGame
## Introduction
This is a discord game to practice being an ambassador for the EarthStrike movement. Players are randomly assigned as actors and persuader. After the actor reads their role, they are connected to a persuader via voice chat. The persuader then needs to work to get the actor interested in EarthStrike. Afterwards, the actor fills out ratings and feedback on well the persuader did, which is then shared with the persuader.

## Installing the bot on a Discord Server
- Create an application at https://discordapp.com/developers/
- https://discordapp.com/api/oauth2/authorize?client_id=CLIENT_ID_HERE&scope=bot&permissions=19930113

## Running the bot
Set environment variables:

`DISCORD_BOT_TOKEN`, `DISCORD_SERVER_ID` with respective information for your server. The Bot token comes from discordapp.com developer. The server id can be obtained from the server by right-clicking on the server, and clicking on the "copy id" menu. `DISCORD_TEST_MODE` can be set to `1` to enter test mode.

Currently, the prolific usage of [f-strings](https://realpython.com/python-f-strings/) requires python3.6+. Once these variables are set, you can run
`pip3 install -r requirements.txt
python3 bot.py
`

## Joining the game
You can message the bot '$join' to join the game.
