"""
* @author        yasir <yasiramunandar@gmail.com>
* @date          2022-09-06 10:12:09
* @projectName   MissKatyPyro
* Copyright @YasirPedia All rights reserved
"""

from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from async_pymongo import AsyncClient

from misskaty.vars import DATABASE_NAME, DATABASE_URI


class Database:
    def __init__(self, uri: str, database_name: str, timeout_ms: int = 5000):
        self.uri = self._normalize_uri(uri)
        self.database_name = database_name
        self.client = AsyncClient(
            self.uri,
            serverSelectionTimeoutMS=timeout_ms,
            connectTimeoutMS=timeout_ms,
        )
        self.db = self.client[self.database_name]

    @staticmethod
    def _normalize_uri(uri: str) -> str:
        parsed = urlparse(uri)
        if parsed.scheme != "mongodb" or parsed.hostname not in {"localhost", "127.0.0.1"}:
            return uri

        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        query.setdefault("directConnection", "true")
        return urlunparse(parsed._replace(query=urlencode(query)))

    async def ping(self):
        return await self.client.admin.command("ping")


mongo = Database(DATABASE_URI, DATABASE_NAME)
dbname = mongo.db
