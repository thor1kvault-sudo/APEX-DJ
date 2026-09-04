# 🎵 APEX DJ - Discord Music & Song Bot

A high-performance Discord Music Bot built with **Python**, **discord.py**, and **yt-dlp**. It replicates the exact interactive embed design from your screenshot ("THOR PLAY'S 🤖"), complete with button controls, progress bar, queue system, and support for pasting Spotify and YouTube links or text queries.

---

## 🌟 Features

- **Link Auto-Detection:** Paste any **Spotify** (track, album, playlist) or **YouTube** link directly into any channel where you're in a voice channel, and it will immediately queue and play the song!
- **Search Query Support:** Type song titles like `/play A.R. Rahman - Enna Sona` or `!play Enna Sona`.
- **Exact Embed UI Replication:**
  - Dynamic Track Title & Album Cover Thumbnail
  - Visual Progress Bar (`🔘▬▬▬▬▬▬▬▬▬▬▬▬▬▬ 0:00 / 3:33`)
  - Metadata: Requester (`Added by @user`), Voice Channel info, Queue Size, Volume %, Loop status.
- **Interactive Control Buttons:**
  - `❤️ Like`: Save favorite tracks
  - `⏸ Pause` / `▶ Resume`: Toggle playback
  - `⏭ Skip`: Move to the next track
  - `⏹ Stop`: Clear queue and leave voice channel
  - `🔄 AutoPlay`: Toggle continuous music recommendations when the queue ends
  - `🎛 Dashboard`: View control center and up next list
  - `👍 Love this` / `👎 Not for me`: Interactive user feedback
- **Slash Commands & Prefix Commands:** Use `/play`, `/skip`, `/pause`, `/queue`, etc. or `!play`, `!skip`, `!stop`.

---

## 🚀 Step-by-Step Setup Guide

### 1️⃣ Get a Discord Bot Token
1. Go to the [Discord Developer Portal](https://discord.com/developers/applications).
2. Click **New Application** and enter a name (e.g., `APEX DJ` or `THOR PLAY'S`).
3. Go to the **Bot** tab on the left menu.
4. Click **Reset Token** (or **Copy Token**) to copy your Bot Token.
5. **Crucial:** Scroll down to **Privileged Gateway Intents** and enable ALL three intents:
   - ✅ **Presence Intent**
   - ✅ **Server Members Intent**
   - ✅ **Message Content Intent**
6. Click **Save Changes**.

---

### 2️⃣ Invite the Bot to Your Discord Server
1. In the Developer Portal, go to **OAuth2 -> URL Generator**.
2. Under **Scopes**, select:
   - ✅ `bot`
   - ✅ `applications.commands`
3. Under **Bot Permissions**, select:
   - ✅ `Send Messages`
   - ✅ `Embed Links`
   - ✅ `Attach Files`
   - ✅ `Use External Emojis`
   - ✅ `Connect`
   - ✅ `Speak`
   - ✅ `Use Voice Activity`
4. Copy the generated URL at the bottom, paste it into your browser, select your server, and authorize the bot!

---

### 3️⃣ Configure `.env` File
Open the `.env` file in the project folder and paste your Discord Bot Token:

```env
DISCORD_TOKEN=your_bot_token_here
BOT_PREFIX=!
BOT_NAME=APEX DJ
```

---

### 4️⃣ Install Dependencies
Run the following command in your terminal:

```bash
pip install -r requirements.txt
```

*(Note: FFmpeg is already installed on your system!)*

---

### 5️⃣ Run the Bot
To start the bot, execute:

```bash
python bot.py
```

Once you see:
```text
🤖 Bot Logged In as: APEX DJ#1234
Synced Slash Commands globally!
```
Your bot is online and ready!

---

## 🎧 How to Use

1. **Join any Voice Channel** in your Discord server.
2. Either paste a **YouTube** or **Spotify** link directly in text chat, OR use commands:
   - `/play Enna Sona`
   - `!play https://open.spotify.com/track/4d0x...`
3. The bot will join your voice channel and post the interactive **Now playing** player control embed!
