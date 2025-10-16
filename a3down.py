#!/usr/bin/python3
"""
ArmA 3 Server/Mod Updater — Windows/Linux Compatible (Full, Original Logic)
============================================================================
This version preserves the original logic and features, with minimal, safe improvements:
- OS-aware launch parameter formatting (Windows uses ";" / Linux uses "\;")
- Launch params include the configured MODS_DIR path relative to SERVER_DIR (e.g., "mods/@...")
- Windows symlink creation with automatic Junction fallback (mklink /J)
- Linux-only shell calls replaced with cross‑platform Python where applicable
- Colored console logging (colorama) for better readability
- HTML selection is fail-safe (won't crash when no file exists)



MIT License

Copyright (c) 2025 Jon

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

import sys
import os
import re
import time
import logging
import subprocess
import shutil
import requests
import argparse
import configparser

from datetime import datetime
from bs4 import BeautifulSoup
from pathlib import Path
from colorama import Fore, Style, init

# ---------- Init colored output ----------
init(autoreset=True)

# =====================[ CONFIGURATION ]===================== #
config = configparser.ConfigParser()
config.read('a3down_settings.txt')

# Access the configuration variables
STEAM_CMD  = config.get('DEFAULT', 'STEAM_CMD')
STEAM_USER = config.get('DEFAULT', 'STEAM_USER')
STEAM_PASS = config.get('DEFAULT', 'STEAM_PASS')

MAX_TRIES  = config.getint('DEFAULT', 'MAX_TRIES')
MODS_DIR   = Path(config.get('DEFAULT', 'MODS_DIR'))

SERVER_ID  = config.get('DEFAULT', 'SERVER_ID')
SERVER_DIR = Path(config.get('DEFAULT', 'SERVER_DIR'))
HTML_DIR   = Path(config.get('DEFAULT', 'HTML_DIR'))

LOG      = config.getboolean('DEFAULT', 'LOG')
LOG_DIR  = config.get('DEFAULT', 'LOG_DIR')
LOG_NAME = config.get('DEFAULT', 'LOG_NAME')

WORKSHOP_DIR = SERVER_DIR / "steamapps/workshop/content/107410"
KEYS_DIR     = SERVER_DIR / "keys"

# Internal files
FAILED_MODS_FILE = Path('failed_mods.txt')

# Patterns / constants
UPDATE_PATTERN = re.compile(r"workshopAnnouncement.*?<p id=\"(\d+)\">", re.DOTALL)
TITLE_PATTERN  = re.compile(r"(?<=<div class=\"workshopItemTitle\">)(.*?)(?=<\/div>)", re.DOTALL)
WORKSHOP_CHANGELOG_URL = "https://steamcommunity.com/sharedfiles/filedetails/changelog"

# ---------- Logging setup ----------
if LOG:
    os.makedirs(LOG_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log_filename = f"{LOG_DIR}/{LOG_NAME}-{timestamp}.log"
    handlers = [logging.FileHandler(log_filename, encoding="utf-8"), logging.StreamHandler()]
else:
    handlers = [logging.StreamHandler()]
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s: %(message)s",
    datefmt="%H:%M",
    handlers=handlers
)

# ===============[ SMALL LOG HELPERS FOR COLOR ]=============== #
def _bar(msg: str) -> str:
    # Length of "HH:MM - LEVEL: " is about 10, keep original look
    bar_len = len(datetime.now().strftime("%H:%M")) + 10 + len(msg)
    return "=" * bar_len

def log(msg: str):
    """Original 'banner' logger, now with cyan info text."""
    print(Fore.CYAN + _bar(msg))
    logging.info(Fore.CYAN + msg + Style.RESET_ALL)
    print(Fore.CYAN + _bar(msg) + Style.RESET_ALL)

def log_warn(msg: str):
    print(Fore.YELLOW + _bar(msg))
    logging.warning(Fore.YELLOW + msg + Style.RESET_ALL)
    print(Fore.YELLOW + _bar(msg) + Style.RESET_ALL)

def log_error(msg: str):
    print(Fore.RED + _bar(msg))
    logging.error(Fore.RED + msg + Style.RESET_ALL)
    print(Fore.RED + _bar(msg) + Style.RESET_ALL)

# =====================[ OS DETECTION ]===================== #
def os_type():
    if os.name == "nt":
        return "Windows"
    elif os.name == "posix":
        if sys.platform.startswith("darwin"):
            return "macOS"
        else:
            return "Linux"
    else:
        return "Unknown"

# =====================[ STEAMCMD RUNTIME ]===================== #
def call_steamcmd(params):
    """
    Runs SteamCMD with real-time streaming of output to the console.
    Windows: use a single command string with shell=True (handles .exe + spaces).
    Linux/macOS: use list execution.
    """
    if os_type() == "Windows":
        cmd = f"\"{STEAM_CMD}\" " + " ".join(params)
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            shell=True
        )
    else:
        process = subprocess.Popen(
            [STEAM_CMD] + params,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
    for line in process.stdout:
        logging.info(line.rstrip())
    process.wait()
    return process

# =====================[ SERVER UPDATE ]===================== #
def update_server():
    log(f"Updating A3 server ({SERVER_ID})")
    cmd_params = [
        f"+force_install_dir {str(SERVER_DIR)}",
        f"+login {STEAM_USER} {STEAM_PASS}",
        f"+app_update {str(SERVER_ID)} validate",
        "+quit"
    ]
    call_steamcmd(cmd_params)

# =====================[ WORKSHOP UPDATE CHECK ]===================== #
def mod_needs_update(mod_id, path: Path):
    """
    Check Steam workshop changelog timestamp against local folder ctime.
    Returns True if a newer update exists (or if we fail safely -> False).
    """
    try:
        response = requests.get(f"{WORKSHOP_CHANGELOG_URL}/{mod_id}", timeout=20).text
        match = UPDATE_PATTERN.search(response)
        if match:
            updated_at = datetime.fromtimestamp(int(match.group(1)))
            created_at = datetime.fromtimestamp(path.stat().st_ctime)
            return updated_at >= created_at
        else:
            logging.error(f"Getting Mod Changelog check failed: {mod_id}")
            return False
    except requests.exceptions.RequestException as e:
        logging.error(f"Error occurred while making the request: {e}")
        return False

# =====================[ HTML FILE PICKER (SAFE) ]===================== #
def html_file():
    """
    Returns newest HTML in HTML_DIR.
    If none → log and return None (caller must handle None).
    """
    html_files = list(HTML_DIR.glob("*.html"))
    if not html_files:
        log_error("No HTML files found.")
        return None

    html_files.sort(key=lambda x: x.stat().st_ctime, reverse=True)

    if len(html_files) == 1:
        chosen_file = html_files[0]
        logging.info(f"Only one HTML file found: {chosen_file.name}, automatically selected.")
        return chosen_file
    else:
        log("Choose an HTML file:")
        for index, file in enumerate(html_files, start=1):
            logging.info(f"{index}. {file.name} (Created: {datetime.fromtimestamp(file.stat().st_ctime).strftime('%Y-%m-%d %H:%M')})")
        try:
            choice = int(input("Your choice (number): "))
            chosen_file = html_files[choice - 1]
            logging.info(f"You selected: {chosen_file.name}")
            return chosen_file
        except (ValueError, IndexError):
            log_error("Invalid choice. Please enter a valid number.")
            return None

# =====================[ MOD LIST PARSER ]===================== #
A3Modlist  = {}
A3Modnames = []

def mods(html_path):
    """
    Parse the exported preset HTML for mods and fill A3Modlist/A3Modnames.
    Safe when html_path is None -> returns empty.
    """
    global A3Modlist, A3Modnames
    A3Modlist.clear()
    A3Modnames.clear()

    if not html_path:
        log_warn("No HTML file selected – skipping mod parsing.")
        return A3Modlist, A3Modnames

    with open(html_path, "r", encoding="utf-8") as file:
        html_content = file.read()
    soup = BeautifulSoup(html_content, "html.parser")
    mod_containers = soup.find_all("tr", {"data-type": "ModContainer"})
    if mod_containers:
        for mod_container in mod_containers:
            modname = mod_container.find("td", {"data-type": "DisplayName"}).text.strip()
            special_characters = "!#$%^&*()[]{};:,./<>?\\|`~='+-"
            modname = modname.translate(str.maketrans("", "", special_characters))
            modname = modname.lower().replace(" ", "_").replace("_" * 2, "_")
            A3Modnames.append("@" + modname)
            link = mod_container.find("a", {"data-type": "Link"})["href"]
            mod_id = link.split("=")[-1]
            A3Modlist["@" + modname] = mod_id
    else:
        log("No mods found in the HTML.")
    return A3Modlist, A3Modnames

# =====================[ LOCAL MOD FOLDER CHECK ]===================== #
def mod_check(mod_name, mod_id):
    """
    Verify that the mod's Addons/addons folder exists and contains files.
    Returns True if re-download is required.
    """
    path = None
    if (WORKSHOP_DIR / mod_id / "Addons").is_dir():
        path = WORKSHOP_DIR / mod_id / "Addons"
    else:
        path = WORKSHOP_DIR / mod_id / "addons"
    if path.is_dir():
        files = os.listdir(path)
        if files:
            return False
        else:
            log(f"No files found in addons folder for {mod_name} ({mod_id}) ... Start re-downloading.")
            return True
    else:
        log(f"Addons folder not found for {mod_name} ({mod_id})")
        return True

# =====================[ UPDATE MODS (ORIGINAL LOGIC) ]===================== #
lowercase = False
def update_mods():
    """
    Use workshop timestamps + local checks to determine if a mod needs update.
    Delete/re-download only when needed. Record failed mods.
    """
    global lowercase
    if FAILED_MODS_FILE.exists():
        FAILED_MODS_FILE.unlink()
    log("Updating mods")
    if A3Modlist:
        for mod_name, mod_id in A3Modlist.items():
            path = WORKSHOP_DIR / mod_id
            # Determine if update is required
            must_update = True
            if path.is_dir():
                # Only update if remote newer or local broken
                if mod_needs_update(mod_id, path) or mod_check(mod_name, mod_id):
                    # Remove existing folder so we can verify download success
                    shutil.rmtree(path)
                    lowercase = True
                else:
                    log(f"No update required for {mod_name} ({mod_id})... SKIPPING")
                    must_update = False
            if not must_update and path.is_dir():
                continue

            # Keep trying until the download actually succeeded
            tries = 0
            while (not path.is_dir()) and tries < MAX_TRIES:
                tries += 1
                log(f"Updating {mod_name} ({mod_id}) | {tries}")
                steam_cmd_params = [
                    f"+force_install_dir {str(SERVER_DIR)}",
                    f"+login {STEAM_USER} {STEAM_PASS}",
                    f"+workshop_download_item 107410 {str(mod_id)} validate",
                    "+quit"
                ]
                call_steamcmd(steam_cmd_params)
                time.sleep(3)

            if tries >= MAX_TRIES:
                log(f"!! Updating the mod {mod_name} ({mod_id}) failed after {tries} tries !!")
                with open(FAILED_MODS_FILE, 'a', encoding="utf-8") as f:
                    f.write(f"{mod_id}\n")
    if lowercase is False:
        log("No Mod Updates required")
    elif not A3Modlist:
        log("No mod IDs found in the HTML file.")

# =====================[ FORCE UPDATE (ORIGINAL) ]===================== #
def ForeUpdate():
    if A3Modlist:
        for mod_name, mod_id in A3Modlist.items():
            log(f"Updating {mod_name} ({mod_id})")
            steam_cmd_params = [
                f"+force_install_dir {str(SERVER_DIR)}",
                f"+login {STEAM_USER} {STEAM_PASS}",
                f"+workshop_download_item 107410 {str(mod_id)} validate",
                "+quit"
            ]
            call_steamcmd(steam_cmd_params)
            time.sleep(3)
    else:
        log("No mod IDs found in the HTML file.")

# =====================[ RETRY FAILED MODS (FIXED tries) ]===================== #
def retry_failed_mods():
    if not FAILED_MODS_FILE.exists():
        log("No failed mods file present. Nothing to retry.")
        return
    log("Retrying failed mods until success")
    with open(FAILED_MODS_FILE, encoding="utf-8") as f:
        failed_ids = [l.strip() for l in f if l.strip()]
    for mod_id in failed_ids:
        mod_name = next((name for name, mid in A3Modlist.items() if mid == mod_id), mod_id)
        path = WORKSHOP_DIR / mod_id
        tries = 0
        while True:
            # Success condition: folder exists and contains any entries
            if path.is_dir() and any(path.iterdir()):
                log(f"{mod_name} ({mod_id}) succesfully Downloaded.")
                break
            tries += 1
            log(f"Retry downloading failed mod {mod_name} ({mod_id}) | {tries}")
            steam_cmd_params = [
                f"+force_install_dir {str(SERVER_DIR)}",
                f"+login {STEAM_USER} {STEAM_PASS}",
                f"+workshop_download_item 107410 {mod_id} validate",
                "+quit"
            ]
            call_steamcmd(steam_cmd_params)
            time.sleep(3)
    # Delete file after finish
    FAILED_MODS_FILE.unlink()

# =====================[ LOWERCASE WORKSHOP DIR (PYTHON, LINUX ONLY CALLER) ]===================== #
def lowercase_workshop_dir():
    """
    Convert names to lowercase recursively. 
    Only called by original script on Linux; implemented in Python for portability.
    """
    for root, dirs, files in os.walk(WORKSHOP_DIR, topdown=False):
        for name in files:
            src = Path(root) / name
            dst = Path(root) / name.lower()
            if src != dst:
                # On case-insensitive FS (Windows), two-step rename to avoid conflicts
                tmp = Path(root) / (name + ".__TMP__")
                try:
                    if os.name == "nt" and src.name.lower() == dst.name.lower():
                        src.rename(tmp)
                        tmp.rename(dst)
                    else:
                        src.rename(dst)
                except Exception as e:
                    logging.error(f"Lowercase rename failed for file {src}: {e}")
        for name in dirs:
            src = Path(root) / name
            dst = Path(root) / name.lower()
            if src != dst:
                tmp = Path(root) / (name + ".__TMP__")
                try:
                    if os.name == "nt" and src.name.lower() == dst.name.lower():
                        src.rename(tmp)
                        tmp.rename(dst)
                    else:
                        src.rename(dst)
                except Exception as e:
                    logging.error(f"Lowercase rename failed for dir {src}: {e}")

# =====================[ CREATE MOD SYMLINKS (JUNCTION FALLBACK) ]===================== #
def create_mod_symlinks():
    """Create symlinks for mods. On Windows, fall back to junctions when needed."""
    symlink_created = False
    for mod_name, mod_id in A3Modlist.items():
        link_path = MODS_DIR / mod_name
        real_path = WORKSHOP_DIR / mod_id
        if real_path.is_dir() and not link_path.exists():
            if not symlink_created:
                log("Creating symlinks...")
                symlink_created = True
            try:
                os.symlink(real_path, link_path, target_is_directory=True)
                log(f"Creating symlink '{link_path}'...")
            except (OSError, NotImplementedError):
                if os_type() == "Windows":
                    # mklink /J link target
                    subprocess.run(["cmd", "/c", "mklink", "/J", str(link_path), str(real_path)], shell=True)
                    log(f"Creating junction '{link_path}'...")
                else:
                    logging.error("Error occurred while creating symlinks")
        elif not real_path.is_dir():
            log(f"Mod '{mod_name}' does not exist! ({real_path})")
        # if link already exists, skip silently

    if not symlink_created:
        log("No symlinks were created.")

# =====================[ LAUNCH PARAMS WRITER (OS-AWARE, MODS PATH) ]===================== #
def print_launch_params():
    """Generate launch params using correct separator and relative MODS_DIR path."""
    log("Generating launch params...")
    if not A3Modnames:
        logging.error("No mods collected; cannot generate launch params.")
        return
    # relative MODS_DIR (e.g., 'mods') against server root
    rel_path = Path(MODS_DIR).relative_to(SERVER_DIR)
    mod_paths = [str(rel_path / mod_name) for mod_name in A3Modnames]
    sep = ";" if os_type() == "Windows" else r"\;"
    params = "\n".join(f"{m}{sep}" for m in mod_paths)
    try:
        with open("ModsParam.txt", "w", encoding="utf-8") as file:
            file.write(params)
        logging.debug(params)
        log("Launch parameters written to file: ModsParam.txt")
    except Exception as e:
        logging.error(f"Error occurred while generating launch parameters: {e}")

# =====================[ COPY KEYS (ORIGINAL LOGIC) ]===================== #
def copy_keys():
    log("Copying server keys...")
    key_path = KEYS_DIR  # Destination directory for the keys

    # Remove only broken symlinks (that point to nonexistent files)
    for key in os.listdir(KEYS_DIR):
        key_file = key_path / key
        if key_file.is_symlink() and not key_file.exists():
            log(f"Removing broken symlink: '{key}'")
            key_file.unlink()

    # Dictionary to track already set keys
    existing_keys = {}

    for mod_name in A3Modnames:
        if mod_name not in A3Modlist.items():
            real_path = MODS_DIR / mod_name
            if not real_path.is_dir():
                log(f"Couldn't copy the key from: '{mod_name}', directory doesn't exist.")
                continue

            # Check for "keys" and "key" folders
            key_dir = None
            if (real_path / "keys").is_dir():
                key_dir = real_path / "keys"
            elif (real_path / "key").is_dir():
                key_dir = real_path / "key"
            else:
                log(f"Couldn't find the key folder of: {mod_name}")
                continue

            for key in os.listdir(key_dir):
                real_key_path = key_dir / key
                key_dest = key_path / key

                # If the key is already linked by another mod, skip it
                if key in existing_keys:
                    log(f"Skipping duplicate key '{key}' from mod '{mod_name}' (already linked by '{existing_keys[key]}')")
                    continue

                # If the symlink already exists, check if it is correct
                if key_dest.exists():
                    if key_dest.is_symlink():
                        try:
                            if os.path.samefile(key_dest, real_key_path):
                                existing_keys[key] = mod_name  # Store the key as linked
                                continue
                        except FileNotFoundError:
                            pass  # If the old path is broken, it will be replaced

                        log(f"Removing incorrect key symlink: {key}")
                    else:
                        log(f"Removing incorrect key file: {key}")

                    key_dest.unlink()  # Delete only if incorrect

                try:
                    log(f"Creating symlink to key for: '{mod_name}' ({key})")
                    # On Windows: create normal file link fallback if needed
                    try:
                        key_dest.symlink_to(real_key_path)
                    except (OSError, NotImplementedError):
                        if os_type() == "Windows":
                            # copy as last resort to keep behavior
                            shutil.copy2(real_key_path, key_dest)
                    existing_keys[key] = mod_name  # Mark the key as linked
                except OSError as e:
                    logging.error(f"Error occurred while creating symlink: {e}")

# =====================[ DEBUG HELPER ]===================== #
def debug():
    for mod_name, mod_id in A3Modlist.items():
        path = WORKSHOP_DIR / mod_id
        print(f"{mod_name}: {mod_needs_update(mod_id, path)}")

# =====================[ CLEAR HELPERS ]===================== #
def clearallmods():
    log("Removing Mods")
    w_path = WORKSHOP_DIR
    m_path = MODS_DIR
    workshop_dir = os.path.join(SERVER_DIR, "steamapps", "workshop")

    # Remove .acf files
    if os.path.exists(workshop_dir):
        for filename in os.listdir(workshop_dir):
            if filename.endswith(".acf"):
                file_path = os.path.join(workshop_dir, filename)
                os.remove(file_path)
                logging.info(f"File deleted: {filename}")

    for path in [w_path, m_path]:
        if os.path.exists(path):
            try:
                for filename in os.listdir(path):
                    file_path = os.path.join(path, filename)
                    if os.path.isfile(file_path) or os.path.islink(file_path):
                        os.unlink(file_path)
                    elif os.path.isdir(file_path):
                        shutil.rmtree(file_path)
                logging.info(f"Successfully cleared {path}")
            except Exception as e:
                logging.error(f"Failed to clear {path}: {e}")
        else:
            logging.warning(f"Directory {path} does not exist")

def clearmods():
    for mod_name, mod_id in A3Modlist.items():
        path = WORKSHOP_DIR / mod_id
        if path.is_dir():
            log(f"Deleting {mod_name} ({mod_id})")
            shutil.rmtree(path)

# =====================[ COMPOSITE OPERATIONS ]===================== #
def update():

    html = html_file()
    mods(html)
    update_mods()
    if os_type() == "Linux":
        lowercase_workshop_dir()
    create_mod_symlinks()
    copy_keys()
    print_launch_params()

def param():
    """Only copy keys and write launch parameters (no updates)."""
    html = html_file()
    mods(html)
    copy_keys()
    print_launch_params()

# =====================[ ARGUMENT PARSER ]===================== #
def parse_arguments():
    parser = argparse.ArgumentParser(description="ArmA 3 Server/Mod Update", exit_on_error=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("-su", "--ServerUpdate", action="store_true", help="Perform a full Server update")
    group.add_argument("-u", "--Update", action="store_true", help="Perform a normal update")
    group.add_argument("-fu", "--ForceUpdate", action="store_true", help="Perform a Forced Mod update")
    group.add_argument("-lo", "--LaunchOptions", action="store_true", help="Only get Launch options + copy keys")
    group.add_argument("-cl", "--clear", action="store_true", help="Clear mods of a selected html file")
    group.add_argument("-ca", "--clearall", action="store_true", help="Clear all mods")
    group.add_argument("-l", "--lower", action="store_true", help="Lowercase Workshop Dir")
    group.add_argument("-d", "--debug", action="store_true", help="Debugging")
    group.add_argument("-r", "--retry", action="store_true", help="Retry Failed mods")
    group.add_argument("-sy", "--symlink", action="store_true", help="Creating the Mod symlinks")
    return parser.parse_args()

# =====================[ ENTRY POINT ]===================== #
if __name__ == "__main__":
    args = parse_arguments()

    if args.ServerUpdate:
        log("Starting Full Server update..")
        update_server()
        update()
        log("Full update completed.")
    elif args.Update:
        update()
        log("Update completed.")
    elif args.ForceUpdate:
        html = html_file()
        mods(html)
        ForeUpdate()
        if os_type() == "Linux":
            lowercase_workshop_dir()
        create_mod_symlinks()
        copy_keys()
        print_launch_params()
        log("Forced Update completed.")
    elif args.LaunchOptions:
        param()
        log("Launch options and keys processed.")
    elif args.clear:
        html = html_file()
        mods(html)
        clearmods()
        log("All mods cleared successfully.")
    elif args.clearall:
        clearallmods()
        log("All mods cleared successfully.")
    elif args.lower:
        log("Converting uppercase files/folders to lowercase...")
        lowercase_workshop_dir()
    elif args.debug:
        print(mods(html_file()))
        debug()
    elif args.retry:
        retry_failed_mods()
    elif args.symlink:
        html = html_file()
        mods(html)
        create_mod_symlinks()
    else:
        print("No valid option selected.")
        sys.exit(1)
