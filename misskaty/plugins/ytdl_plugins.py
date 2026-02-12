# * @author        Yasir Aris M <yasiramunandar@gmail.com>
# * @date          2023-06-21 22:12:27
# * @projectName   MissKatyPyro
# * Copyright ©YasirPedia All rights reserved
import asyncio
import os
import time
from pathlib import Path
from uuid import uuid4

from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.errors import MessageNotModified, QueryIdInvalid, WebpageMediaEmpty
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaAudio,
    InputMediaPhoto,
    InputMediaVideo,
    Message,
)
from yt_dlp import DownloadError, YoutubeDL

from misskaty import app
from misskaty.core import pyro_cooldown
from misskaty.core.decorator import capture_err, new_task
from misskaty.helper import fetch, isValidURL, use_chat_lang
from misskaty.helper.pyro_progress import humanbytes, time_formatter
from misskaty.vars import COMMAND_HANDLER

YT_REGEX = r"^(https?://)?(www\.)?(youtube|youtu|youtube-nocookie)\.(com|be)/(watch\?v=|embed/|v/|.+\?v=)?(?P<id>[A-Za-z0-9\-=_]{11})"
YT_DB = {}
YTDL_CACHE = {}
ACTIVE_DOWNLOADS = {}


class DownloadCancelled(Exception):
    pass


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


def parse_quality_tree(info: dict) -> dict:
    formats = info.get("formats") or []
    resolutions = {}

    for target_height in (1080, 720, 480, 360, 240):
        candidates = []
        for fmt in formats:
            height = int(fmt.get("height") or 0)
            if height != target_height:
                continue
            if fmt.get("vcodec") in (None, "none"):
                continue
            tbr = int(fmt.get("tbr") or fmt.get("vbr") or 0)
            format_id = str(fmt.get("format_id"))
            selector = format_id
            if fmt.get("acodec") in (None, "none"):
                selector = f"{format_id}+bestaudio/best"
            candidates.append(
                {
                    "label": f"{tbr}kbps" if tbr else "Auto bitrate",
                    "format": selector,
                    "bitrate": tbr,
                    "kind": "video",
                    "ext": "mp4",
                }
            )
        if candidates:
            unique = {}
            for c in candidates:
                key = c["bitrate"] // 50 if c["bitrate"] else -1
                if key not in unique or c["bitrate"] > unique[key]["bitrate"]:
                    unique[key] = c
            resolutions[str(target_height)] = sorted(unique.values(), key=lambda x: x["bitrate"], reverse=True)[:5]

    audio = [
        {"label": "320kbps", "format": "bestaudio/best", "kind": "audio", "ext": "mp3", "bitrate": "320"},
        {"label": "192kbps", "format": "bestaudio/best", "kind": "audio", "ext": "mp3", "bitrate": "192"},
        {"label": "128kbps", "format": "bestaudio/best", "kind": "audio", "ext": "mp3", "bitrate": "128"},
    ]
    return {"resolutions": resolutions, "audio": audio}




async def animate_processing(message: Message, title: str, stop_event: asyncio.Event):
    frames = ["😺", "😸", "😹", "😻"]
    idx = 0
    while not stop_event.is_set():
        text = f"{frames[idx % len(frames)]} {title}"
        try:
            if message.media:
                await message.edit_caption(text)
            else:
                await message.edit_text(text)
        except Exception:
            pass
        idx += 1
        await asyncio.sleep(1.2)


async def yt_extract(url: str, flat: bool = False) -> dict:
    def _extract():
        opts = build_ydl_opts({"skip_download": True})
        if flat:
            opts["extract_flat"] = "in_playlist"
        with YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=False)

    return await asyncio.to_thread(_extract)


async def download_thumb_file(url: str | None, job_id: str, output_dir: str) -> str | None:
    if not url:
        return None
    try:
        response = await fetch.get(url)
        if response.status_code != 200:
            return None
        thumb_path = os.path.join(output_dir, f"{job_id}_thumb.jpg")
        with open(thumb_path, "wb") as file:
            file.write(response.content)
        return thumb_path
    except Exception:
        return None


def quality_markup(cache_key: str, tree: dict) -> InlineKeyboardMarkup:
    rows = []
    for res in tree["resolutions"].keys():
        rows.append([InlineKeyboardButton(f"🎬 {res}p", callback_data=f"yt_res|{cache_key}|{res}")])
    rows.append([InlineKeyboardButton("🎧 Audio MP3", callback_data=f"yt_audio|{cache_key}")])
    return InlineKeyboardMarkup(rows)


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
    await ctx.reply_photo(await get_ytthumb(i.get("id")), caption=out, reply_markup=btn, parse_mode=ParseMode.HTML)


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

    progress_msg = await ctx.reply("😺 Processing yt-dlp data...")
    stop_event = asyncio.Event()
    anim_task = asyncio.create_task(animate_processing(progress_msg, "Processing yt-dlp data...", stop_event))
    try:
        info = await yt_extract(url)
    except Exception as err:
        stop_event.set()
        await anim_task
        return await progress_msg.edit_text(f"{strings('err_parse')}\n\n<code>{err}</code>", parse_mode=ParseMode.HTML)
    finally:
        stop_event.set()
        await anim_task

    cache_key = rand_key()
    tree = parse_quality_tree(info)
    YTDL_CACHE[cache_key] = {
        "url": url,
        "title": info.get("title") or "Untitled",
        "thumb": info.get("thumbnail") or "assets/thumb.jpg",
        "duration": int(info.get("duration") or 0),
        "quality_tree": tree,
        "user_id": ctx.from_user.id,
    }

    caption = f"<b>{YTDL_CACHE[cache_key]['title']}</b>\n\n1) Select resolution\n2) Select bitrate"
    markup = quality_markup(cache_key, tree)
    try:
        await progress_msg.edit_media(
            InputMediaPhoto(YTDL_CACHE[cache_key]["thumb"], caption=caption, parse_mode=ParseMode.HTML),
            reply_markup=markup,
        )
    except WebpageMediaEmpty:
        await progress_msg.edit_media(
            InputMediaPhoto("assets/thumb.jpg", caption=caption, parse_mode=ParseMode.HTML),
            reply_markup=markup,
        )


@app.on_callback_query(filters.regex(r"^yt_(res|audio)\|"))
@use_chat_lang()
async def ytdl_pick_step(_, cq: CallbackQuery, strings):
    callback = cq.data.split("|")
    action, cache_key = callback[0], callback[1]
    data = YTDL_CACHE.get(cache_key)
    if not data:
        return await cq.answer("Task expired", show_alert=True)
    if cq.from_user.id != data["user_id"]:
        return await cq.answer(strings("unauth"), True)

    if action == "yt_res":
        res = callback[2]
        options = data["quality_tree"]["resolutions"].get(res, [])
        if not options:
            return await cq.answer("No bitrate option for this resolution", show_alert=True)
        rows = [
            [InlineKeyboardButton(f"{opt['label']}", callback_data=f"yt_dl|{cache_key}|v|{res}|{idx}")]
            for idx, opt in enumerate(options)
        ]
        rows.append([InlineKeyboardButton("⬅️ Back", callback_data=f"yt_back|{cache_key}")])
        return await cq.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(rows))

    rows = [
        [InlineKeyboardButton(f"🎧 {opt['label']}", callback_data=f"yt_dl|{cache_key}|a|{opt['bitrate']}")]
        for opt in data["quality_tree"]["audio"]
    ]
    rows.append([InlineKeyboardButton("⬅️ Back", callback_data=f"yt_back|{cache_key}")])
    await cq.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(rows))


@app.on_callback_query(filters.regex(r"^yt_back\|"))
@use_chat_lang()
async def ytdl_back_choice(_, cq: CallbackQuery, strings):
    cache_key = cq.data.split("|")[1]
    data = YTDL_CACHE.get(cache_key)
    if not data:
        return await cq.answer("Task expired", show_alert=True)
    if cq.from_user.id != data["user_id"]:
        return await cq.answer(strings("unauth"), True)
    await cq.edit_message_reply_markup(reply_markup=quality_markup(cache_key, data["quality_tree"]))


@app.on_callback_query(filters.regex(r"^yt_dl\|"))
@use_chat_lang()
@new_task
async def ytdl_download_callback(self: Client, cq: CallbackQuery, strings):
    callback = cq.data.split("|")
    cache_key = callback[1]
    data = YTDL_CACHE.get(cache_key)
    if not data:
        return await cq.answer("Task expired", show_alert=True)
    if cq.from_user.id != data["user_id"]:
        return await cq.answer(strings("unauth"), True)

    if callback[2] == "v":
        res = callback[3]
        idx = int(callback[4])
        option = data["quality_tree"]["resolutions"][res][idx]
        label = f"{res}p • {option['label']}"
    else:
        bitrate = callback[3]
        option = {"kind": "audio", "ext": "mp3", "format": "bestaudio/best", "bitrate": bitrate}
        label = f"MP3 {bitrate}kbps"

    job_id = rand_key()
    ACTIVE_DOWNLOADS[job_id] = {"cancelled": False, "downloaded": 0, "total": 0, "speed": 0, "eta": 0}
    cancel_markup = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data=f"yt_cancel|{job_id}")]])

    try:
        await cq.edit_message_caption(f"Preparing <b>{label}</b>...", parse_mode=ParseMode.HTML, reply_markup=cancel_markup)
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

    def do_download():
        ydl_opts = build_ydl_opts({
            "outtmpl": file_path,
            "noprogress": True,
            "format": option["format"],
            "progress_hooks": [progress_hook],
            "merge_output_format": "mp4",
        })
        if option["kind"] == "audio":
            ydl_opts["postprocessors"] = [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": option.get("bitrate", "192")}]
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
            f"⬇️ Downloading <b>{label}</b>\n"
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
        await asyncio.sleep(7)

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

    start = time.time()
    last_upload_edit = 0.0
    thumb_file = await download_thumb_file(data.get("thumb"), job_id, output_dir)

    async def upload_progress(current, total):
        nonlocal last_upload_edit
        if ACTIVE_DOWNLOADS.get(job_id, {}).get("cancelled"):
            raise DownloadCancelled("Cancelled by user")
        now = time.time()
        if (now - last_upload_edit) < 7 and current != total:
            return
        last_upload_edit = now
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
            media = InputMediaAudio(
                media=downloaded_file,
                caption=data["title"],
                duration=data.get("duration") or None,
                title=data["title"],
                thumb=thumb_file,
            )
        else:
            media = InputMediaVideo(
                media=downloaded_file,
                caption=data["title"],
                duration=data.get("duration") or None,
                thumb=thumb_file,
                supports_streaming=True,
            )
        await upload_progress(0, 1)
        await self.edit_message_media(
            cq.message.chat.id,
            cq.message.id,
            media=media,
            reply_markup=None,
        )
    except DownloadCancelled:
        await cq.edit_message_caption("❌ Upload cancelled.")
    except Exception as err:
        await cq.edit_message_caption(f"❌ Upload failed: <code>{err}</code>", parse_mode=ParseMode.HTML)
    finally:
        ACTIVE_DOWNLOADS.pop(job_id, None)
        if os.path.exists(downloaded_file):
            os.remove(downloaded_file)
        if thumb_file and os.path.exists(thumb_file):
            os.remove(thumb_file)


@app.on_callback_query(filters.regex(r"^yt_cancel\|"))
@use_chat_lang()
async def ytdl_cancel_callback(_, cq: CallbackQuery, strings):
    job_id = cq.data.split("|")[1]
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
    url = entry.get("url") or entry.get("webpage_url") or f"https://www.youtube.com/watch?v={entry.get('id')}"

    stop_event = asyncio.Event()
    anim_task = asyncio.create_task(animate_processing(cq.message, "Fetching yt-dlp metadata...", stop_event))
    try:
        info = await yt_extract(url)
    finally:
        stop_event.set()
        await anim_task

    cache_key = rand_key()
    tree = parse_quality_tree(info)
    YTDL_CACHE[cache_key] = {
        "url": url,
        "title": info.get("title") or entry.get("title") or "Untitled",
        "thumb": info.get("thumbnail") or "assets/thumb.jpg",
        "duration": int(info.get("duration") or entry.get("duration") or 0),
        "quality_tree": tree,
        "user_id": cq.from_user.id,
    }
    await cq.edit_message_reply_markup(reply_markup=quality_markup(cache_key, tree))


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
