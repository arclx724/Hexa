from database import dbname

greetingdb = dbname["greetings"]


async def is_welcome(chat_id: int) -> bool:
    return bool(await greetingdb.find_one({"chat_id": chat_id}))


async def toggle_welcome(chat_id: int):
    if await is_welcome(chat_id):
        await greetingdb.delete_one({"chat_id": chat_id})
        return False
    else:
        await greetingdb.insert_one({"chat_id": chat_id})
        return True


async def get_welcome_data(chat_id: int):
    return await greetingdb.find_one({"chat_id": chat_id}) or {}


async def get_welcome_text(chat_id: int):
    data = await get_welcome_data(chat_id)
    return data.get("welcome_text")


async def set_welcome_text(chat_id: int, text: str):
    await greetingdb.update_one(
        {"chat_id": chat_id},
        {"$set": {"welcome_text": text}},
        upsert=True,
    )


async def reset_welcome_text(chat_id: int):
    await greetingdb.update_one({"chat_id": chat_id}, {"$unset": {"welcome_text": 1}})
