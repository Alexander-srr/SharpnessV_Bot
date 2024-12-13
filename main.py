import yt_dlp
import asyncio
import discord
import os
from dotenv import load_dotenv
from discord.ext import commands

# Загрузка переменных из файла .env
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# Проверяем и загружаем opus (для голосовых функций Discord)
if not discord.opus.is_loaded():
    discord.opus.load_opus('/usr/lib/x86_64-linux-gnu/libopus.so.0')

# Настройки бота
class MusicBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.messages = True
        intents.guilds = True
        intents.voice_states = True
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)
        self.queue = asyncio.Queue()  # Очередь треков
        self.now_playing = None  # Текущий трек
        self.volume = 0.5  # Громкость

    async def on_ready(self):
        print(f"Бот {self.user} запущен и готов!")

# Создаем экземпляр бота
bot = MusicBot()

# Команда !play для воспроизведения треков
@bot.command(name="play", help="Воспроизвести трек из YouTube по URL.")
async def play(ctx, url: str):
    # Подключение к голосовому каналу
    if not ctx.author.voice:
        await ctx.send("Вы должны находиться в голосовом канале, чтобы использовать эту команду.")
        return

    if not ctx.voice_client:
        await ctx.author.voice.channel.connect()

    # Загрузка трека с помощью yt_dlp
    ydl_opts = {
        'format': 'bestaudio/best',
        'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'}],
        'cookiefile': 'cookies.txt'
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            audio_url = info['url']
            title = info['title']

        # Добавляем трек в очередь
        await bot.queue.put((audio_url, title))
        await ctx.send(f"Трек добавлен в очередь: **{title}**")

        # Если ничего не играет, начинаем воспроизведение
        if not bot.now_playing:
            await play_next(ctx)

    except Exception as e:
        await ctx.send(f"Ошибка при загрузке трека: {e}")

# Воспроизведение следующего трека
async def play_next(ctx):
    if bot.queue.empty():
        bot.now_playing = None
        await ctx.send("Очередь пуста. Бот отключается.")
        await ctx.voice_client.disconnect()
        return

    audio_url, title = await bot.queue.get()
    bot.now_playing = title

    ffmpeg_options = {'options': f'-vn -filter:a "volume={bot.volume}"'}
    ctx.voice_client.stop()
    ctx.voice_client.play(
        discord.FFmpegPCMAudio(audio_url, **ffmpeg_options),
        after=lambda e: asyncio.run_coroutine_threadsafe(play_next(ctx), bot.loop)
    )

    await ctx.send(f"Сейчас играет: **{title}**")

# Команда !skip для пропуска текущего трека
@bot.command(name="skip", help="Пропустить текущий трек.")
async def skip(ctx):
    if not ctx.voice_client or not ctx.voice_client.is_playing():
        await ctx.send("Сейчас ничего не играет.")
        return

    ctx.voice_client.stop()
    await ctx.send("Текущий трек пропущен.")

# Команда !stop для отключения бота
@bot.command(name="stop", help="Остановить бота и отключиться от голосового канала.")
async def stop(ctx):
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        await ctx.send("Бот отключился от голосового канала.")

# Команда !pause для паузы
@bot.command(name="pause", help="Приостановить воспроизведение.")
async def pause(ctx):
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.pause()
        await ctx.send("Воспроизведение приостановлено.")

# Команда !resume для возобновления
@bot.command(name="resume", help="Возобновить воспроизведение.")
async def resume(ctx):
    if ctx.voice_client and ctx.voice_client.is_paused():
        ctx.voice_client.resume()
        await ctx.send("Воспроизведение возобновлено.")

# Запуск бота
bot.run(TOKEN)
