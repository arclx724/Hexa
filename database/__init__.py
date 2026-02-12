"""
* @author        yasir <yasiramunandar@gmail.com>
* @date          2022-09-06 10:12:09
* @projectName   MissKatyPyro
* Copyright @YasirPedia All rights reserved
"""

from motor.motor_asyncio import AsyncIOMotorClient

from misskaty.vars import DATABASE_NAME, DATABASE_URI

mongo = AsyncIOMotorClient(DATABASE_URI)
dbname = mongo[DATABASE_NAME]
