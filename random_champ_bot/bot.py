import os
import random 

import discord

from discord.ext import commands
from dotenv import load_dotenv
from io import BytesIO

from champs.random_champ_weighted import get_random_champs_weighted, make_grid_from_champs

load_dotenv()

bot = commands.Bot(command_prefix="champs", intents=discord.Intents.all())

random_wyns = [
    "wyn is a fucking moron",
    "wyn is literally steve from minecraft",
    "petrol head wyn strikes again",
    "wyn has single digit IQ",
    "wyn has double digit IQ",
    "wyn's anivia is actually really good",
    "wyn on ad vs. wyn off-role",
    "wyn's favourite beer is budweiser",
    "wyn spent >1k on a greenhouse for tomatoes",
    "wyn drives a 2008 honda civic which he paid 10k for in 2024",
    "wyn wishes he could main qiyana",
    "just imagine being wyn",
    "wyn likes to go fly fishing with his dad",
    "leblanc combo 2022",
    "wyn gets silent when tilted",
    "wyn cannot play jhin",
]


@bot.command()
async def get(ctx, N="40"):
    special = False
    if N == "0.5":
        N = "1"
        special = True
    try:
        N = int(N)
    except:
        await ctx.send("Send a whole number between 1 & 120")
        return
    if N == 1337:
        wyns = random_wyns.copy()
        random.shuffle(wyns)
        await ctx.send(wyns[0])
        return
    if N < 1 or N > 120:
        await ctx.send("Send a whole number between 1 & 120")
        return
    champs = get_random_champs_weighted(N)
    img = make_grid_from_champs(champs)
    if special:
        champs = [champ[:len(champ)//2] for champ in champs]
        img = img.crop((0, 0, 30, 60))
    img_bytes = BytesIO()
    img.save(img_bytes, format='PNG')
    img_bytes.seek(0)
    file = discord.file.File(img_bytes, filename='champs.png')
    await ctx.send(", ".join(champs), file=file)

bot.run(os.getenv("DISCORD_TOKEN"))
