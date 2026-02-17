import os
import time
import asyncio
import uvloop
import uvicorn
from asyncio import get_event_loop
from faulthandler import enable as faulthandler_enable
from logging import ERROR, INFO, StreamHandler, basicConfig, getLogger, handlers

# uvloop setup
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
getLogger("pyrogram").setLevel(ERROR)

MOD_LOAD, MOD_NOLOAD, HELPABLE, cleanmode = [], ["subscene_dl"], {}, {}
botStartTime = time.time()
misskaty_version = "v2.16.1"
faulthandler_enable()

# --- STEP 1: Define Variables at Top Level ---
BOT_ID = 0
BOT_NAME = ""
BOT_USERNAME = ""
UBOT_ID = None
UBOT_NAME = None
UBOT_USERNAME = None

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

# --- STEP 2: Start and Assign Values ---
async def initialize_bot():
    global BOT_ID, BOT_NAME, BOT_USERNAME, UBOT_ID, UBOT_NAME, UBOT_USERNAME
    
    await app.start()
    BOT_ID = app.me.id
    BOT_NAME = app.me.first_name
    BOT_USERNAME = app.me.username
    
    if USER_SESSION:
        try:
            await user.start()
            UBOT_ID = user.me.id
            UBOT_NAME = user.me.first_name
            UBOT_USERNAME = user.me.username
        except Exception:
            pass

loop.run_until_complete(initialize_bot())
print(f"BOT STARTED AS @{BOT_USERNAME}")

# Scheduler
jobstores = {"default": MongoDBJobStore(client=MongoClient(DATABASE_URI), database=DATABASE_NAME, collection="nightmode")}
scheduler = AsyncIOScheduler(jobstores=jobstores, timezone=TZ)
