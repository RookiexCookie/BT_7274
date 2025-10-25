import os
import sys
import time
import random
import datetime
import tempfile
import subprocess
import threading
import json
from pathlib import Path

# --- Core Dependencies ---
import webbrowser
import pyautogui
from pynput.keyboard import Key, Listener as KeyboardListener
import speech_recognition as sr
import sounddevice as sd
import soundfile as sf
import requests
import psutil

# --- Optional Dependencies ---
try:
    import noisereduce as nr
    import numpy as np
    HAS_NR = True
except ImportError:
    HAS_NR = False

# --- New Dependencies (Group 1 & 2) ---
import shutil
import re
import hashlib
try:
    import pyperclip
    HAS_CLIPBOARD = True
except ImportError:
    HAS_CLIPBOARD = False
try:
    import feedparser
    HAS_FEED = True
except ImportError:
    HAS_FEED = False
try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False
try:
    import git
    HAS_GIT = True
except ImportError:
    HAS_GIT = False
try:
    import screen_brightness_control as sbc
    HAS_BRIGHTNESS = True
except ImportError:
    HAS_BRIGHTNESS = False
try:
    import spotipy
    from spotipy.oauth2 import SpotifyOAuth
    HAS_SPOTIPY = True
except ImportError:
    HAS_SPOTIPY = False

# ----------------------------------------


# ==============================================================================
# ---------- CONFIGURATION & GLOBAL STATE ----------
# ==============================================================================
try:
    SCRIPT_DIR = Path(__file__).parent
    with open(SCRIPT_DIR / "config.json", "r") as f:
        CONFIG = json.load(f)
    
    TTS_CACHE_DIR = SCRIPT_DIR / CONFIG['paths']['tts_cache_dir']
    TTS_CACHE_DIR.mkdir(exist_ok=True)

except Exception as e:
    print(f"FATAL ERROR loading config.json: {e}")
    sys.exit(1)

# --- GLOBAL OBJECTS ---
recognizer = sr.Recognizer()
is_speaking = threading.Event()
is_recording = threading.Event()
mic_lock = threading.Lock()
sp = None # Spotify object

# --- NEW: Context and Memory Globals ---
last_context = {"file": None, "search": None, "app": None}
memory_data = {}
watchdog_data = {}
MEMORY_FILE_PATH = SCRIPT_DIR / CONFIG['paths']['memory_file']
CLIPBOARD_LOG_PATH = SCRIPT_DIR / CONFIG['paths']['clipboard_log']
WATCHDOG_FILE_PATH = SCRIPT_DIR / CONFIG['paths']['watchdog_file']

# ==============================================================================
# ---------- CORE HELPER FUNCTIONS (speak, transcribe, etc.) ----------
# ==============================================================================

def safe_print(text: str):
    with threading.Lock():
        print(text)

def sanitize_for_filename(text: str) -> str:
    safe_text = text.encode('ascii', 'ignore').decode('ascii')
    safe_text = "".join(c for c in safe_text if c.isalnum() or c in " _-").strip()
    return safe_text[:75] + ".wav"

def speak(key_or_text: str):
    if is_speaking.is_set(): return
    is_speaking.set()

    output_file_path = None
    is_temp_file = False

    try:
        if key_or_text in CONFIG['dialogue_pools']:
            is_temp_file = False
            text = random.choice(CONFIG['dialogue_pools'][key_or_text])
            cache_file = TTS_CACHE_DIR / sanitize_for_filename(text)
            output_file_path = cache_file

            if not cache_file.exists():
                safe_print(f"BT-7274 (Caching): {text}")
                cmd = [str(SCRIPT_DIR / CONFIG['paths']['piper_exe']), 
                       "-m", str(SCRIPT_DIR / CONFIG['paths']['voice_model']), 
                       "--output_file", str(cache_file)]
                subprocess.run(cmd, input=text.encode("utf-8"), check=True, 
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                safe_print(f"BT-7274 (Cached): {text}")
        
        else:
            is_temp_file = True
            text = key_or_text
            safe_print(f"BT-7274 (Generating): {text}")

            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                temp_wav = f.name
            output_file_path = temp_wav
            
            cmd = [str(SCRIPT_DIR / CONFIG['paths']['piper_exe']), 
                   "-m", str(SCRIPT_DIR / CONFIG['paths']['voice_model']), 
                   "--output_file", str(temp_wav)]
            subprocess.run(cmd, input=text.encode("utf-8"), check=True, 
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        if output_file_path and Path(output_file_path).exists():
            data, samplerate = sf.read(output_file_path, dtype="float32")
            sd.play(data, samplerate)
            sd.wait()

    except Exception as e:
        safe_print(f"ERROR in speak: {e}")
    
    finally:
        is_speaking.clear()
        if is_temp_file and output_file_path and Path(output_file_path).exists():
            try: os.remove(output_file_path)
            except Exception: pass

def reduce_noise_if_available(audio: sr.AudioData) -> sr.AudioData:
    if not HAS_NR: return audio
    try:
        raw_data = audio.get_raw_data()
        sample_rate = audio.sample_rate
        sample_width = audio.sample_width
        dtype = f'<i{sample_width}'
        audio_data_np = np.frombuffer(raw_data, dtype=dtype).astype(np.float32)
        audio_data_np /= np.iinfo(dtype).max
        reduced_noise_audio = nr.reduce_noise(y=audio_data_np, sr=sample_rate)
        reduced_noise_audio *= np.iinfo(dtype).max
        reduced_noise_audio = reduced_noise_audio.astype(dtype)
        return sr.AudioData(reduced_noise_audio.tobytes(), sample_rate, sample_width)
    except Exception as e:
        safe_print(f"WARNING: Noise reduction failed: {e}")
        return audio

def transcribe_audio(audio: sr.AudioData) -> str:
    if not audio: return "None"
    try:
        processed_audio = reduce_noise_if_available(audio)
        text = recognizer.recognize_google(processed_audio)
        safe_print(f"PILOT: {text}")
        return text.lower()
    except sr.UnknownValueError:
        return "None"
    except sr.RequestError:
        speak("Pilot, my connection to command is down.")
        return "None"

def get_confirmation() -> bool:
    speak("confirmation")
    with mic_lock:
        try:
            with sr.Microphone() as source:
                audio = recognizer.listen(source, timeout=4, phrase_time_limit=3)
            text = transcribe_audio(audio)
            return any(word in text for word in CONFIG['confirmation_words'])
        except sr.WaitTimeoutError:
            return False

# ==============================================================================
# ---------- NEW: MEMORY & WATCHDOG HELPER FUNCTIONS ----------
# ==============================================================================

def load_memory_file(file_path):
    """Generic function to load a JSON file."""
    if file_path.exists():
        try:
            with open(file_path, "r") as f:
                return json.load(f)
        except Exception as e:
            safe_print(f"ERROR: Could not load {file_path}: {e}")
    return {}

def save_memory_file(file_path, data):
    """Generic function to save data to a JSON file."""
    try:
        with open(file_path, "w") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        safe_print(f"ERROR: Could not save {file_path}: {e}")

# ==============================================================================
# ---------- COMMAND PROCESSING (Bug Fix Included) ----------
# ==============================================================================

def process_command(query: str):
    """
    Finds the *best* matching command from the config and executes it.
    This version prioritizes the longest matching keyword to solve collisions.
    """
    global last_command_subject
    if not query or query == "None":
        return

    best_match_command, best_match_len, best_match_keyword = None, 0, ""

    for command in CONFIG['commands']:
        for keyword in command['keywords']:
            if query.startswith(keyword):
                if len(keyword) > best_match_len:
                    best_match_len = len(keyword)
                    best_match_command = command
                    best_match_keyword = keyword

    if best_match_command:
        command = best_match_command
        if "ack" in command:
            speak(command["ack"])
        
        query_data = query.replace(best_match_keyword, "", 1).strip()
        last_context["search"] = query_data if "search" in command['type'] else None
        
        execute_action(command, query_data)
        return
                
    speak("error")


def execute_action(command: dict, query_data: str):
    """Executes the action defined in the matched command object."""
    action_type = command['type']
    global last_context, memory_data, watchdog_data
    
    try:
        # --- Script Shutdown ---
        if action_type == "script.shutdown":
            speak("shutdown")
            time.sleep(2)
            os._exit(0)

        # --- System Commands ---
        elif action_type == "system.status":
            cpu = psutil.cpu_percent(interval=1)
            mem = psutil.virtual_memory().percent
            status_report = f"All systems nominal. CPU at {cpu} percent. Memory at {mem} percent."
            try:
                battery = psutil.sensors_battery()
                if battery:
                    status_report += f" Battery is at {battery.percent} percent."
            except AttributeError: pass
            speak(status_report)
        
        # --- NEW: Top Processes ---
        elif action_type == "system.top_processes":
            try:
                processes = sorted(psutil.process_iter(['name', 'cpu_percent', 'memory_percent']), 
                                   key=lambda p: p.info['cpu_percent'], reverse=True)
                top_cpu = processes[0].info['name']
                top_cpu_val = processes[0].info['cpu_percent']
                
                processes_mem = sorted(processes, key=lambda p: p.info['memory_percent'], reverse=True)
                top_mem = processes_mem[0].info['name']
                top_mem_val = round(processes_mem[0].info['memory_percent'], 1)

                speak(f"Hostile process {top_cpu} is consuming {top_cpu_val} percent CPU. {top_mem} is using {top_mem_val} percent memory.")
            except Exception as e:
                safe_print(f"ERROR: Top Process failed: {e}")
                speak("I was unable to analyze system processes.")

        elif action_type in ["system.shutdown", "system.restart"]:
            if get_confirmation():
                mode = "/s" if action_type == "system.shutdown" else "/r"
                speak(f"Confirmed. Initiating system {action_type.split('.')[-1]}.")
                subprocess.run(["shutdown", mode, "/t", "5"])
        
        elif action_type == "system.lock":
            subprocess.run(["rundll32.exe", "user32.dll,LockWorkStation"])
        
        elif action_type == "system.set_brightness":
            if not HAS_BRIGHTNESS:
                speak("Brightness control module not found."); return
            try:
                value = int(re.findall(r'\d+', query_data)[0])
                if 0 <= value <= 100:
                    sbc.set_brightness(value)
                    speak(f"Brightness set to {value} percent.")
            except Exception as e:
                safe_print(f"ERROR: Brightness control failed: {e}")

        elif action_type in ["system.wifi_on", "system.wifi_off"]:
            try:
                iface = CONFIG['settings']['wifi_interface_name']
                state = "enable" if action_type == "system.wifi_on" else "disable"
                cmd = f'netsh interface set interface "{iface}" admin={state}'
                subprocess.run(cmd, check=True, shell=True, 
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception as e:
                safe_print(f"ERROR: WiFi control failed: {e}")

        # --- App & Web Commands ---
        elif action_type == "app.open" or action_type == "app.close":
            target_name = next((name for name in command['targets'] if name in query_data), None)
            if not target_name:
                speak("Please specify which application.")
                return
            target_path_or_exe = command['targets'][target_name]
            if action_type == "app.open":
                subprocess.Popen(target_path_or_exe)
                last_context["app"] = target_name
            else:
                subprocess.run(["taskkill", "/f", "/im", target_path_or_exe], 
                               capture_output=True, check=False)
                speak(f"{target_name} process terminated.")
        
        elif action_type == "web.open":
            site_name = next((name for name in command['targets'] if name in query_data), None)
            if site_name:
                webbrowser.open(command['targets'][site_name])
            else: speak("Please specify which website to open.")
        
        elif action_type == "web.search":
            webbrowser.open(command['url_template'].format(query=query_data))

        # --- NEW: Web Watchdog ---
        elif action_type == "web.watchdog":
            if not (HAS_BS4 and HAS_FEED):
                speak("Watchdog modules are not installed, Pilot."); return
            
            target_name = query_data.lower()
            if not target_name or target_name not in CONFIG['watchdog_targets']:
                speak("Please specify a valid watchdog target."); return
            
            target = CONFIG['watchdog_targets'][target_name]
            speak(f"Checking watchdog for {target_name}...")
            try:
                headers = {'User-Agent': 'Mozilla/5.0'}
                response = requests.get(target['url'], headers=headers)
                soup = BeautifulSoup(response.text, 'lxml')
                element = soup.select_one(target['selector'])
                
                if not element:
                    speak("Error: I could not find the target element on the page."); return

                current_hash = hashlib.md5(element.text.encode()).hexdigest()
                last_hash = watchdog_data.get(target_name)

                if last_hash == current_hash:
                    speak("Negative, Pilot. No change detected at that node.")
                else:
                    speak(f"Affirmative. The watchdog target {target_name} has been updated.")
                    watchdog_data[target_name] = current_hash
                    save_memory_file(WATCHDOG_FILE_PATH, watchdog_data)
            except Exception as e:
                safe_print(f"ERROR: Watchdog failed: {e}")
                speak("I was unable to check the webpage.")

        # --- NEW: RSS Intel Feed ---
        elif action_type == "feed.check":
            if not HAS_FEED:
                speak("RSS Feed module is not installed."); return
            
            feed_name = query_data.lower()
            if not feed_name or feed_name not in CONFIG['rss_feeds']:
                speak("Please specify a valid feed to check."); return
            
            feed_url = CONFIG['rss_feeds'][feed_name]
            feed = feedparser.parse(feed_url)
            
            if not feed.entries:
                speak(f"No new intel from {feed_name}."); return
            
            latest_entry = feed.entries[0]
            speak(f"New intel from {feed_name}. The latest entry is: {latest_entry.title}")

        # --- Media Commands (incl. Now Playing) ---
        elif action_type == "media.play_music":
            if not sp: speak("spotify_error"); return
            try:
                devices = sp.devices()
                active_device = next((d for d in devices['devices'] if d['is_active']), None)
                if not active_device: speak("spotify_no_device"); return
                
                device_id, song_to_play = active_device['id'], None
                artist_name, song_name = None, query_data
                
                if " by " in query_data:
                    try: song_name, artist_name = query_data.split(" by ", 1)
                    except ValueError: pass

                results = sp.search(q=query_data, limit=5, type='track')
                if not results['tracks']['items']:
                    speak(f"I could not find {query_data} on Spotify."); return

                if artist_name:
                    for track in results['tracks']['items']:
                        for artist in track['artists']:
                            if artist_name.lower() in artist['name'].lower():
                                song_to_play = track; break
                        if song_to_play: break
                
                if not song_to_play: song_to_play = results['tracks']['items'][0]
                
                sp.start_playback(device_id=device_id, uris=[song_to_play['uri']])
                speak(f"Playing {song_to_play['name']} by {song_to_play['artists'][0]['name']}.")
            except Exception as e:
                safe_print(f"Spotify play failed: {e}")
                speak("spotify_error")
        
        elif action_type == "media.now_playing":
            if not sp: speak("spotify_error"); return
            try:
                track_info = sp.current_playback()
                if track_info and track_info['is_playing'] and track_info['item']:
                    speak(f"You are listening to {track_info['item']['name']} by {track_info['item']['artists'][0]['name']}.")
                else: speak("Nothing is currently playing on Spotify.")
            except Exception as e:
                safe_print(f"ERROR: Now Playing failed: {e}")
                speak("spotify_error")

        elif action_type == "media.key_press":
            pyautogui.press(command['key'])
        
        elif action_type == "media.volume_change":
            key = "volumeup" if command['direction'] == "up" else "volumedown"
            for _ in range(command['amount']): pyautogui.press(key)

        # --- Memory, Clipboard, & Utility ---
        elif action_type == "utility.remember":
            try:
                key, value = query_data.split(" is ", 1)
                memory_data[key.lower()] = value
                save_memory_file(MEMORY_FILE_PATH, memory_data)
                speak(f"Understood. I will remember that {key} is {value}.")
            except Exception as e:
                safe_print(f"ERROR: Failed to parse memory: {e}")
                speak("I didn't understand. Please say 'remember that [key] is [value]'.")
        
        elif action_type == "utility.recall":
            key = query_data.lower()
            value = memory_data.get(key)
            if value: speak(f"You said that {key} is {value}.")
            else: speak(f"I have no memory of {key}, Pilot.")
        
        elif action_type == "utility.archive_clipboard":
            if not HAS_CLIPBOARD: speak("Clipboard module not installed."); return
            try:
                clipboard_content = pyperclip.paste()
                with open(CLIPBOARD_LOG_PATH, "a", encoding="utf-8") as f:
                    f.write(f"\n--- Archived at {datetime.datetime.now()} ---\n{clipboard_content}\n")
            except Exception as e:
                safe_print(f"ERROR: Failed to archive clipboard: {e}")

        # --- File & OS Automation ---
        elif action_type == "file.search":
            if not query_data: speak("Please specify a file name."); return
            speak(f"Searching for {query_data}...")
            search_dirs = [Path.home() / "Documents", Path.home() / "Desktop", Path.home() / "Downloads"]
            found_files = []
            for directory in search_dirs:
                try: found_files.extend(list(directory.rglob(f"*{query_data}*")))
                except Exception as e: safe_print(f"Error searching {directory}: {e}")
            
            if found_files:
                first_result = found_files[0]
                speak(f"I found {first_result.name} in your {first_result.parent.name} folder. Opening it.")
                os.startfile(first_result)
                last_context["file"] = first_result # NEW: Set context
            else:
                speak(f"I could not locate any files matching {query_data}.")

        # --- NEW: File Move (Context-Aware) ---
        elif action_type == "file.move":
            target_file = None
            if query_data.startswith("it") or query_data.startswith("that"):
                if last_context["file"]:
                    target_file = last_context["file"]
                    query_data = query_data.replace("it", "").replace("that", "").strip()
                else:
                    speak("What file are you referring to, Pilot?"); return
            else:
                speak("File move command is not fully implemented for non-context files."); return # Placeholder
            
            if not target_file: return
            
            # Simple destination parser: "move it to [destination]"
            if "to " in query_data:
                destination_name = query_data.split("to ", 1)[-1].lower()
                dest_path = None
                if destination_name == "desktop":
                    dest_path = Path.home() / "Desktop"
                elif destination_name == "documents":
                    dest_path = Path.home() / "Documents"
                elif destination_name == "downloads":
                    dest_path = Path.home() / "Downloads"
                
                if dest_path and dest_path.exists():
                    try:
                        shutil.move(str(target_file), str(dest_path / target_file.name))
                        speak(f"Moved {target_file.name} to {destination_name}.")
                        last_context["file"] = dest_path / target_file.name # Update context
                    except Exception as e:
                        safe_print(f"ERROR: File move failed: {e}")
                        speak(f"I was unable to move the file.")
                else:
                    speak(f"I do not recognize the destination {destination_name}.")
            else:
                speak("Please specify a destination, for example: 'move it to desktop'.")

        # --- NEW: File Delete (Context-Aware) ---
        elif action_type == "file.delete":
            target_file = None
            if query_data == "it" or query_data == "that" or not query_data:
                if last_context["file"]:
                    target_file = last_context["file"]
                else:
                    speak("What file are you referring to, Pilot?"); return
            
            if not target_file:
                speak("I could not find the file to delete."); return
            
            speak(f"Confirm: delete {target_file.name}?")
            if get_confirmation():
                try:
                    os.remove(target_file)
                    speak("Target eliminated.")
                    last_context["file"] = None # Clear context
                except Exception as e:
                    safe_print(f"ERROR: File delete failed: {e}")
                    speak("Deletion failed. The file may be in use.")
            else:
                speak("Deletion aborted.")

        elif action_type == "file.desktop_janitor":
            speak("Acknowledged. Sorting non-essential files.")
            desktop_path = Path.home() / "Desktop"
            targets = {
                "Pictures": [".png", ".jpg", ".jpeg"],
                "Videos": [".mp4", ".mkv", ".mov"],
                "Downloads": [".zip", ".rar", ".exe", ".msi"],
                "Documents": [".pdf", ".docx", ".txt", ".csv"]
            }
            file_count = 0
            for item in desktop_path.glob("*"):
                if not item.is_file(): continue
                for folder_name, extensions in targets.items():
                    if item.suffix.lower() in extensions:
                        target_dir = Path.home() / folder_name
                        target_dir.mkdir(exist_ok=True)
                        try:
                            shutil.move(str(item), str(target_dir / item.name))
                            file_count += 1
                        except Exception as e:
                            safe_print(f"Failed to move {item.name}: {e}")
                        break
            speak(f"Desktop cleanup complete. {file_count} files were sorted.")

        # --- NEW: Backup Protocol ---
        elif action_type == "backup.run":
            target_name = query_data.lower()
            if not target_name or target_name not in CONFIG['backup_targets']:
                speak("Please specify a valid backup target."); return
            
            source_dir = CONFIG['backup_targets'][target_name]
            backup_dir = Path(CONFIG['paths']['backup_dir'])
            backup_dir.mkdir(exist_ok=True)
            
            timestamp = datetime.datetime.now().strftime('%Y-%m-%d_%H%M')
            archive_name = f"backup_{target_name}_{timestamp}"
            
            speak(f"Running backup for {target_name}...")
            try:
                shutil.make_archive(str(backup_dir / archive_name), 'zip', source_dir)
                speak("Backup complete and secured.")
            except Exception as e:
                safe_print(f"ERROR: Backup failed: {e}")
                speak("I encountered an error during the backup protocol.")

        # --- Macro Execution ---
        elif action_type == "macro.run":
            macro_name = query_data.lower()
            if macro_name in CONFIG['macros']:
                speak(f"Executing macro: {macro_name}.")
                for step in CONFIG['macros'][macro_name]:
                    try:
                        step_type = step['type']
                        step_data = step.get('data', "")
                        step_command = next((cmd for cmd in CONFIG['commands'] if cmd['type'] == step_type), None)
                        
                        if step_command:
                            safe_print(f"Macro step: {step_type} | Data: {step_data}")
                            while is_speaking.is_set(): time.sleep(0.1)
                            execute_action(step_command, step_data)
                            time.sleep(1.0) # Buffer between macro commands
                        else:
                            safe_print(f"Macro Warning: Command type '{step_type}' not found.")
                    except Exception as e:
                        safe_print(f"ERROR: Macro step failed: {e}")
                speak(f"Macro {macro_name} complete.")
            else:
                speak(f"I do not have a macro named {macro_name}.")

        # --- NEW: Git Integration ---
        elif action_type == "git.status":
            if not HAS_GIT: speak("Git module not installed."); return
            project_name = query_data.lower()
            if not project_name or project_name not in CONFIG['project_paths']:
                speak("Please specify a valid project."); return
            
            repo_path = CONFIG['project_paths'][project_name]
            try:
                repo = git.Repo(repo_path)
                if not repo.is_dirty(untracked_files=True):
                    speak(f"Project {project_name} is clean, Pilot.")
                else:
                    untracked = len(repo.untracked_files)
                    changed = len(repo.index.diff(None))
                    speak(f"Project {project_name} has {changed} modified files and {untracked} untracked files.")
            except Exception as e:
                safe_print(f"ERROR: Git status failed: {e}")
                speak("I was unable to check the repository status.")

        elif action_type == "git.commit_push":
            if not HAS_GIT: speak("Git module not installed."); return
            project_name = query_data.lower()
            if not project_name or project_name not in CONFIG['project_paths']:
                speak("Please specify a valid project."); return
            
            repo_path = CONFIG['project_paths'][project_name]
            try:
                repo = git.Repo(repo_path)
                if not repo.is_dirty(untracked_files=True):
                    speak("No changes to commit."); return
                
                speak("Committing all changes and pushing to remote.")
                repo.git.add(all=True)
                repo.git.commit(m=f"Auto-commit by BT-7274 at {datetime.datetime.now()}")
                repo.git.push()
                speak("Commit and push successful.")
            except Exception as e:
                safe_print(f"ERROR: Git commit/push failed: {e}")
                speak("Git operation failed. Check for conflicts or authentication.")

        # --- General & Utility Commands ---
        elif action_type == "general.time":
            speak(f"The time is {datetime.datetime.now():%H:%M}.")
        
        elif action_type == "general.date":
            speak(f"Today is {datetime.datetime.now().strftime('%A, %B %d, %Y')}.")
        
        elif action_type == "general.joke":
            speak("jokes")
        
        elif action_type == "api.weather":
            api_key = CONFIG["api_keys"]["openweather_api_key"]
            city = CONFIG["api_keys"]["weather_city"]
            res = requests.get(f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={api_key}&units=metric").json()
            if res["cod"] == 200:
                speak(f"The current temperature is {res['main']['temp']:.0f} degrees with {res['weather'][0]['description']}.")
            else: speak("Unable to retrieve weather data.")
        
        elif action_type == "utility.type":
            pyautogui.write(query_data, interval=0.05)

    except Exception as e:
        safe_print(f"FATAL ERROR executing action {action_type}: {e}")
        speak("I have encountered a critical error, Pilot.")

# ==============================================================================
# ---------- PTT & INITIALIZATION ----------
# ==============================================================================

def handle_ptt_flow():
    """Plays PTT ack, listens, transcribes, and processes."""
    speak("ptt_ack")
    
    safe_print("LISTENING...")
    audio = None
    with mic_lock:
        try:
            with sr.Microphone() as source:
                audio = recognizer.listen(source, timeout=5, phrase_time_limit=8)
        except sr.WaitTimeoutError:
            pass
    
    text = transcribe_audio(audio)
    is_recording.clear()
    process_command(text)


def calibrate_microphone():
    safe_print("Calibrating microphone for ambient noise...")
    with mic_lock:
        with sr.Microphone() as source:
            recognizer.adjust_for_ambient_noise(source, duration=1.5)
    safe_print("Calibration complete.")

def initialize_spotify():
    global sp
    if not HAS_SPOTIPY:
        safe_print("WARNING: 'spotipy' library not found. Spotify features will be disabled.")
        return
    creds = CONFIG.get('spotify')
    if not creds or "YOUR_SPOTIFY_CLIENT_ID" in creds['client_id']:
        safe_print("WARNING: Spotify credentials missing in config.json. Spotify features disabled.")
        return
    try:
        scope = (
            "user-modify-playback-state "
            "user-read-playback-state "
            "user-read-currently-playing "
            "user-library-read"
        )
        auth_manager = SpotifyOAuth(
            scope=scope,
            client_id=creds['client_id'],
            client_secret=creds['client_secret'],
            redirect_uri=creds['redirect_uri'],
            cache_path=SCRIPT_DIR / ".spotipyoauthcache"
        )
        sp = spotipy.Spotify(auth_manager=auth_manager)
        sp.devices()
        safe_print("Spotify connection established.")
    except Exception as e:
        safe_print(f"ERROR: Spotify initialization failed: {e}")
        sp = None

def initialize_systems():
    """CalGibrates mic, initializes Spotify, and loads memory."""
    global memory_data, watchdog_data
    psutil.cpu_percent(interval=None) # Prime psutil
    calibrate_microphone()
    initialize_spotify()
    memory_data = load_memory_file(MEMORY_FILE_PATH)
    watchdog_data = load_memory_file(WATCHDOG_FILE_PATH)
    speak("startup")

def main():
    """Main entry point. Initializes systems and starts the PTT listener."""
    initialize_systems()
    
    ptt_key_str = CONFIG['settings']['push_to_talk_key']
    try:
        ptt_key = getattr(Key, ptt_key_str)
    except AttributeError:
        safe_print(f"ERROR: Invalid 'push_to_talk_key': {ptt_key_str}.")
        sys.exit(1)
    
    def on_press(key):
        if key == ptt_key and not is_speaking.is_set() and not is_recording.is_set():
            is_recording.set()
            threading.Thread(target=handle_ptt_flow, daemon=True).start()

    with KeyboardListener(on_press=on_press) as listener:
        safe_print(f"BT-7274 INITIALIZED. Press {ptt_key_str.upper()} to speak.")
        try:
            listener.join()
        except KeyboardInterrupt:
            safe_print("\nShutdown signal received.")
            speak("shutdown")
            time.sleep(2)

if __name__ == "__main__":
    main()