import yt_dlp
import asyncio
import discord
import os
from dotenv import load_dotenv
from discord.ext import commands

# Указываем путь к opus библиотеке (если требуется)
discord.opus.load_opus('/opt/homebrew/lib/libopus.dylib')

# Загрузка переменных из файла .env
load_dotenv()

# Получение токена из переменной окружения
TOKEN = os.getenv("DISCORD_TOKEN")

# Настройки бота
class MusicBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.messages = True
        intents.guilds = True
        intents.voice_states = True
        super().__init__(command_prefix="!", intents=intents)
        self.queue = asyncio.Queue()  # Очередь треков
        self.now_playing = None  # Текущий трек
        self.volume = 0.5  # Громкость
        self.message_with_controls = None  # Сообщение с кнопками

    async def on_ready(self):
        print(f"Бот {self.user} запущен и готов!")
        try:
            synced = await self.tree.sync()  # Синхронизация Slash-команд
            print(f"Синхронизировано {len(synced)} команд (Slash-команды).")
        except Exception as e:
            print(f"Ошибка синхронизации команд: {e}")

bot = MusicBot()

# Команда /play с интерактивными кнопками
@bot.tree.command(name="play", description="Воспроизвести трек из URL.")
async def play(interaction: discord.Interaction, url: str):
    # Подключение к голосовому каналу, если бот не подключен
    if not interaction.guild.voice_client:
        if interaction.user.voice:
            channel = interaction.user.voice.channel
            await channel.connect()
            await interaction.response.send_message("Бот подключился к голосовому каналу!")
        else:
            await interaction.response.send_message("Сначала подключитесь к голосовому каналу!", ephemeral=True)
            return
    else:
        # Первичный ответ, если бот уже подключен
        await interaction.response.defer()  # Сообщает Discord, что ответ будет отправлен позже

    # Загрузка аудио с помощью yt_dlp
    ydl_opts = {
        'format': 'bestaudio[ext=webm]/bestaudio/best',
        'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'}],
        'noplaylist': True,  # Отключение загрузки плейлистов
        'quiet': False,  # Включение логирования для отладки
        'verbose': True,  # Подробное логирование
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            audio_url = info['url']
            title = info['title']
    except Exception as e:
        await interaction.followup.send("Ошибка при загрузке трека. Убедитесь, что URL корректный.", ephemeral=True)
        print(f"Ошибка загрузки: {e}")
        return

    # Добавление трека в очередь
    await bot.queue.put((audio_url, title))
    await interaction.followup.send(f"Трек добавлен в очередь: **{title}**")

    # Если ничего не играет, запускаем трек
    if not bot.now_playing:
        await play_next(interaction)

# Воспроизведение следующего трека
async def play_next(interaction):
    if bot.queue.empty():
        bot.now_playing = None
        await interaction.followup.send("Очередь пуста.")
        return

    audio_url, title = await bot.queue.get()
    bot.now_playing = title

    ffmpeg_options = {'options': f'-vn -loglevel debug -filter:a "volume={bot.volume}"'}
    interaction.guild.voice_client.stop()
    interaction.guild.voice_client.play(
        discord.FFmpegPCMAudio(audio_url, **ffmpeg_options),
        after=lambda e: asyncio.run_coroutine_threadsafe(play_next(interaction), bot.loop)
    )

    # Создание кнопок управления
    buttons = discord.ui.View()
    buttons.add_item(discord.ui.Button(label="Stop", style=discord.ButtonStyle.danger, custom_id="stop"))
    buttons.add_item(discord.ui.Button(label="Pause", style=discord.ButtonStyle.primary, custom_id="pause"))
    buttons.add_item(discord.ui.Button(label="Resume", style=discord.ButtonStyle.success, custom_id="resume"))
    buttons.add_item(discord.ui.Button(label="Skip", style=discord.ButtonStyle.secondary, custom_id="skip"))

    # Отправка сообщения с кнопками
    if bot.message_with_controls:
        await bot.message_with_controls.delete()
    bot.message_with_controls = await interaction.followup.send(f"Сейчас играет: **{title}**", view=buttons)

# Обработчик кнопок
@bot.event
async def on_interaction(interaction: discord.Interaction):
    if interaction.type != discord.InteractionType.component:
        return

    custom_id = interaction.data["custom_id"]

    if custom_id == "stop":
        if interaction.guild.voice_client:
            await interaction.guild.voice_client.disconnect()
            await interaction.response.send_message("Бот отключился от голосового канала.")
    elif custom_id == "pause":
        if interaction.guild.voice_client and interaction.guild.voice_client.is_playing():
            interaction.guild.voice_client.pause()
            await interaction.response.send_message("Воспроизведение приостановлено.")
    elif custom_id == "resume":
        if interaction.guild.voice_client and interaction.guild.voice_client.is_paused():
            interaction.guild.voice_client.resume()
            await interaction.response.send_message("Воспроизведение возобновлено.")
    elif custom_id == "skip":
        if interaction.guild.voice_client and interaction.guild.voice_client.is_playing():
            interaction.guild.voice_client.stop()
            await interaction.response.send_message("Текущий трек пропущен.")
    else:
        await interaction.response.send_message("Неизвестная команда.", ephemeral=True)

# Запуск бота
bot.run(TOKEN)