"""
* @author        yasir <yasiramunandar@gmail.com>
* @date          2022-09-06 10:12:09
* @projectName   MissKatyPyro
* Copyright @YasirPedia All rights reserved
"""

from pymongo import AsyncMongoClient

from misskaty.vars import DATABASE_NAME, DATABASE_URI

mongo = AsyncMongoClient(DATABASE_URI)
dbname = mongo[DATABASE_NAME]
