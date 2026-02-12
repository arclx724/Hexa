# This plugin to learn session using pyrogram
from pyrogram.types import Message

from misskaty import app
from misskaty.core.listener_errors import ListenerTimeout


@app.on_cmd("session")
async def session(_, ctx: Message):
    try:
        nama = await ctx.ask("Ketik nama kamu:", timeout=60)
        umur = await ctx.ask("Ketik umur kamu", timeout=60)
        alamat = await ctx.ask("Ketik alamat kamu:", timeout=60)
    except ListenerTimeout:
        return await ctx.reply_msg("Session expired, silakan ulangi /session")

    await app.send_msg(
        ctx.chat.id,
        f"Nama Kamu Adalah: {nama.text}\nUmur Kamu Adalah: {umur.text}\nAlamat Kamu Adalah: {alamat.text}",
    )
