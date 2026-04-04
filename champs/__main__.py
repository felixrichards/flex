import os

import discord
from discord.ext import commands
from dotenv import load_dotenv

from champs.db import db
from champs.draft import handle_draft
from champs.elo import handle_elo
from champs.get import handle_get
from champs.match import handle_match, handle_on_message

load_dotenv()

bot = commands.Bot(command_prefix="champs", intents=discord.Intents.all())
DB_PATH = os.getenv("CHAMPS_DB_PATH", "/app/data/champs.db")


# `champsget [N] [filters...]`
# Returns random champions (weighted by role by default), with optional count and filters.
# Special cases supported by handler: OTP shortcut, half-name mode, and Wyn easter egg.
@bot.command()
async def get(ctx, *args):
    await handle_get(ctx, args)


# `champsmatch [subcommand]`
# Parse/confirm scoreboard matches and maintain mappings/history.
# Subcommands: `help`, `addplayer <player> <name> [role]`, `delete` (with screenshot), or default parse flow.
@bot.command()
async def match(ctx, *args):
    await handle_match(ctx, args, DB_PATH)


# `champselo [player_or_username ...]`
# Shows ELO table with rank, player, elo, wins, losses.
# With args, filters to matching players (username args map to actual names; duplicates are ignored).
@bot.command()
async def elo(ctx, *args):
    await handle_elo(ctx, args, DB_PATH)


# `champsdraft [players...] [+player...] [-player...]`
# Builds two balanced teams using role-aware effective ELO (supports voice-channel auto-detection).
@bot.command()
async def draft(ctx, *args):
    await handle_draft(ctx, args, DB_PATH)


# Handles replies to bot match messages for JSON correction updates,
# then falls back to normal command processing for all other messages.
@bot.event
async def on_message(message: discord.Message):
    handled = await handle_on_message(message, bot, DB_PATH)
    if not handled:
        await bot.process_commands(message)


db.init_db(DB_PATH)
bot.run(os.getenv("DISCORD_TOKEN"))
