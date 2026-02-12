"""
* @author        yasir <yasiramunandar@gmail.com>
* @date          2022-09-06 10:12:09
* @projectName   MissKatyPyro
* Copyright @YasirPedia All rights reserved
"""

import os
import socket
from logging import getLogger
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from async_pymongo import AsyncClient

from misskaty.vars import DATABASE_NAME, DATABASE_URI

LOGGER = getLogger("MissKaty")


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
    def _is_resolvable(hostname: str) -> bool:
        try:
            socket.getaddrinfo(hostname, None)
            return True
        except OSError:
            return False

    @staticmethod
    def _mask_uri(uri: str) -> str:
        parsed = urlparse(uri)
        if "@" not in parsed.netloc:
            return uri
        auth, host = parsed.netloc.rsplit("@", 1)
        if ":" in auth:
            user, _ = auth.split(":", 1)
            auth = f"{user}:***"
        else:
            auth = "***"
        return urlunparse(parsed._replace(netloc=f"{auth}@{host}"))

    @classmethod
    def _normalize_uri(cls, uri: str) -> str:
        parsed = urlparse(uri)
        if parsed.scheme not in {"mongodb", "mongodb+srv"} or not parsed.hostname:
            return uri

        query = dict(parse_qsl(parsed.query, keep_blank_values=True))

        # Local single-node optimization.
        if parsed.scheme == "mongodb" and parsed.hostname in {"localhost", "127.0.0.1"}:
            query.setdefault("directConnection", "true")
            return urlunparse(parsed._replace(query=urlencode(query)))

        # Optional fallback (disabled by default) for unresolved local aliases.
        use_fallback = os.environ.get("DATABASE_LOCAL_FALLBACK", "false").lower() in {
            "1",
            "true",
            "yes",
        }
        if use_fallback and not cls._is_resolvable(parsed.hostname):
            netloc = parsed.netloc
            if "@" in netloc:
                auth, hostpart = netloc.rsplit("@", 1)
            else:
                auth, hostpart = "", netloc

            if ":" in hostpart:
                _, port = hostpart.rsplit(":", 1)
                hostpart = f"127.0.0.1:{port}"
            else:
                hostpart = "127.0.0.1"

            query.setdefault("directConnection", "true")
            fallback_netloc = f"{auth + '@' if auth else ''}{hostpart}"
            fallback_uri = urlunparse(
                parsed._replace(netloc=fallback_netloc, query=urlencode(query))
            )
            LOGGER.warning(
                "DATABASE_URI host '%s' tidak bisa di-resolve. Fallback ke local URI: %s",
                parsed.hostname,
                cls._mask_uri(fallback_uri),
            )
            return fallback_uri

        return uri

    async def ping(self):
        return await self.client.admin.command("ping")


mongo = Database(DATABASE_URI, DATABASE_NAME)
dbname = mongo.db
