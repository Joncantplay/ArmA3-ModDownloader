#!/usr/bin/python3
"""
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
## Script Version: v1.0 ##

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

## Configuration ##
config = configparser.ConfigParser()

# Read the configuration file
config.read('settings.txt')

# Access the configuration variables
STEAM_CMD = config.get('DEFAULT', 'STEAM_CMD')
STEAM_USER = config.get('DEFAULT', 'STEAM_USER')
STEAM_PASS = config.get('DEFAULT', 'STEAM_PASS')

MAX_TRIES = config.getint('DEFAULT', 'MAX_TRIES')
MODS_DIR = Path(config.get('DEFAULT', 'MODS_DIR'))

SERVER_ID = config.get('DEFAULT', 'SERVER_ID')
SERVER_DIR = Path(config.get('DEFAULT', 'SERVER_DIR'))
HTML_DIR = Path(config.get('DEFAULT', 'HTML_DIR'))

LOG = config.getboolean('DEFAULT', 'LOG')
LOG_DIR = config.get('DEFAULT', 'LOG_DIR')
LOG_NAME = config.get('DEFAULT', 'LOG_NAME')

WORKSHOP_DIR = SERVER_DIR / "steamapps/workshop/content/107410"
KEYS_DIR = SERVER_DIR / "keys"
## End of Configuration ##


UPDATE_PATTERN = re.compile(r"workshopAnnouncement.*?<p id=\"(\d+)\">", re.DOTALL)
TITLE_PATTERN = re.compile(r"(?<=<div class=\"workshopItemTitle\">)(.*?)(?=<\/div>)", re.DOTALL)
WORKSHOP_CHANGELOG_URL = "https://steamcommunity.com/sharedfiles/filedetails/changelog"

if LOG:
    os.makedirs(LOG_DIR, exist_ok=True)  # Ensure the directory exists
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_filename = f"{LOG_DIR}/{LOG_NAME}-{timestamp}.log"
    handlers = [logging.FileHandler(log_filename), logging.StreamHandler()]
else:
    handlers = [logging.StreamHandler()]
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s: %(message)s", datefmt="%H:%M", handlers=handlers,)


def log(msg):
    # Calculate the length of the log message with timestamp and log level
    log_prefix_length = len(datetime.now().strftime("%H:%M")) + 10
    total_length = log_prefix_length + len(msg)
    
    # Print the line of "=" characters to match the total length
    print("=" * total_length)
    logging.info(msg)
    print("=" * total_length)


def call_steamcmd(params):
    result = subprocess.run([STEAM_CMD] + params, text=True, capture_output=True)
    logging.info(result.stdout)  # Log the output
    if result.stderr:  # Check if there is any error
        logging.error(f'Error: {result.stderr}')  # Log error
    return result  # Return the result object
def call_steamcmd(params):
    process = subprocess.Popen([STEAM_CMD] + params, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    stdout, stderr = process.communicate()
    logging.info(stdout)  # Log the output
    if stderr:  # Check if there is any error
        logging.error(f'Error: {stderr}')  # Log error
    return process  # Return the process object

def update_server():
    log(f"Updating A3 server ({SERVER_ID})")
    cmd_params = [
                    f"+force_install_dir {str(SERVER_DIR)}",
                    f"+login {STEAM_USER} {STEAM_PASS}",
                    f"+app_update {str(SERVER_ID)} validate",
                    "+quit"
                ]
    call_steamcmd(cmd_params)


def mod_needs_update(mod_id, path):
    try:
        response = requests.get(f"{WORKSHOP_CHANGELOG_URL}/{mod_id}", timeout=20).text
        match = UPDATE_PATTERN.search(response)
        if match:
            updated_at = datetime.fromtimestamp(int(match.group(1)))
            created_at = datetime.fromtimestamp(path.stat().st_ctime)

            return updated_at >= created_at
        else:
            logging.error(f"Getting Mod Changelog check failed: {mod_id} ")
            return False
    except requests.exceptions.RequestException as e:
        logging.error(f"Error occurred while making the request: {e}")
        return False

def html_file():
    # List all HTML files in the A3_HTML_DIR directory
    html_files = list(HTML_DIR.glob("*.html"))

    # Sort files by creation date
    html_files.sort(key=lambda x: x.stat().st_ctime, reverse=True)

    # Check if there are any HTML files found
    if not html_files:
        logging.error("No HTML files found.")
        return None

    # Display the sorted HTML files to the user if no argument is provided
    
    if len(html_files) == 1:
        chosen_file = html_files[0]
        logging.info(f"Only one HTML file found: {chosen_file.name}, automatically selected.")
        return chosen_file
    else:
        log("Choose an HTML file:")
        for index, file in enumerate(html_files, start=1):
            logging.info(f"{index}. {file.name} (Created: {datetime.fromtimestamp(file.stat().st_ctime).strftime('%Y-%m-%d %H:%M')})")

    # Prompt the user to choose a file
    try:
        choice = int(input("Your choice (number): "))
        chosen_file = html_files[choice - 1]  # Adjust for 0-based indexing
        logging.info(f"You selected: {chosen_file.name}")
        return chosen_file
    except (ValueError, IndexError):
        logging.error("Invalid choice. Please enter a valid number.")
        return None


A3Modlist = {}
A3Modnames = []
def mods(html):
    with open(html, "r") as file:
        html_content = file.read()
    soup = BeautifulSoup(html_content, "html.parser")
    mod_containers = soup.find_all("tr", {"data-type": "ModContainer"})
    if mod_containers:
        for mod_container in mod_containers:
            modname = mod_container.find("td", {"data-type": "DisplayName"}).text.strip()
            special_characters = "!#$%^&*()[]{};:,./<>?\|`~='+-"
            modname = modname.translate(str.maketrans("", "", special_characters))
            modname = modname.lower().replace(" ", "_").replace("_" * 2, "_")
            A3Modnames.append("@" + modname)
            link = mod_container.find("a", {"data-type": "Link"})["href"]
            mod_id = link.split("=")[-1]
            A3Modlist["@" + modname] = mod_id
    else:
        log("No mods found in the HTML.")
    return A3Modlist, A3Modnames

def mod_check(mod_name, mod_id):
    # for mod_name, mod_id in A3Modlist.items():
    if "Addons" in os.listdir(WORKSHOP_DIR / mod_id):
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

lowercase = False
def update_mods():
    global lowercase
    log("Updating mods")
    if A3Modlist:
        for mod_name, mod_id in A3Modlist.items():
            path = WORKSHOP_DIR / mod_id
            # Check if mod needs to be updated
            if path.is_dir():
                if mod_needs_update(mod_id, path) or mod_check(mod_name, mod_id):
                    # Delete existing folder so that we can verify whether the download succeeded
                    shutil.rmtree(path)
                    lowercase = True
                else:
                    log(f"No update required for {mod_name} ({mod_id})... SKIPPING")
                    continue
            # Keep trying until the download actually succeeded
            tries = 0
            while path.is_dir() is False and tries < MAX_TRIES:
                tries += 1
                log(f"Updating {mod_name} ({mod_id}) | {tries}")

                steam_cmd_params = [
                    f"+force_install_dir {str(SERVER_DIR)}",
                    f"+login {STEAM_USER} {STEAM_PASS}",
                    f"+workshop_download_item 107410 {str(mod_id)} validate",
                    "+quit"
                    ]
                call_steamcmd(steam_cmd_params)
                # Sleep for a bit so that we can kill the script if needed
                time.sleep(3)
            if tries >= MAX_TRIES:
                log(f"!! Updating the mod {mod_name} ({mod_id}) failed after {tries} tries !!")
    if lowercase is False:
        log("No Mod Updates required")
    elif A3Modlist is False:
        log("No mod IDs found in the HTML file.")

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

def lowercase_workshop_dir():
    # Converts uppercase files/folders to lowercase in the workshop directory.
    if lowercase:
        log("Converting uppercase files/folders to lowercase...")
        subprocess.run(["find", str(WORKSHOP_DIR), "-depth", "-exec", "rename", "-v", "s/(.*)\/([^\/]*)/$1\/\L$2/", "{}", ";"])


def create_mod_symlinks():
    # Flag to check if any symlink is created
    symlink_created = False

    for mod_name, mod_id in A3Modlist.items():
        link_path = MODS_DIR / mod_name
        real_path = WORKSHOP_DIR / mod_id
        if real_path.is_dir() and not link_path.is_symlink():
            if not symlink_created:
                log("Creating symlinks...")
                symlink_created = True
            link_path.symlink_to(real_path)
            log(f"Creating symlink '{link_path}'...")
        elif not real_path.is_dir():
            log(f"Mod '{mod_name}' does not exist! ({real_path})")
        elif link_path.is_symlink():
            continue
        else:
            logging.error("Error occurred while creating symlinks")

    # If no symlinks were created, and you need to handle that case, you can add an else block here.
    if not symlink_created:
        log("No symlinks were created.")


def print_launch_params():
    # Generates launch parameters for the mods and logs them.
    log("Generating launch params...")
    rel_path = Path(MODS_DIR).relative_to(SERVER_DIR)
    mod_paths = [str(rel_path / mod_name) for mod_name in A3Modnames]
    try:
        # params = "-mod=" + "\;".join(mod_paths)
        params = "\;".join(mod_paths)
        with open("launch_params.txt", "w") as file:
            file.write(params)
        logging.debug(params)
        log("Launch parameters written to file: launch_params.txt")
    except Exception as e:
        logging.error(f"Error occurred while generating launch parameters: {e}")


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
                                # log(f"Skipping already existing key: '{key}' ({mod_name})")
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
                    key_dest.symlink_to(real_key_path)
                    existing_keys[key] = mod_name  # Mark the key as linked
                except OSError as e:
                    logging.error(f"Error occurred while creating symlink: {e}")

def debug():
    for mod_name, mod_id in A3Modlist.items():
        path = WORKSHOP_DIR / mod_id
        print(f"{mod_name}: {mod_needs_update(mod_id, path)}")



def clearallmods():
    log("Removing Mods")
    w_path = WORKSHOP_DIR
    m_path = MODS_DIR
    workshop_dir = os.path.join(SERVER_DIR, "steamapps", "workshop")

    # Check if the directory exists
    if os.path.exists(workshop_dir):
        # Iterate over all files in the workshop directory
        for filename in os.listdir(workshop_dir):
            # Check if the file has a .acf extension
            if filename.endswith(".acf"):
                # Construct the full file path
                file_path = os.path.join(workshop_dir, filename)
                # Delete the file
                os.remove(file_path)
                logging.info(f"File deleted: {filename}")
    for path in [w_path, m_path]:
        if os.path.exists(path):
            try:
                # Remove all the contents of the directory
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
            # Delete existing folder so that we can verify whether the download succeeded
            log(f"Deleting {mod_name} ({mod_id})")
            shutil.rmtree(path)
            


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


def update():
    mods(html_file())
    update_mods()
    if os_type() == "Linux":
        lowercase_workshop_dir()
    create_mod_symlinks()
    copy_keys()
    print_launch_params()


def param():
    mods(html_file())
    copy_keys()
    print_launch_params()


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
    return parser.parse_args()


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
        mods(html_file())
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
        mods(html_file())
        clearmods()
        log("All mods cleared successfully.")
    elif args.clearall:
        clearallmods()
        log("All mods cleared successfully.")
    elif args.lower:
        log("Converting uppercase files/folders to lowercase...")
        subprocess.run(["find", str(WORKSHOP_DIR), "-depth", "-exec", "rename", "-v", "s/(.*)\/([^\/]*)/$1\/\L$2/", "{}", ";"])
    elif args.debug:
        print(mods(html_file()))
        debug()
    else:
        print("No valid option selected.")
        sys.exit(1)
