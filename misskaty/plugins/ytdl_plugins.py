# * @author        Yasir Aris M <yasiramunandar@gmail.com>
# * @date          2023-06-21 22:12:27
# * @projectName   MissKatyPyro
# * Copyright ©YasirPedia All rights reserved
import asyncio
import os
import time
from pathlib import Path
from logging import getLogger
from uuid import uuid4

from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.errors import MessageNotModified, QueryIdInvalid, WebpageMediaEmpty
from pyrogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, Message
from yt_dlp import DownloadError, YoutubeDL

from misskaty import app
from misskaty.core import pyro_cooldown
from misskaty.core.decorator import capture_err, new_task
from misskaty.helper import fetch, isValidURL, use_chat_lang
from misskaty.helper.pyro_progress import humanbytes, time_formatter
from misskaty.vars import COMMAND_HANDLER

LOGGER = getLogger("MissKaty")
YT_REGEX = r"^(https?://)?(www\.)?(youtube|youtu|youtube-nocookie)\.(com|be)/(watch\?v=|embed/|v/|.+\?v=)?(?P<id>[A-Za-z0-9\-=_]{11})"
YT_DB = {}
YTDL_CACHE = {}
ACTIVE_DOWNLOADS = {}


class DownloadCancelled(Exception):
    """Raised when user cancels active yt-dlp task."""


def rand_key() -> str:
    return str(uuid4())[:8]


def format_progress_bar(percentage: float) -> str:
    filled = max(0, min(20, int(percentage // 5)))
    return f"[{'●' * filled}{'○' * (20 - filled)}]"




def get_cookie_file() -> str | None:
    cookie_file = Path("cookies.txt")
    return str(cookie_file) if cookie_file.is_file() else None


def build_ydl_opts(extra: dict | None = None) -> dict:
    opts = {
        "quiet": True,
        "no_warnings": True,
        "js_runtimes": {"deno": {"path": "/root/.deno/bin/deno"}},
    }
    if cookie_file := get_cookie_file():
        opts["cookiefile"] = cookie_file
    if extra:
        opts.update(extra)
    return opts

def resolve_downloaded_file(output_dir: str, job_id: str, expected_ext: str | None = None) -> str | None:
    candidates = sorted(Path(output_dir).glob(f"{job_id}.*"), key=lambda x: x.stat().st_mtime, reverse=True)
    if expected_ext:
        for file in candidates:
            if file.suffix.lower() == f".{expected_ext.lower()}":
                return str(file)
    return str(candidates[0]) if candidates else None


def parse_video_options(info: dict) -> list[dict]:
    options = []
    seen = set()
    formats = info.get("formats") or []
    heights = sorted({f.get("height") for f in formats if f.get("height")}, reverse=True)
    for height in heights:
        if height in seen:
            continue
        seen.add(height)
        options.append(
            {
                "label": f"🎬 {height}p",
                "kind": "video",
                "format": f"bestvideo[height<={height}]+bestaudio/best[height<={height}]",
                "ext": "mp4",
            }
        )
        if len(options) >= 6:
            break
    for bitrate in (320, 192, 128):
        options.append(
            {
                "label": f"🎧 Audio MP3 {bitrate}kbps",
                "kind": "audio",
                "format": "bestaudio/best",
                "ext": "mp3",
                "bitrate": str(bitrate),
            }
        )
    return options


async def yt_extract(url: str, flat: bool = False) -> dict:
    def _extract():
        opts = build_ydl_opts({"skip_download": True})
        if flat:
            opts["extract_flat"] = "in_playlist"
        with YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=False)

    return await asyncio.to_thread(_extract)


@app.on_cmd("ytsearch", no_channel=True)
@use_chat_lang()
async def ytsearch(_, ctx: Message, strings):
    if len(ctx.command) == 1:
        return await ctx.reply(strings("no_query"))
    query = ctx.text.split(maxsplit=1)[1]
    search_key = rand_key()
    search = await yt_extract(f"ytsearch10:{query}", flat=True)
    results = search.get("entries") or []
    if not results:
        return await ctx.reply(strings("no_res").format(kweri=query))
    YT_DB[search_key] = {"query": query, "results": results}
    i = results[0]
    out = strings("yts_msg").format(
        pub=i.get("upload_date") or "-",
        dur=time_formatter(i.get("duration") or 0),
        vi=humanbytes(i.get("view_count") or 0),
        clink=i.get("channel_url") or i.get("uploader_url") or "https://youtube.com",
        cname=i.get("channel") or i.get("uploader") or "Unknown",
    )
    btn = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(f"1/{len(results)}", callback_data=f"ytdl_scroll|{search_key}|0")],
            [InlineKeyboardButton(strings("dl_btn"), callback_data=f"yt_gen|{search_key}|0")],
        ]
    )
    img = await get_ytthumb(i.get("id"))
    await ctx.reply_photo(img, caption=out, reply_markup=btn, parse_mode=ParseMode.HTML)


@app.on_message(
    filters.command(["ytdown"], COMMAND_HANDLER)
    | filters.regex(YT_REGEX)
    & ~filters.channel
    & ~filters.via_bot
    & pyro_cooldown.wait(60)
)
@capture_err
@use_chat_lang()
async def ytdownv2(_, ctx: Message, strings):
    if not ctx.from_user:
        return await ctx.reply(strings("no_channel"))
    url = ctx.command[1] if ctx.command and len(ctx.command) > 1 else ctx.text or ctx.caption
    if not isValidURL(url):
        return await ctx.reply(strings("invalid_link"))

    try:
        info = await yt_extract(url)
    except Exception as err:
        return await ctx.reply(f"{strings('err_parse')}\n\n<code>{err}</code>", parse_mode=ParseMode.HTML)

    title = info.get("title") or "Untitled"
    thumb = info.get("thumbnail") or "assets/thumb.jpg"
    options = parse_video_options(info)
    cache_key = rand_key()
    YTDL_CACHE[cache_key] = {
        "url": url,
        "title": title,
        "thumb": thumb,
        "options": options,
        "user_id": ctx.from_user.id,
    }

    rows = []
    for idx, opt in enumerate(options):
        rows.append([InlineKeyboardButton(opt["label"], callback_data=f"yt_dl|{cache_key}|{idx}")])
    caption = f"<b>{title}</b>\n\nChoose output quality:"  # noqa: E501
    markup = InlineKeyboardMarkup(rows)
    try:
        await ctx.reply_photo(thumb, caption=caption, reply_markup=markup, parse_mode=ParseMode.HTML)
    except WebpageMediaEmpty:
        await ctx.reply_photo("assets/thumb.jpg", caption=caption, reply_markup=markup, parse_mode=ParseMode.HTML)


@app.on_callback_query(filters.regex(r"^yt_dl\|"))
@use_chat_lang()
@new_task
async def ytdl_download_callback(self: Client, cq: CallbackQuery, strings):
    callback = cq.data.split("|")
    cache_key = callback[1]
    index = int(callback[2])
    data = YTDL_CACHE.get(cache_key)
    if not data:
        return await cq.answer("Task expired", show_alert=True)
    if cq.from_user.id != data["user_id"]:
        return await cq.answer(strings("unauth"), True)

    option = data["options"][index]
    job_id = rand_key()
    ACTIVE_DOWNLOADS[job_id] = {
        "cancelled": False,
        "downloaded": 0,
        "total": 0,
        "speed": 0,
        "eta": 0,
        "stage": "download",
    }
    cancel_markup = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data=f"yt_cancel|{job_id}")]])

    try:
        await cq.edit_message_caption(
            f"Preparing <b>{option['label']}</b>...",
            parse_mode=ParseMode.HTML,
            reply_markup=cancel_markup,
        )
    except MessageNotModified:
        pass

    output_dir = "downloads"
    os.makedirs(output_dir, exist_ok=True)
    file_path = os.path.join(output_dir, f"{job_id}.%(ext)s")

    def progress_hook(status):
        state = ACTIVE_DOWNLOADS.get(job_id)
        if not state:
            return
        if state["cancelled"]:
            raise DownloadCancelled("Cancelled by user")
        if status.get("status") == "downloading":
            state["downloaded"] = status.get("downloaded_bytes") or 0
            state["total"] = status.get("total_bytes") or status.get("total_bytes_estimate") or 0
            state["speed"] = status.get("speed") or 0
            state["eta"] = status.get("eta") or 0
        elif status.get("status") == "finished":
            state["stage"] = "upload"

    def do_download():
        ydl_opts = build_ydl_opts({
            "outtmpl": file_path,
            "noprogress": True,
            "format": option["format"],
            "progress_hooks": [progress_hook],
            "merge_output_format": "mp4",
        })
        if option["kind"] == "audio":
            ydl_opts["postprocessors"] = [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": option.get("bitrate", "192"),
            }]
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(data["url"], download=True)
            return ydl.prepare_filename(info)

    download_task = asyncio.create_task(asyncio.to_thread(do_download))
    status_text = ""

    while not download_task.done():
        state = ACTIVE_DOWNLOADS[job_id]
        total = state["total"] or 1
        percentage = (state["downloaded"] / total) * 100 if state["total"] else 0
        text = (
            f"⬇️ Downloading <b>{option['label']}</b>\n"
            f"{format_progress_bar(percentage)} {percentage:.2f}%\n"
            f"{humanbytes(state['downloaded'])} / {humanbytes(state['total'])}\n"
            f"Speed: {humanbytes(state['speed'])}/s\n"
            f"ETA: {time_formatter(int(state['eta'])) or 'Unknown'}"
        )
        if text != status_text:
            try:
                await cq.edit_message_caption(text, parse_mode=ParseMode.HTML, reply_markup=cancel_markup)
                status_text = text
            except (MessageNotModified, QueryIdInvalid):
                pass
        await asyncio.sleep(2)

    try:
        downloaded_file = await download_task
    except DownloadCancelled:
        ACTIVE_DOWNLOADS.pop(job_id, None)
        return await cq.edit_message_caption("❌ Download cancelled.")
    except DownloadError as err:
        ACTIVE_DOWNLOADS.pop(job_id, None)
        return await cq.edit_message_caption(f"❌ Download failed: <code>{err}</code>", parse_mode=ParseMode.HTML)
    except Exception as err:
        ACTIVE_DOWNLOADS.pop(job_id, None)
        return await cq.edit_message_caption(f"❌ Download error: <code>{err}</code>", parse_mode=ParseMode.HTML)

    if "%" in downloaded_file or not os.path.exists(downloaded_file):
        downloaded_file = resolve_downloaded_file(output_dir, job_id, option.get("ext"))
    if not downloaded_file or not os.path.exists(downloaded_file):
        ACTIVE_DOWNLOADS.pop(job_id, None)
        return await cq.edit_message_caption("❌ Downloaded file not found.")

    ACTIVE_DOWNLOADS[job_id]["stage"] = "upload"
    start = time.time()

    async def upload_progress(current, total):
        state = ACTIVE_DOWNLOADS.get(job_id)
        if not state:
            return
        if state["cancelled"]:
            raise DownloadCancelled("Cancelled by user")
        percentage = current * 100 / total if total else 0
        text = (
            f"⬆️ Uploading <b>{os.path.basename(downloaded_file)}</b>\n"
            f"{format_progress_bar(percentage)} {percentage:.2f}%\n"
            f"{humanbytes(current)} / {humanbytes(total)}\n"
            f"Elapsed: {time_formatter(int(time.time() - start)) or '0 seconds'}"
        )
        try:
            await cq.edit_message_caption(text, parse_mode=ParseMode.HTML, reply_markup=cancel_markup)
        except (MessageNotModified, QueryIdInvalid):
            pass

    try:
        if option["kind"] == "audio":
            await self.send_audio(
                cq.message.chat.id,
                downloaded_file,
                caption=data["title"],
                progress=upload_progress,
            )
        else:
            await self.send_video(
                cq.message.chat.id,
                downloaded_file,
                caption=data["title"],
                supports_streaming=True,
                progress=upload_progress,
            )
        await cq.edit_message_caption("✅ Done.")
    except DownloadCancelled:
        await cq.edit_message_caption("❌ Upload cancelled.")
    finally:
        ACTIVE_DOWNLOADS.pop(job_id, None)
        if os.path.exists(downloaded_file):
            os.remove(downloaded_file)


@app.on_callback_query(filters.regex(r"^yt_cancel\|"))
@use_chat_lang()
async def ytdl_cancel_callback(_, cq: CallbackQuery, strings):
    callback = cq.data.split("|")
    job_id = callback[1]
    task = ACTIVE_DOWNLOADS.get(job_id)
    if not task:
        return await cq.answer("Task already finished", show_alert=True)
    task["cancelled"] = True
    try:
        await cq.answer("Cancelling task...")
    except QueryIdInvalid:
        pass


@app.on_callback_query(filters.regex(r"^ytdl_scroll"))
@use_chat_lang()
async def ytdl_scroll_callback(_, cq: CallbackQuery, strings):
    callback = cq.data.split("|")
    search_key = callback[1]
    page = int(callback[2])
    data = YT_DB.get(search_key)
    if not data:
        return await cq.answer("Search expired", show_alert=True)
    if cq.from_user.id != cq.message.reply_to_message.from_user.id:
        return await cq.answer(strings("unauth"), True)

    results = data["results"]
    if page < 0 or page > len(results) - 1:
        return await cq.answer(strings("endlist"), show_alert=True)
    i = results[page]
    out = strings("yts_msg").format(
        pub=i.get("upload_date") or "-",
        dur=time_formatter(i.get("duration") or 0),
        vi=humanbytes(i.get("view_count") or 0),
        clink=i.get("channel_url") or i.get("uploader_url") or "https://youtube.com",
        cname=i.get("channel") or i.get("uploader") or "Unknown",
    )

    scroll_btn = [[]]
    if page > 0:
        scroll_btn[0].append(InlineKeyboardButton(strings("back"), callback_data=f"ytdl_scroll|{search_key}|{page - 1}"))
    scroll_btn[0].append(InlineKeyboardButton(f"{page + 1}/{len(results)}", callback_data=f"ytdl_scroll|{search_key}|{page}"))
    if page < len(results) - 1:
        scroll_btn[0].append(InlineKeyboardButton("Next", callback_data=f"ytdl_scroll|{search_key}|{page + 1}"))

    btn = InlineKeyboardMarkup(scroll_btn + [[InlineKeyboardButton(strings("dl_btn"), callback_data=f"yt_gen|{search_key}|{page}")]])
    await cq.edit_message_media(InputMediaPhoto(await get_ytthumb(i.get("id")), caption=out), reply_markup=btn)


@app.on_callback_query(filters.regex(r"^yt_gen\|"))
@use_chat_lang()
async def ytdl_gen_from_search(_, cq: CallbackQuery, strings):
    callback = cq.data.split("|")
    search_key = callback[1]
    page = int(callback[2])
    data = YT_DB.get(search_key)
    if not data:
        return await cq.answer("Search expired", show_alert=True)
    if cq.from_user.id != cq.message.reply_to_message.from_user.id:
        return await cq.answer(strings("unauth"), True)

    entry = data["results"][page]
    url = entry.get("url") or entry.get("webpage_url")
    if not url:
        url = f"https://www.youtube.com/watch?v={entry.get('id')}"
    info = await yt_extract(url)

    options = parse_video_options(info)
    cache_key = rand_key()
    YTDL_CACHE[cache_key] = {
        "url": url,
        "title": info.get("title") or entry.get("title") or "Untitled",
        "thumb": info.get("thumbnail") or "assets/thumb.jpg",
        "options": options,
        "user_id": cq.from_user.id,
    }
    rows = [[InlineKeyboardButton(opt["label"], callback_data=f"yt_dl|{cache_key}|{idx}")] for idx, opt in enumerate(options)]
    await cq.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(rows))


async def get_ytthumb(videoid: str | None):
    if not videoid:
        return "https://i.imgur.com/4LwPLai.png"
    thumb_quality = ["maxresdefault.jpg", "hqdefault.jpg", "sddefault.jpg", "mqdefault.jpg", "default.jpg"]
    thumb_link = "https://i.imgur.com/4LwPLai.png"
    for quality in thumb_quality:
        link = f"https://i.ytimg.com/vi/{videoid}/{quality}"
        if (await fetch.get(link)).status_code == 200:
            thumb_link = link
            break
    return thumb_link
