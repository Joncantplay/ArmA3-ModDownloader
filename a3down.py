#!/usr/bin/python3
""" 
MIT License

Copyright (c) 2024 Joncantplay.eu

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

from datetime import datetime
from bs4 import BeautifulSoup
from pathlib import Path

## Configuration ##
STEAM_CMD = "steamcmd"  # Alternatively "steamcmd" if package is installed

STEAM_USER = "NAME"
STEAM_PASS = "PASS"

A3_SERVER_ID = "233780 -beta creatordlc"
A3_SERVER_DIR = "/path/to/serverfiles"

A3_WORKSHOP_DIR = Path(A3_SERVER_DIR) / "steamapps/workshop/content/107410"
A3_MODS_DIR = Path(A3_SERVER_DIR) / "mods"
A3_KEYS_DIR = Path(A3_SERVER_DIR) / "keys"
A3_HTML = sys.argv[1]
## Optional: Logging
LOG = True # True = Enabled; False = Disabled
LOG_DIR = "/path/to/log"
LOG_NAME = "FileName"
## End of Configuration ##




UPDATE_PATTERN = re.compile(
    r"workshopAnnouncement.*?<p id=\"(\d+)\">", re.DOTALL)
TITLE_PATTERN = re.compile(
    r"(?<=<div class=\"workshopItemTitle\">)(.*?)(?=<\/div>)", re.DOTALL)
WORKSHOP_CHANGELOG_URL = "https://steamcommunity.com/sharedfiles/filedetails/changelog"

if LOG:
    os.makedirs(LOG_DIR, exist_ok=True)  # Ensure the directory exists
    timestamp = datetime.now().isoformat()
    log_filename = f"{LOG_DIR}/{LOG_NAME}-{timestamp}.log"
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', handlers=[logging.FileHandler(log_filename), logging.StreamHandler()])
else:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', handlers=[logging.StreamHandler()])

def install_dependencies():
    assert 'requests' not in sys.modules
    assert 'beautifulsoup4' not in sys.modules
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requests beautifulsoup4"])

if sys.argv[1] == "setup":
    install_dependencies()

## Functions/Script ##
def log(msg):
    logging.info("{{0:=<{}}}".format(len(msg)).format(""))
    logging.info(msg)
    logging.info("{{0:=<{}}}".format(len(msg)).format(""))

def call_steamcmd(params):
    try:
        result = subprocess.run([STEAM_CMD] + shlex.split(params), text=True)
        logging.info(result.stdout)  # Log combined output and error
        if result.stderr:  # Check if there is any error
            logging.error(f'Error: {result.stderr}')  # Log error
        return result  # Return the result object
    except subprocess.CalledProcessError as e:
                logging.error(f'Error occurred while running steamcmd: {e}')
    except FileNotFoundError as e:
                logging.error(f'File not found error occurred: {e}')
    except PermissionError as e:
                logging.error(f'Permission error occurred: {e}')
    except subprocess.TimeoutExpired as e:
                logging.error(f'Timeout expired error occurred: {e}')
    except Exception as e:
                logging.error(f'An unexpected error occurred: {e}')

def update_server():
    log("Updating A3 server ({})".format(A3_SERVER_ID))
    steam_cmd_params = " +force_install_dir {}".format(A3_SERVER_DIR)
    steam_cmd_params += " +login {} {}".format(STEAM_USER, STEAM_PASS)
    steam_cmd_params += " +app_update {} validate".format(A3_SERVER_ID)
    steam_cmd_params += " +quit"

    call_steamcmd(steam_cmd_params)


def mod_needs_update(mod_id, path):
    if path.is_dir():
        response = requests.get('{}/{}'.format(WORKSHOP_CHANGELOG_URL, mod_id), timeout=5).text
        match = UPDATE_PATTERN.search(response)

        if match:
            updated_at = datetime.fromtimestamp(int(match.group(1)))
            created_at = datetime.fromtimestamp(path.stat().st_ctime)

            return updated_at >= created_at
    return False


def mods(html):
    A3Modlist = {}
    A3Modnames = []
    with open(html, 'r') as file:
        html_content = file.read()
    soup = BeautifulSoup(html_content, 'html.parser')
    mod_containers = soup.find_all('tr', {'data-type': 'ModContainer'})
    if mod_containers:
        for mod_container in mod_containers:
            modname = mod_container.find('td', {'data-type': 'DisplayName'}).text.strip()
            special_characters = "!#$%^&*()[]{};:,./<>?\|`~='+-"
            modname = modname.translate(str.maketrans('', '', special_characters))
            modname = modname.lower().replace(" ", "_").replace("_" * 2, "_")
            A3Modnames.append("@" + modname)
            link = mod_container.find('a', {'data-type': 'Link'})['href']
            mod_id = link.split('=')[-1]
            A3Modlist["@" + modname] = mod_id
    else:
        log("No mods found in the HTML.")
    return A3Modlist, A3Modnames


def update_mods(A3Modlist):
    log("Updating mods")
    if A3Modlist:
        for mod_name, mod_id in A3Modlist.items():
            path = A3_WORKSHOP_DIR / mod_id

            # Check if mod needs to be updated
            if path.is_dir():
                if mod_needs_update(mod_id, path):
                    # Delete existing folder so that we can verify whether the
                    # download succeeded
                    shutil.rmtree(path)
                else:
                    log(f'No update required for {mod_name} ({mod_id})... SKIPPING')
                    return

            # Keep trying until the download actually succeeded
            tries = 0
            while not path.is_dir() and tries < 3:
                log("Updating \"{}\" ({}) | {}".format(mod_name, mod_id, tries + 1))

                steam_cmd_params = " +force_install_dir {}".format(A3_SERVER_DIR)
                steam_cmd_params += " +login {} {}".format(STEAM_USER, STEAM_PASS)
                steam_cmd_params += " +workshop_download_item 107410 {} validate".format(mod_id)
                steam_cmd_params += " +quit"

                call_steamcmd(steam_cmd_params)

                # Sleep for a bit so that we can kill the script if needed
                time.sleep(3)

                tries = tries + 1

            if tries >= 3:
                log("!! Updating mod ID {} failed after {} tries !!".format(mod_id, tries))
    else:
        log("No mod IDs found in the HTML file.")


def lowercase_workshop_dir():
    log("Converting uppercase files/folders to lowercase...")
    subprocess.run(["find", str(A3_WORKSHOP_DIR), "-depth", "-exec", "rename", "-v", "s/(.*)\/([^\/]*)/$1\/\L$2/", "{}", ";"])


def create_mod_symlinks(A3Modlist):
    log("Creating symlinks...")
    for mod_name, mod_id in A3Modlist.items():
        link_path = A3_MODS_DIR / mod_name
        real_path = A3_WORKSHOP_DIR / mod_id
        if real_path.is_dir():
            if not link_path.is_symlink():
                link_path.symlink_to(real_path)
                log("Creating symlink '{}'...".format(link_path))
        else:
            log("Mod '{}' does not exist! ({})".format(mod_name, real_path))


def print_launch_params(A3Modnames):
    log("Generating launch params...")
    rel_path = A3_MODS_DIR.relative_to(A3_SERVER_DIR)
    params = "-mod="
    for mod_name in A3Modnames:
        params += "{}/{}\;".format(rel_path, mod_name)
    logging.info(params)


def copy_keys(A3Modnames, A3Modlist):
    log("Copying server keys...")
    # Check for broken symlinks
    key_path = A3_KEYS_DIR
    for key in os.listdir(A3_KEYS_DIR):
        if key_path.is_symlink():
            log("Removing not needed server key '{}'".format(key))
            key_path.unlink()
    # Update/add new key symlinks
    key_regex = re.compile(r'(key).*', re.I)
    for mod_name in A3Modnames:
        if mod_name not in A3Modlist.items():
            real_path = A3_MODS_DIR / mod_name
            if not real_path.is_dir():
                log("Couldn't copy key for mod '{}', directory doesn't exist.".format(mod_name))
            else:
                dirlist = os.listdir(real_path)
                keyDirs = [x for x in dirlist if re.search(key_regex, x)]
                if keyDirs:
                    keyDir = keyDirs[0]
                    if (real_path / keyDir).is_file():
                        # Key is placed in root directory
                        key = keyDir
                        try:
                            if not key_path.exists():
                                log("Creating symlink to key for mod '{}' ({})".format(mod_name, key))
                                key_path.symlink_to(real_path / key)
                        except OSError as e:
                            logging.error(f'Error occurred while creating symlink: {e}')
                    else:
                        # Key is in a folder
                        for key in os.listdir(real_path / keyDir):
                            real_key_path = real_path / keyDir / key
                            try:
                                if not key_path.exists():
                                    log("Creating symlink to key for mod '{}' ({})".format(mod_name, key))
                                    key_path.symlink_to(real_key_path)
                            except OSError as e:
                                logging.error(f'Error occurred while creating symlink: {e}')
                else:
                    log("!! Couldn't find key folder for mod {} !!".format(mod_name))


def execute_full():
    A3Modlist, A3Modnames = mods(A3_HTML)
    update_server()
    update_mods(A3Modlist)
    lowercase_workshop_dir()
    create_mod_symlinks(A3Modlist)
    copy_keys(A3Modnames, A3Modlist)
    print_launch_params(A3Modnames)


def execute_light():
    A3Modlist, A3Modnames = mods(A3_HTML)
    copy_keys(A3Modnames, A3Modlist)
    print_launch_params(A3Modnames)


if __name__ == "__main__":
    log("Choose a option:")
    print("1. Full Update (With ArmA Server)")
    print("2. Normal Update")
    print("3. Only print Launch options + copy keys")
    print("4. Exit")
    
    choice = input("Option: ")

    if choice == '1':
        update_server()
        execute_full()
    elif choice == '2':
        execute_full()
    elif choice == '3':
        execute_light
    elif choice == '4':
        exit
    else:
        print("Invalid Input.")