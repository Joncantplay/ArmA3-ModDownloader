
![Logo](https://cdn.joncantplay.eu/img/github.png)

[![MIT License](https://img.shields.io/badge/License-MIT-green.svg)](https://choosealicense.com/licenses/mit/)
# ArmA3 ModDownloader
Updating/Installing ArmA3 Mods via HTML file
## Features

- **ArmA 3 Server Update**  
  Automatically updates the ArmA 3 server to the latest version.

- **Mod Download via HTML File**  
  - Downloads mods using an HTML file.  
  - If multiple HTML files are provided, a selection menu allows choosing the correct one.

- **Case Conversion (Linux Compatibility)**  
  - Converts uppercase filenames to lowercase to avoid issues on Linux-based servers.

- **Copying Keys to the Key Folder**  
  - Automatically moves required `.bikey` files to the correct key directory.

- **Printing Mod Launch Parameters**  
  - Generates and displays the correct startup parameters for loaded mods.

- **Logging**  
  - Creates and maintains a log file to track actions and errors.

## Usage

Run the script with the following command:
```bash
python3 a3down.py [Option]
```
Available Options:

- `-h`
  Display all available options.

- `-su`, `--ServerUpdate`
  Perform a complete server update.

- `-u`, `--Update`
  Execute a standard update.

- `-fu`, `--ForceUpdate`
  Forcefully update mods, regardless if needed or not.

- `-lo`, `--LaunchOptions`
  Retrieve only the launch options and copy the necessary keys.

- `-cl`, `--clear`
  Remove mods from a specified HTML file.

- `-ca`, `--clearall`
  Remove all mods.

- `-l`, `--lower`
  Convert the workshop directory names to lowercase.

- `-d`, `--debug`
  Enable debugging mode to show which mods require an update and which ones are detected in the HTML file.

Run `./download` to start a new tmux session to let the update run in background

## Settings

Edit the settings.txt file:
| Name         | Value                 | Description |
|-------------|---------------------|-------------|
| **STEAM_CMD**  | `steamcmd`          | Path to SteamCMD (On Linux, use `steamcmd` if the package is installed) |
| **STEAM_USER** | `NAME`              | Steam username |
| **STEAM_PASS** | `PASSWORD`          | Steam password |
|              |                      |  |
| **SERVER_ID**  | `233780`            | ArmA 3 server ID (Add `-beta creatordlc` for Creator DLC content) |
| **SERVER_DIR** | `/path/to/serverfiles` | Path to server files |
| **HTML_DIR**   | `/path/to/htmlfolder`  | Path to the HTML folder |
| **MODS_DIR**   | `/path/to/arma/mods`   | Path to the mods folder |
|              |                      |  |
| **LOG**        | `Boolean`           | `True` = Enable logging; `False` = Disable logging |
| **LOG_DIR**    | `/path/to/logfolder`   | Path to the log folder |
| **LOG_NAME**   | `string`            | Log file name |
|              |                      |  |
| **MAX_TRIES**  | `3`                 | Number of attempts to download a mod before skipping it |

## Required Python Packages
This script requires the following external Python packages:

- `requests`
- `beautifulsoup4`

To install all required packages, you can use the following command:
`pip install requests beautifulsoup4`

## Roadmap

- Adding Support for downloading Workshop missions

## Feedback

If you have any feedback, please reach out to me via [E-Mail](mailto:github@joncantplay.eu) or [Discord](https://discord.gg/bzw7qPya3X).

For bug reports use the [Issues](https://github.com/Joncantplay/ArmA3-ModDownloader/issues) tab
