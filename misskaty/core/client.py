from pyrogram import Client

from database import Database


class MissKatyClient(Client):
    def __init__(self, *args, database: Database, **kwargs):
        super().__init__(*args, **kwargs)
        self.database = database
        self.db = database.db
