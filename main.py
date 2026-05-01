import os
import discord
from discord.ext import commands
import yt_dlp as youtube_dl
import asyncio

# ============================
# CONFIGURATION
# ============================
TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise ValueError("No DISCORD_TOKEN found in environment variables")

PREFIX = "K!"

COOKIES_FILE = "/app/cookies.txt"

# yt-dlp options
# ios/android clients bypass YouTube's JS challenge — no Node.js runtime needed
YDL_OPTIONS = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'quiet': True,
    'default_search': 'ytsearch',
    'extract_flat': False,
    'cookiefile': COOKIES_FILE if os.path.exists(COOKIES_FILE) else None,
    'extractor_args': {
        'youtube': {
            'player_client': ['tv_embedded', 'web_embedded', 'web_creator'],
        }
    },
    'http_headers': {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
}

# FFmpeg options — reconnect flags must be in before_options
FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}

# ============================
# MUSIC QUEUE MANAGER
# ============================
class MusicQueue:
    def __init__(self):
        self.queue = []
        self.current = None

    def add(self, song):
        self.queue.append(song)

    def get_next(self):
        if self.queue:
            self.current = self.queue.pop(0)
            return self.current
        self.current = None
        return None

    def clear(self):
        self.queue.clear()
        self.current = None

    def remove(self, index):
        if 0 <= index < len(self.queue):
            return self.queue.pop(index)

    def is_empty(self):
        return len(self.queue) == 0 and self.current is None

    def get_queue_list(self):
        return self.queue.copy()


# ============================
# BOT SETUP
# ============================
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix=PREFIX, intents=intents, help_command=None)

queues = {}


def get_queue(guild_id):
    if guild_id not in queues:
        queues[guild_id] = MusicQueue()
    return queues[guild_id]


# ============================
# HELPER FUNCTIONS
# ============================
async def play_next(ctx, error=None):
    if error:
        print(f"Playback error: {error}")

    guild_id = ctx.guild.id
    queue = get_queue(guild_id)
    voice_client = ctx.voice_client

    if not voice_client or not voice_client.is_connected():
        return

    next_song = queue.get_next()
    if next_song:
        source = await get_audio_source(next_song['url'])
        if source:
            def after_playing(e):
                coro = play_next(ctx, e)
                asyncio.run_coroutine_threadsafe(coro, bot.loop)

            voice_client.play(source, after=after_playing)

            duration = next_song.get('duration', 0)
            if isinstance(duration, int):
                minutes, seconds = divmod(duration, 60)
                duration_str = f"{minutes}:{seconds:02d}"
            else:
                duration_str = str(duration)

            embed = discord.Embed(title="🎵 Now Playing", color=discord.Color.green())
            embed.add_field(name="Title", value=next_song['title'], inline=False)
            embed.add_field(name="Duration", value=duration_str, inline=True)
            embed.add_field(name="Requested by", value=next_song.get('requester', 'Unknown'), inline=True)
            await ctx.send(embed=embed)
        else:
            await ctx.send("❌ Failed to load the audio stream. Skipping...")
            await play_next(ctx)
    else:
        # Wait 5 minutes then auto-disconnect if idle
        await asyncio.sleep(300)
        if voice_client and voice_client.is_connected() and not voice_client.is_playing():
            await voice_client.disconnect()
            if guild_id in queues:
                del queues[guild_id]
            await ctx.send("👋 Queue empty. Left voice channel due to inactivity.")


async def get_audio_source(url):
    try:
        loop = asyncio.get_event_loop()
        with youtube_dl.YoutubeDL(YDL_OPTIONS) as ydl:
            info = await loop.run_in_executor(None, lambda: ydl.extract_info(url, download=False))
            if 'entries' in info:
                info = info['entries'][0]
            audio_url = info['url']
            return discord.FFmpegPCMAudio(audio_url, **FFMPEG_OPTIONS)
    except Exception as e:
        print(f"Error extracting audio: {e}")
        return None


async def get_song_info(query, requester):
    try:
        loop = asyncio.get_event_loop()
        with youtube_dl.YoutubeDL(YDL_OPTIONS) as ydl:
            info = await loop.run_in_executor(None, lambda: ydl.extract_info(query, download=False))
            if 'entries' in info:
                info = info['entries'][0]
    except Exception as e:
        print(f"Error fetching song info: {e}")
        return None

    return {
        'title': info.get('title', 'Unknown'),
        'duration': info.get('duration', 0),
        'url': info.get('webpage_url', info.get('url')),
        'requester': requester
    }


# ============================
# COMMANDS
# ============================
@bot.command(name='p', aliases=['play'])
async def play(ctx, *, query):
    if not ctx.author.voice:
        await ctx.send("❌ You are not connected to a voice channel.")
        return

    voice_channel = ctx.author.voice.channel
    voice_client = ctx.voice_client

    if not voice_client:
        voice_client = await voice_channel.connect()
    elif voice_client.channel != voice_channel:
        await voice_client.move_to(voice_channel)

    async with ctx.typing():
        song = await get_song_info(query, ctx.author.display_name)

    if not song:
        await ctx.send("❌ Could not find that song. Please try another.")
        return

    queue = get_queue(ctx.guild.id)
    queue.add(song)

    if not voice_client.is_playing() and not voice_client.is_paused():
        await play_next(ctx)
    else:
        await ctx.send(f"✅ Added to queue: **{song['title']}**")


@bot.command(name='pause')
async def pause(ctx):
    voice_client = ctx.voice_client
    if voice_client and voice_client.is_playing():
        voice_client.pause()
        await ctx.send("⏸ Paused. Use `K!resume` to continue.")
    else:
        await ctx.send("❌ Nothing is playing right now.")


@bot.command(name='resume')
async def resume(ctx):
    voice_client = ctx.voice_client
    if voice_client and voice_client.is_paused():
        voice_client.resume()
        await ctx.send("▶️ Resumed.")
    else:
        await ctx.send("❌ The player is not paused or nothing is playing.")


@bot.command(name='skip')
async def skip(ctx):
    voice_client = ctx.voice_client
    if voice_client and (voice_client.is_playing() or voice_client.is_paused()):
        voice_client.stop()
        await ctx.send("⏭ Skipped current song.")
    else:
        await ctx.send("❌ No song is currently playing.")


@bot.command(name='queue', aliases=['q'])
async def show_queue(ctx):
    queue = get_queue(ctx.guild.id)
    queue_list = queue.get_queue_list()

    if not queue_list and not queue.current:
        await ctx.send("📭 The queue is empty.")
        return

    embed = discord.Embed(title="🎶 Music Queue", color=discord.Color.blue())
    description = ""

    if queue.current:
        description += f"**Now Playing:** {queue.current['title']} (requested by {queue.current['requester']})\n\n"

    if queue_list:
        description += "**Up Next:**\n"
        for i, song in enumerate(queue_list[:10], 1):
            description += f"`{i}.` **{song['title']}** — {song['requester']}\n"
        if len(queue_list) > 10:
            description += f"\n... and {len(queue_list) - 10} more."

    embed.description = description
    await ctx.send(embed=embed)


@bot.command(name='remove', aliases=['rm'])
async def remove(ctx, index: int):
    queue = get_queue(ctx.guild.id)
    removed = queue.remove(index - 1)  # user uses 1-based index
    if removed:
        await ctx.send(f"🗑 Removed: **{removed['title']}**")
    else:
        await ctx.send("❌ Invalid queue position.")


@bot.command(name='stop')
async def stop(ctx):
    voice_client = ctx.voice_client
    if voice_client:
        get_queue(ctx.guild.id).clear()
        voice_client.stop()
        await ctx.send("⏹ Stopped playback and cleared the queue.")
    else:
        await ctx.send("❌ I'm not connected to a voice channel.")


@bot.command(name='now', aliases=['np'])
async def now_playing(ctx):
    queue = get_queue(ctx.guild.id)
    if queue.current:
        duration = queue.current.get('duration', 0)
        if isinstance(duration, int):
            minutes, seconds = divmod(duration, 60)
            duration_str = f"{minutes}:{seconds:02d}"
        else:
            duration_str = str(duration)

        embed = discord.Embed(title="🎵 Now Playing", color=discord.Color.green())
        embed.add_field(name="Title", value=queue.current['title'], inline=False)
        embed.add_field(name="Duration", value=duration_str, inline=True)
        embed.add_field(name="Requested by", value=queue.current.get('requester', 'Unknown'), inline=True)
        await ctx.send(embed=embed)
    else:
        await ctx.send("❌ No song is currently playing.")


@bot.command(name='leave', aliases=['disconnect', 'dc'])
async def leave(ctx):
    voice_client = ctx.voice_client
    if voice_client:
        get_queue(ctx.guild.id).clear()
        await voice_client.disconnect()
        if ctx.guild.id in queues:
            del queues[ctx.guild.id]
        await ctx.send("👋 Disconnected from voice channel.")
    else:
        await ctx.send("❌ I'm not in a voice channel.")


@bot.command(name='join')
async def join(ctx):
    if ctx.author.voice:
        await ctx.author.voice.channel.connect()
        await ctx.send("✅ Joined voice channel!")
    else:
        await ctx.send("❌ You are not in a voice channel.")


@bot.command(name='help', aliases=['h'])
async def help_command(ctx):
    embed = discord.Embed(
        title="🎵 Kbot Music Commands",
        description=f"Prefix: `{PREFIX}`",
        color=discord.Color.purple()
    )
    commands_list = [
        ("`K!p <song>`", "Play a song or add to queue"),
        ("`K!pause`", "Pause playback"),
        ("`K!resume`", "Resume playback"),
        ("`K!skip`", "Skip the current song"),
        ("`K!stop`", "Stop and clear the queue"),
        ("`K!queue` / `K!q`", "Show the current queue"),
        ("`K!now` / `K!np`", "Show the current song"),
        ("`K!remove <#>`", "Remove a song from the queue"),
        ("`K!join`", "Join your voice channel"),
        ("`K!leave`", "Leave the voice channel"),
    ]
    for name, value in commands_list:
        embed.add_field(name=name, value=value, inline=False)
    await ctx.send(embed=embed)


# ============================
# EVENTS
# ============================
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ Missing argument. Usage: `{ctx.prefix}{ctx.command.name} {ctx.command.signature}`")
    else:
        await ctx.send(f"⚠️ An error occurred: {str(error)}")
        print(f"Error: {error}")


@bot.event
async def on_ready():
    print(f"✅ {bot.user} connected to Discord!")
    print(f"   Prefix: {PREFIX}")
    print(f"   Cookies: {'found' if os.path.exists(COOKIES_FILE) else 'NOT FOUND — YouTube may block requests'}")
    await bot.change_presence(activity=discord.Game(name=f"{PREFIX}p <song>"))


# ============================
# RUN BOT
# ============================
if __name__ == "__main__":
    bot.run(TOKEN)
