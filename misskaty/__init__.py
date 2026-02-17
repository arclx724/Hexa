import os
import time
import asyncio
import uvloop
import uvicorn
from asyncio import get_event_loop
from faulthandler import enable as faulthandler_enable
from logging import ERROR, INFO, StreamHandler, basicConfig, getLogger, handlers

# 1. uvloop setup
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
from pyrogram import Client, filters
from web.webserver import api
from misskaty.vars import *

# 2. Logging Setup
basicConfig(
    level=INFO,
    format="[%(levelname)s] - [%(asctime)s - %(name)s - %(message)s] -> [%(module)s:%(lineno)d]",
    datefmt="%d-%b-%y %H:%M:%S",
    handlers=[StreamHandler()],
)
getLogger("pyrogram").setLevel(ERROR)

# 3. Global Variables
MOD_LOAD, MOD_NOLOAD, HELPABLE, cleanmode = [], ["subscene_dl"], {}, {}
botStartTime = time.time()
misskaty_version = "v2.16.1"
BOT_ID, BOT_NAME, BOT_USERNAME = 0, "", ""
UBOT_ID, UBOT_NAME, UBOT_USERNAME = None, None, None

faulthandler_enable()

# 4. Smart Manual Patching (Fixes 'no_channel' and other custom args)
def manual_patch(client_class):
    if not hasattr(client_class, "on_cmd"):
        def on_cmd(self, command, group=0, *args, **kwargs):
            # Filtering out custom arguments that pyrogram's command filter doesn't support
            valid_args = ["prefixes", "case_sensitive"]
            cmd_args = {k: v for k, v in kwargs.items() if k in valid_args}
            return self.on_message(filters.command(command, **cmd_args), group)
        client_class.on_cmd = on_cmd

manual_patch(Client)

# 5. Initialize Clients
app = Client(
    "HexaFinalV7",
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

# 6. Web Server Function
async def run_wsgi():
    config = uvicorn.Config(api, host="0.0.0.0", port=int(PORT))
    server = uvicorn.Server(config)
    await server.serve()

# 7. Start Logic
async def start_everything():
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

# Execute
loop.run_until_complete(start_everything())
print(f"DONE! STARTED AS @{BOT_USERNAME}")

# 8. Scheduler
jobstores = {"default": MongoDBJobStore(client=MongoClient(DATABASE_URI), database=DATABASE_NAME, collection="nightmode")}
scheduler = AsyncIOScheduler(jobstores=jobstores, timezone=TZ)
