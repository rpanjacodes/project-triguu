import os
import time
import random
import subprocess
import discord
from discord.ext import commands, tasks
import asyncio

# Configuration
MUSIC_FOLDER = "music/"
GIF_FILE = "bg.gif"
RTMP_URL = "rtmp://a.rtmp.youtube.com/live2/"  # Replace with your key
BOT_TOKEN = ""  # Replace this
FPS = 24
RESTART_COOLDOWN = 600  # 10 minutes

# Discord Bot Setup
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# Memory of previous state
last_music_set = set()
last_gif_modified = None
last_restart_time = 0

# Get shuffled playlist
def get_playlist():
    mp3_files = [f for f in os.listdir(MUSIC_FOLDER) if f.endswith(".mp3")]
    if not mp3_files:
        print("[ERROR] No MP3 files found in music folder!")
        return []
    random.shuffle(mp3_files)
    return [os.path.join(MUSIC_FOLDER, f) for f in mp3_files]

# Combine audio into one temporary file
def combine_audio(tracks):
    combined_path = "combined_output.mp3"
    list_file = "playlist_temp.txt"
    with open(list_file, "w", encoding="utf-8") as f:
        for track in tracks:
            f.write(f"file '{os.path.abspath(track)}'\n")
    subprocess.run(f'ffmpeg -y -f concat -safe 0 -i {list_file} -c copy {combined_path}', shell=True)
    return combined_path

# Create FFmpeg command
def create_ffmpeg_command():
    playlist = get_playlist()
    if not playlist:
        return None
    combine_audio(playlist)
    return f"""
    ffmpeg -stream_loop -1 -i "{GIF_FILE}" -stream_loop -1 -i "combined_output.mp3" \
    -filter_complex "[0:v]fps={FPS},scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:-1:-1:color=black,format=yuv420p[v]" \
    -map "[v]" -map 1:a \
    -c:v libx264 -preset veryfast -b:v 3000k -maxrate 3000k -bufsize 6000k \
    -c:a aac -b:a 192k -ar 44100 \
    -f flv "{RTMP_URL}"
    """.strip()

# Kill FFmpeg and restart stream
def restart_stream():
    global last_restart_time
    now = time.time()
    if now - last_restart_time < RESTART_COOLDOWN:
        print("[INFO] Restart skipped (cooldown active)")
        return
    last_restart_time = now
    print("[INFO] Restarting stream...")
    subprocess.run("pkill -f ffmpeg", shell=True)
    time.sleep(2)
    command = create_ffmpeg_command()
    if command:
        subprocess.Popen(command, shell=True)
        print("[INFO] Stream started successfully.")
    else:
        print("[ERROR] Could not start stream. Check playlist.")

# Watch for new MP3s
@tasks.loop(seconds=60)
async def watch_music_folder():
    global last_music_set
    current_music_set = set(f for f in os.listdir(MUSIC_FOLDER) if f.endswith(".mp3"))
    if current_music_set != last_music_set:
        print("[INFO] Music folder updated. Refreshing stream...")
        last_music_set = current_music_set
        restart_stream()

# Watch for GIF file change
@tasks.loop(seconds=30)
async def watch_gif_file():
    global last_gif_modified
    try:
        current_modified = os.path.getmtime(GIF_FILE)
        if last_gif_modified is None:
            last_gif_modified = current_modified
        elif current_modified != last_gif_modified:
            print("[INFO] Background GIF changed. Restarting stream with new visual.")
            last_gif_modified = current_modified
            # GIF changes trigger immediate restart, bypass cooldown
            subprocess.run("pkill -f ffmpeg", shell=True)
            time.sleep(2)
            command = create_ffmpeg_command()
            if command:
                subprocess.Popen(command, shell=True)
                print("[INFO] Stream restarted with new GIF.")
    except Exception as e:
        print(f"[ERROR] Checking GIF file: {e}")

# Manual commands
@bot.command()
async def restart(ctx):
    subprocess.run("pkill -f ffmpeg", shell=True)
    time.sleep(2)
    command = create_ffmpeg_command()
    if command:
        subprocess.Popen(command, shell=True)
        await ctx.send("✅ Stream restarted!")
    else:
        await ctx.send("❌ Stream restart failed (missing playlist?)")

@bot.command()
async def nowplaying(ctx):
    playlist = get_playlist()
    if playlist:
        await ctx.send(f"🎵 Now Playing: `{os.path.basename(playlist[0])}`")
    else:
        await ctx.send("⚠️ No songs currently playing.")

# When bot is ready
@bot.event
async def on_ready():
    print(f"[BOT] Logged in as {bot.user}")
    global last_music_set, last_gif_modified
    last_music_set = set(f for f in os.listdir(MUSIC_FOLDER) if f.endswith(".mp3"))
    last_gif_modified = os.path.getmtime(GIF_FILE)
    restart_stream()
    watch_music_folder.start()
    watch_gif_file.start()

# Run Bot
bot.run(BOT_TOKEN)
