import os
import time
import asyncio
import uvloop
import uvicorn
from asyncio import get_event_loop
from faulthandler import enable as faulthandler_enable
from logging import ERROR, INFO, StreamHandler, basicConfig, getLogger, handlers

# uvloop setup - MUST be before importing Pyrogram Client
asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
try:
    loop = asyncio.get_event_loop()
except RuntimeError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

from apscheduler.jobstores.mongodb import MongoDBJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from async_pymongo import AsyncClient
from pymongo import MongoClient
from pyrogram import Client
from web.webserver import api
from misskaty.vars import *

# Logging Setup
basicConfig(
    level=INFO,
    format="[%(levelname)s] - [%(asctime)s - %(name)s - %(message)s] -> [%(module)s:%(lineno)d]",
    datefmt="%d-%b-%y %H:%M:%S",
    handlers=[StreamHandler()],
)

MOD_LOAD, MOD_NOLOAD, HELPABLE, cleanmode = [], ["subscene_dl"], {}, {}
botStartTime = time.time()
faulthandler_enable()

# Pyrogram Clients
app = Client(
    "MissKatyBot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    mongodb=dict(connection=AsyncClient(DATABASE_URI), remove_peers=True),
)

user = Client(
    "YasirUBot",
    session_string=USER_SESSION,
    mongodb=dict(connection=AsyncClient(DATABASE_URI), remove_peers=False),
)

# Function to start everything
async def start_misskaty():
    await app.start()
    print(f"BOT STARTED AS @{app.me.username}")
    if USER_SESSION:
        try:
            await user.start()
            print("USERBOT STARTED")
        except Exception as e:
            print(f"USERBOT ERROR: {e}")

# Trigger the start
loop.run_until_complete(start_misskaty())

BOT_ID = app.me.id
BOT_NAME = app.me.first_name
BOT_USERNAME = app.me.username
