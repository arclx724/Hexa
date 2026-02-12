"""
* @author        yasir <yasiramunandar@gmail.com>
* @date          2022-09-06 10:12:09
* @projectName   MissKatyPyro
* Copyright @YasirPedia All rights reserved
"""

from pymongo import AsyncMongoClient

from misskaty.vars import DATABASE_NAME, DATABASE_URI


class Database:
    def __init__(self, uri: str, database_name: str):
        self.uri = uri
        self.database_name = database_name
        self.client = AsyncMongoClient(self.uri)
        self.db = self.client[self.database_name]

    async def ping(self):
        return await self.client.admin.command("ping")

    @staticmethod
    def _mask_uri(uri: str) -> str:
        if "@" not in uri:
            return uri
        head, tail = uri.rsplit("@", 1)
        if ":" in head:
            user = head.split(":", 1)[0]
            return f"{user}:***@{tail}"
        return f"***@{tail}"


mongo = Database(DATABASE_URI, DATABASE_NAME)
dbname = mongo.db
