# 🎧 APEX DJ - High-Performance Discord Music Bot

**APEX DJ** is a feature-rich, modern Discord Music Bot powered by `discord.py` v2, `yt-dlp`, and `FFmpeg`. It includes interactive UI control buttons, rich embeds with live progress bars, queue management, volume controls, and ready-to-deploy Docker configuration for Render hosting.

---

## 🔥 Key Features

- **Interactive UI Control Buttons**: Clickable buttons directly on Discord messages (`Play/Pause`, `Skip`, `Stop`, `Loop`, `Shuffle`, `Queue`, `Vol -`, `Vol +`).
- **Slash Commands**: Full support for native Discord Slash (`/`) commands (`/play`, `/lofi`, `/queue`, `/nowplaying`, `/skip`, `/stop`, `/loop`, `/volume`, `/join`, `/leave`, `/clear`, `/remove`).
- **Live Progress Bar**: Visual progress indicator (`[🔘▬▬▬▬▬▬▬▬▬▬] 01:23 / 03:45`) and track info.
- **24/7 Lofi Stream**: Instant 1-click `/lofi` radio stream command.
- **Multi-Format Audio**: Plays YouTube videos, playlists, Spotify link search, SoundCloud, and direct stream links.
- **Auto-Disconnect**: Cleans up automatically when the voice channel becomes empty or idle.
- **Cloud Ready**: Includes built-in HTTP server and `Dockerfile` with system `FFmpeg` for 24/7 deployment on Render.

---

## 🛠️ Prerequisites & Discord Bot Setup

### Step 1: Create Your Bot on Discord Developer Portal

1. Go to the [Discord Developer Portal](https://discord.com/developers/applications).
2. Click **New Application**, name it **APEX DJ**, and click **Create**.
3. Go to the **Bot** tab on the left menu.
4. Click **Reset Token** (or **Add Bot**) to copy your **Bot Token**. *Keep this token secret!*
5. Scroll down to **Privileged Gateway Intents** and **ENABLE**:
   - ✅ **Message Content Intent**
   - ✅ **Presence Intent** (optional)
   - ✅ **Server Members Intent** (optional)
6. Save changes.

### Step 2: Generate Bot Invite Link

1. Go to **OAuth2** -> **URL Generator** on the left menu.
2. Under **Scopes**, select:
   - ✅ `bot`
   - ✅ `applications.commands`
3. Under **Bot Permissions**, select:
   - ✅ `Send Messages`
   - ✅ `Embed Links`
   - ✅ `Read Message History`
   - ✅ `Connect`
   - ✅ `Speak`
   - ✅ `Use Voice Activity`
4. Copy the generated URL at the bottom and open it in your browser to invite the bot to your Discord server!

---

## 💻 Local Running Instructions

### 1. Install Dependencies & FFmpeg

Make sure Python 3.10+ and `FFmpeg` are installed on your computer.

- **Windows (FFmpeg)**: Download from [ffmpeg.org](https://ffmpeg.org/download.html) or install via winget:
  ```powershell
  winget install "FFmpeg (Essentials Build)"
  ```
- **Mac**: `brew install ffmpeg`
- **Linux**: `sudo apt update && sudo apt install -y ffmpeg`

### 2. Configure Environment Variables

Open `.env` and paste your Discord Bot Token:
```env
DISCORD_TOKEN=your_actual_bot_token_here
PORT=8080
```

### 3. Install Python Requirements & Run

```bash
pip install -r requirements.txt
python bot.py
```

---

## 🚀 How to Push to GitHub & Host on Render

### Step 1: Push Code to GitHub

Open PowerShell in your project folder (`APEX DJ`) and run:

```bash
git init
git add .
git commit -m "Initial commit - APEX DJ Music Bot"
git branch -M main
git remote add origin https://github.com/YOUR_GITHUB_USERNAME/APEX-DJ.git
git push -u origin main
```

*(Replace `YOUR_GITHUB_USERNAME` with your actual GitHub username)*

---

### Step 2: Deploy to Render (24/7 Hosting)

1. Log in to [Render.com](https://render.com/).
2. Click **New +** -> **Web Service**.
3. Connect your GitHub account and select your **APEX-DJ** repository.
4. Render will automatically detect the `Dockerfile` in your repository!
   - **Name**: `apex-dj-bot`
   - **Environment**: `Docker`
   - **Plan**: `Free`
5. Scroll down to **Environment Variables** and add:
   - **Key**: `DISCORD_TOKEN` | **Value**: `your_actual_bot_token_here`
   - **Key**: `PORT` | **Value**: `8080`
6. Click **Create Web Service**.

Render will build the Docker container (which automatically installs FFmpeg and dependencies) and launch your bot 24/7!

---

## 📜 Commands List

| Slash Command | Description |
| :--- | :--- |
| `/play <query>` | Play a song or playlist from YouTube/Search URL |
| `/lofi` | Play 24/7 Lofi Chill Radio stream |
| `/nowplaying` | Show currently playing song with interactive buttons |
| `/queue` | View upcoming song queue |
| `/skip` | Skip the current track |
| `/pause` | Pause music playback |
| `/resume` | Resume paused music playback |
| `/stop` | Stop music, clear queue, and leave voice channel |
| `/loop <Off\|Track\|Queue>` | Set loop mode |
| `/shuffle` | Randomize queue order |
| `/volume <1-100>` | Adjust volume |
| `/join` | Connect bot to your voice channel |
| `/leave` | Disconnect bot from voice channel |
| `/clear` | Clear all queued songs |
| `/remove <index>` | Remove a specific track from queue |

---

## 🛡️ License & Credits
Built with ❤️ using `discord.py` and `yt-dlp`.
