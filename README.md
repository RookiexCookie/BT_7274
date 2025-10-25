# BT-7274 Desktop Assistant

<p align="center">
  <img src="https://media1.tenor.com/m/9wI_bxPl3LIAAAAC/thumbs-up-bt7274.gif" alt="BT-7274 Thumbs Up" width="400"/>
</p>

<p align="center">
  <strong>"Welcome back, Pilot. All systems online."</strong>
</p>

BT-7274 is a **local-first**, voice-activated **desktop assistant for Windows**, themed after the Vanguard-class Titan from *Titanfall 2*.  
Built to uphold the three Vanguard protocols, BT operates entirely offline — using Google’s **speech recognition** for input and [**Piper TTS**](https://github.com/rhasspy/piper) for fast, local voice synthesis.

---

## ⚙️ Protocol Summary

* **PROTOCOL 1: LINK TO PILOT** — Establishes a secure connection through a push-to-talk (PTT) system (`F7` by default). BT listens only when commanded.  
* **PROTOCOL 2: UPHOLD THE MISSION** — Executes complex voice commands including system, file, and media control.  
* **PROTOCOL 3: PROTECT THE PILOT** — Ensures all memory, notes, and data remain **local**. No cloud processing. No third-party tracking.

---

## ► Core Capabilities

BT-7274 is designed for operational efficiency, offering deep integration with Windows systems.

### 🖥️ System & Hardware Control
* **System Status:** Reports CPU, RAM, and battery usage.  
* **Process Intel:** Identifies top CPU and memory-consuming processes.  
* **Power Control:** Shutdown, restart, or lock workstation (with confirmation).  
* **Wi-Fi Control:** Enable or disable your Wi-Fi adapter.  
* **Brightness Control:** Adjust display brightness via command.

> *"All systems nominal, Pilot. Power levels optimal."*

---

### 📁 File Management (Context-Aware)
* **File Search:** Locate files by name across Desktop, Documents, and Downloads.  
* **Follow-up Commands:**  
  * “Move it to desktop.”  
  * “Delete that file.”  
* **Desktop Janitor:** Automatically organize desktop clutter into categorized folders.  

> *"Efficiency is paramount, Pilot. I’ve cleaned your desktop."*

---

### 🌐 Application & Web
* **Launch / Terminate:** Open or close applications defined in `config.json`.  
  * Example: “Open Spotify.” / “Close Chrome.”  
* **Search the Web:** Execute Google queries.  
* **Quick Access:** Instantly open sites like GitHub, Gemini, or YouTube.  

---

### 🧠 Productivity & Automation
* **Macros:** Execute grouped commands like `"run coding macro"` to open VS Code, GitHub, and play lofi music.  
* **Git Integration:**  
  * Check `git status` for a project.  
  * Commit and push with a single voice command.  
* **Backup Protocol:** Compress and back up any specified folder to a defined directory.  
* **Web Watchdog:** Monitor webpages for content changes via CSS selector.  
* **RSS Intel Feeds:** Retrieve updates from selected RSS feeds.  

> *"Mission data secured, Pilot. Backup complete."*

---

### 🎧 Media & Utilities
* **Spotify Control:**  
  * Play tracks or artists (e.g., “Play One Call Away by Charlie Puth”).  
  * Query the “now playing” song.  
  * Manage playback (pause/resume, next, previous, volume).  
* **Memory & Recall:**  
  * “Remember that my Wi-Fi password is 1234.”  
  * “What do you remember about my Wi-Fi password?”  
* **Clipboard Archive:** Save clipboard data to log file.  
* **Dictation:** “Type this — mission report complete.”  
* **General Commands:** Ask for time, date, weather, or a joke.  

> *"Engaging humor module… why do Titans never get tired? Because they have stamina cores."*

---

## ► Requirements

### 🐍 Python Libraries
Install dependencies listed in `requirements.txt`:

```
# Core
pyautogui
pynput
SpeechRecognition
sounddevice
soundfile
requests
psutil

# Optional
noisereduce
numpy
pyperclip
feedparser
beautifulsoup4
GitPython
screen-brightness-control
spotipy
```

### 🔧 External Dependencies
* **[Piper TTS](https://github.com/rhasspy/piper):**  
  - Download `piper.exe` and a voice model (`.onnx`).  
  - Update paths in `config.json`.

* **Spotify API:**  
  - Create a Spotify Developer App.  
  - Add your `client_id`, `client_secret`, and `redirect_uri` in the configuration.

---

## ► Installation & Setup

### 1. Clone the Repository
```bash
git clone https://github.com/RookieCookie/BT-7274-Assistant.git
cd BT-7274-Assistant
```

### 2. Install Piper TTS
* Download the [latest Piper release](https://github.com/rhasspy/piper/releases) for Windows.  
* Extract `piper.exe` and your chosen `.onnx` voice model into the `piper/` folder.  

### 3. Install Python Dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure `config.json`
Edit key fields:
* `paths.piper_exe` → path to `piper.exe`  
* `paths.voice_model` → path to `.onnx` file  
* `paths.backup_dir` → directory for backup archives  
* `api_keys` → insert OpenWeatherMap API key and city  
* `spotify` → add credentials from Spotify Developer Portal  
* `settings.wifi_interface_name` → name of your Wi-Fi adapter  
* `project_paths` → local repo paths  
* `backup_targets` → folders for backup  

### 5. Launch BT
```bash
python main.py
```

> *“Initializing Titan systems. Neural link established.”*

---

## ► Usage

Once initialized, BT will calibrate your microphone and report readiness:

```
BT-7274 INITIALIZED
```

Hold **`F7`** (or your custom push-to-talk key) to give commands.  
BT will respond audibly and execute your directives.

Examples:
* “System status.”  
* “Play lofi.”  
* “Backup my assistant code.”  
* “Commit and push project.”

<p align="center">
  <img src="https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExajNsNmg2emJ5cWt0enp3ZDE1aDNpdTIybnFkZzMzN2J0eWN0eDJocyZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/9J1mS0uR1DRn1iVv4Q/giphy.gif" alt="Protocol 3" width="400"/>
</p>

<p align="center">
  <strong>"Protocol 3: Protect the Pilot. Trust me."</strong>
</p>

---

## ► License & Credits

This project is **fan-made**, inspired by *Titanfall 2* by **Respawn Entertainment**.  
All voice lines, personality traits, and visual themes belong to their respective owners.  
This software is for **educational and personal use only**.

---

## ► Final Log

> “Protocol One: Link to Pilot.  
> Protocol Two: Uphold the Mission.  
> Protocol Three: Protect the Pilot.  
> Mission parameters complete. Awaiting further orders, Pilot.”  

— **BT-7274**
