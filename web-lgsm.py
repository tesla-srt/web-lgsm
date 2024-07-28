#!/usr/bin/env python3
# Main Web LGSM Wrapper Script!
# Rewritten in Python by John R. July 2024.

import os
import sys
import signal
import subprocess

# Where we at with it, Ali?
SCRIPTPATH = os.path.dirname(os.path.abspath(__file__))

def signalint_handler(sig, frame):
    # Suppress stderr for debug ctrl + c stack trace.
    with open(os.devnull, 'w') as fnull:
        sys.stdout = fnull
        sys.stderr = fnull
        sys.stdout = sys.__stdout__
        print('\r [!] Ctrl + C received. Shutting down...')

    exit(0)

def run_command_popen(command):
    """Runs a command through a subprocess.Popen shell"""
    process = subprocess.Popen(
        command,
        shell=True,
        executable='/bin/bash',
        stdin=subprocess.PIPE,
        stdout=None,  # Direct output to the terminal.
        stderr=None,  # Direct error output to the terminal.
        text=True,
        env=os.environ
    )

    # Wait for the process to complete.
    process.wait()

def relaunch_in_venv():
    """Activate the virtual environment and relaunch the script."""
    venv_path = SCRIPTPATH + '/venv/bin/activate'
    if not os.path.isfile(venv_path):
        exit(f" [!] Virtual environment not found at {venv_path}\n" +
             "Create a virtual environment using the following command:\n" +
             "\tpython3 -m venv venv")

    # Activate the virtual environment and re-run the script.
    activate_command = f'source {venv_path} && exec python3 {" ".join(sys.argv)}'
    signal.signal(signal.SIGINT, signalint_handler)

    run_command_popen(activate_command)

# Protection in case user is not in venv.
if os.getenv('VIRTUAL_ENV') is None:
    relaunch_in_venv()
    exit(0)

# Continue imports once we know we're in a venv.
import json
import time
import getopt
import shutil
import string
import getpass
import configparser
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash
from app import db, main as appmain
from app.models import User
from app.utils import contains_bad_chars, check_and_get_lgsmsh

# Import config data.
config = configparser.ConfigParser()
config.read(os.path.join(SCRIPTPATH, 'main.conf'))
# TODO: Put try except around this to catch case where config settings not set.
HOST = config['server']['host']
PORT = config['server']['port']

os.environ['COLUMNS'] = '80'
os.environ['LINES'] = '50'
os.environ['TERM'] = 'xterm-256color'

# Global options hash.
O = { "verbose" : False,
        "check" : False,
         "auto" : False,
    "test_full" : False }

def stop_server():
    result = subprocess.run(["pkill", "gunicorn"], capture_output=True)
    if result.returncode == 0:
        print(" [*] Server Killed!")
    else:
        print(" [!] Server Not Running!")

def check_status():
    result = subprocess.run(["pgrep", "-f", "gunicorn.*web-lgsm"], capture_output=True)
    if result.returncode == 0:
        print(" [*] Server Currently Running.")
    else:
        print(" [*] Server Not Running.")

def start_server():
    status_result = subprocess.run(["pgrep", "-f", "gunicorn.*web-lgsm"], capture_output=True)
    if status_result.returncode == 0:
        print("Server Already Running!")
        exit()

    print(f"""
 ╔═══════════════════════════════════════════════════════╗
 ║ Welcome to the Web LGSM! ☁️  🕹️                         ║
 ║                                                       ║
 ║ You can access the web-lgsm via the url below!        ║
 ║                                                       ║
 ║ http://{HOST}:{PORT}/                               ║
 ║                                                       ║
 ║ You can kill the web server with:                     ║
 ║                                                       ║
 ║ ./web-lgsm.py --stop                                  ║
 ║                                                       ║
 ║ Please Note: It is strongly advisable to firewall off ║
 ║ port {PORT} to the outside world and then proxy this   ║
 ║ server to a real web server such as Apache or Nginx   ║
 ║ with SSL encryption! See the Readme for more info.    ║
 ╚═══════════════════════════════════════════════════════╝
    """)

    # Try to start the gunicorn server as a detached proc.
    try:
        process = subprocess.Popen(
            ["gunicorn", 
             "--access-logfile", f"{SCRIPTPATH}/web-lgsm.log",
             f"--bind={HOST}:{PORT}",
             "--daemon",
             "--worker-class", "gevent",
             "app:main()"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        print(f" [*] Launched Gunicorn server with PID: {process.pid}")
    except Exception as e:
        print(f" [!] Failed to launch Gunicorn server: {e}")

def start_debug():
    """Starts the app in debug mode"""
    from app import main
    # For clean ctrl + c handling.
    signal.signal(signal.SIGINT, signalint_handler)
    app = main()
    app.run(debug=True, host=HOST, port=PORT)

def validate_password(username, password1, password2):
    # Make sure required form items are supplied.
    for form_item in (username, password1, password2):
        if form_item is None or form_item == "":
            return False, "Missing required form field(s)!"

        # Check input lengths.
        if len(form_item) > 150:
            return False, "Form field too long!"

    # Setup rudimentary password strength counter.
    lower_alpha_count = 0
    upper_alpha_count = 0
    number_count = 0
    special_char_count = 0

    # Adjust password strength values.
    for char in list(password1):
        if char in string.ascii_lowercase:
            lower_alpha_count += 1
        elif char in string.ascii_uppercase:
            upper_alpha_count += 1
        elif char in string.digits:
            number_count += 1
        else:
            special_char_count += 1

    # Verify password passes basic strength tests.
    if upper_alpha_count < 1 and number_count < 1 and special_char_count < 1:
        return False, "Password doesn't meet criteria! Must contain: an upper case character, a number, and a special character"

    # To try to nip xss & template injection in the bud.
    if contains_bad_chars(username):
        return False, "Username contains illegal character(s)"

    if password1 != password2:
        return False, "Passwords don't match!"

    if len(password1) < 12:
        return False, "Password is too short!"

    return True, ""

def change_password():
    """Change the password for a given user."""

    username = input("Enter username: ")
    password1 = getpass.getpass("Enter new password: ")
    password2 = getpass.getpass("Confirm new password: ")

    # Validate the new password
    is_valid, message = validate_password(username, password1, password2)

    if not is_valid:
        print(f"Error: {message}")
        return

    # Find the user in the database
    user = User.query.filter_by(username=username).first()

    if user is None:
        print("Error: User not found!")
        return

    # Update the user's password hash
    user.password = generate_password_hash(password1, method='pbkdf2:sha256')
    db.session.commit()

    print("Password updated successfully!")


def update_gs_list():
    """Updates game server json by parsing latest `linuxgsm.sh list` output"""
    lgsmsh = SCRIPTPATH + '/scripts/linuxgsm.sh'
    check_and_get_lgsmsh(lgsmsh)

    servers_list = os.popen(f"{lgsmsh} list").read()

    short_names = []
    long_names = []
    gs_mapping = dict()

    for line in servers_list.split('\n'):
        if len(line.strip()) == 0:
            continue
        if "serverlist.csv" in line:
            continue
        short_name = line.split()[0]
        long_name = ' '.join(line.split()[1:]).replace("'", "").replace("&", "and")

        short_names.append(short_name)
        long_names.append(long_name)
        gs_mapping[short_name] = long_name

    test_json = 'test_data.json'
    test_src = os.path.join(SCRIPTPATH, test_json)
    test_dst = os.path.join(SCRIPTPATH, f'json/{test_json}')
    map_json = open(test_json, "w")
    map_json.write(json.dumps(gs_mapping, indent = 4))
    map_json.close()
    compare_and_move(test_src, test_dst)

    gs_dict = {
        "servers": short_names,
        "server_names": long_names
    }

    servers_json = 'game_servers.json'
    gs_src = os.path.join(SCRIPTPATH, servers_json)
    gs_dst = os.path.join(SCRIPTPATH, f'json/{servers_json}')
    gs_json = open(servers_json, "w")
    gs_json.write(json.dumps(gs_dict, indent = 4))
    gs_json.close()
    compare_and_move(gs_src, gs_dst)

def compare_and_move(src_file, dst_file):
    """Diff's two files and moves src to dst if they differ."""
    file_name = os.path.basename(src_file)
    try:
        with open(src_file, 'r') as file1, open(dst_file, 'r') as file2:
            src_content = file1.read()
            dst_content = file2.read()

        if src_content != dst_content:
            print(f" [*] Backing up {file_name} to {file_name}.bak")
            shutil.copy(dst_file, dst_file+'.bak')
            shutil.move(src_file, dst_file)
            print(f" [!] File {file_name} JSON updated!")
        else:
            os.remove(src_file)
            print(f" [*] File {file_name} JSON already up to date.")
    except FileNotFoundError as e:
        print(f"Error: {e}")
    except IOError as e:
        print(f"Error: {e}")

def run_command(command):
    if O['verbose']:
        print(f" [*] Running command: {command}")

    result = subprocess.run(command, shell=True, capture_output=True, text=True, env=os.environ)

    if O['verbose']:
        print(result.stdout.strip())

    return result.stdout.strip()

def get_git_info():
    upstream = '@{u}'
    local = run_command('git rev-parse @')
    remote = run_command(f'git rev-parse {upstream}')
    base = run_command(f'git merge-base @ {upstream}')
    return local, remote, base

def backup_file(filename):
    if not os.path.isfile(filename):
        print(f" [!] Warning: The file '{filename}' does not exist. No backup created!")
        return None

    epoc = int(time.time())
    backup_filename = f"{filename}.{epoc}.bak"
    os.rename(filename, backup_filename)
    print(f" [*] Backing up {filename} to {backup_filename}")
    return backup_filename

def backup_dir(dirname):
    if not os.path.isdir(dirname):
        print(f" [!] Warning: The directory '{dirname}' does not exist. No backup created!")
        return None

    epoc = int(time.time())
    backup_dirname = f"{dirname}.{epoc}.bak"
    shutil.copytree(dirname, backup_dirname)
    print(f" [*] Backing up {dirname} to {backup_dirname}")
    return backup_dirname

def update_weblgsm():
    local, remote, base = get_git_info()

    if local == remote:
        print(" [*] Web LGSM already up to date!")
        return

    elif local == base:
        print(" [!] Update Required!")
        if O["check"]:
            return

        if not O["auto"]:
            resp = input(" [*] Would you like to update now? (y/n): ")
            if resp.lower() != 'y':
                exit()

        backup_file('main.conf')

        run_command('git clean -f')

        print(" [*] Pulling update from github...")
        run_command('git pull')

        epoc = int(time.time())
        print(f" [*] Backing up venv to venv.{epoc}.bak and creating a new one.")
        backup_dir('venv')
        run_command('python3 -m venv venv')
        run_command('source venv/bin/activate')
        print(" [*] Installing new pip reqs...")
        run_command('python3 -m pip install -r requirements.txt')
        print(" [*] Update completed!")
        return

    elif remote == base:
        print(" [!] Local ahead of remote, need push?", file=sys.stderr)
        print(" [-] Note: Normal users should not see this.", file=sys.stderr)
        sys.exit(1)

    print(" [!] Something has gone horribly wrong!", file=sys.stderr)
    print(" [-] It's possible your local repo has diverged.", file=sys.stderr)
    sys.exit(2)

def check_sudo():
    try:
        # Run the sudo command with the -v option to validate the current timestamp.
        result = subprocess.run(['sudo', '-v'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode != 0:
            print(" [*] No active sudo tty ticket. Please run the script with an active sudo session.")
            sys.exit(1)
    except Exception as e:
        print(f" [!] An error occurred while checking sudo status: {e}")
        sys.exit(1)

def run_tests():
    # Source env vars.
    env_path = os.path.join(SCRIPTPATH, 'tests/test.vars')
    load_dotenv(dotenv_path=env_path)
    os.environ['HOME'] = SCRIPTPATH
    os.environ['APP_PATH'] = SCRIPTPATH

    if O['verbose']:
        for key, value in os.environ.items():
            print(f'{key}={value}')

    # Backup Database.
    db_file = os.path.join(SCRIPTPATH, 'app/database.db')
    db_backup = backup_file(db_file)

    # Setup Mockcraft testdir.
    mockcraft_dir = os.path.join(SCRIPTPATH, 'tests/test_data/Mockcraft')
    cfg_dir = os.path.join(mockcraft_dir, 'lgsm/config-lgsm/mcserver/')
    if not os.path.isdir(mockcraft_dir):
        # will make mockcraft dir in the process.
        os.makedirs(cfg_dir)

        os.chdir(mockcraft_dir)
        run_command("wget -O linuxgsm.sh https://linuxgsm.sh")
        run_command("chmod +x linuxgsm.sh")
        run_command("./linuxgsm.sh mcserver")
        os.chdir(SCRIPTPATH)

    # Reset test server cfg.
    common_cfg = os.path.join(SCRIPTPATH, 'tests/test_data/common.cfg')
    shutil.copy(common_cfg, cfg_dir)

    # Enable verbose even if disabled by default just for test printing.
    if not O['verbose']:
        O['verbose'] = True

    if O['test_full']:
        # Need to get a sudo tty ticket for full game server install.
        check_sudo()
        # Backup Existing MC install, if one exists.
        mcdir = os.path.join(SCRIPTPATH, 'Minecraft')
        if os.path.isdir(mcdir):
            backup_dir(mcdir)

            # Then torch dir.
            shutil.rmtree(mcdir)

        run_command_popen('python -m pytest -vvv --maxfail=1')

    else:
        run_command_popen("python -m pytest -v -k 'not test_full_game_server_install and not test_game_server_start_stop and not test_console_output' --maxfail=1")

    # Restore Database.
    if os.path.isfile(db_backup):
        shutil.move(db_backup, db_file)


def print_help():
    """Prints help menu"""
    print("""
  ╔══════════════════════════════════════════════════════════╗  
  ║ Usage: web-lgsm.py [options]                             ║
  ║                                                          ║
  ║   Options:                                               ║
  ║                                                          ║
  ║   -h, --help        Prints this help menu                ║
  ║   -s, --start       Starts the server (default no args)  ║
  ║   -q, --stop        Stop the server                      ║
  ║   -r, --restart     Restart the server                   ║
  ║   -m, --status      Show server status                   ║
  ║   -d, --debug       Start server in debug mode           ║
  ║   -v, --verbose     More verbose output                  ║
  ║   -p, --passwd      Change web user password             ║
  ║   -u, --update      Update web-lgsm version              ║
  ║   -c, --check       Check if an update is available      ║
  ║   -a, --auto        Run an auto update                   ║
  ║   -f, --fetch_json  Fetch latest game servers json       ║
  ║   -t, --test        Run project's pytest tests (short)   ║
  ║   -x, --test_full   Run ALL project's pytest tests       ║
  ╚══════════════════════════════════════════════════════════╝
    """)
    exit()

def main(argv):
    try:
        longopts = ["help", "start", "stop", "status", "restart", "debug",
                    "verbose", "passwd", "update", "check", "auto", "fetch_json",
                    "test", "test_full"]
        opts, args = getopt.getopt(argv, "hsmrqdvpucaftx", longopts)
    except getopt.GetoptError:
        print_help()

    # If no args, start the server.
    if not opts and not args:
        start_server()
        return

    # Push required opts to global dict.
    for opt, _ in opts:
        if opt in ("-v", "--verbose"):
            O["verbose"] = True
        if opt in ("-c", "--check"):
            O["check"] = True
        if opt in ("-a", "--auto"):
            O["auto"] = True
        if opt in ("-x", "--test_full"):
            O["test_full"] = True

    # Do the needful based on opts.
    for opt, _ in opts:
        if opt in ("-h", "--help"):
            print_help()
        elif opt in ("-s", "--start"):
            start_server()
            return
        elif opt in ("-m", "--status"):
            check_status()
            return
        elif opt in ("-r", "--restart"):
            stop_server()
            time.sleep(2)
            start_server()
            return
        elif opt in ("-q", "--stop"):
            stop_server()
            return
        elif opt in ("-d", "--debug"):
            start_debug()
            return
        elif opt in ("-u", "--update", "-c", "--check", "-a", "--auto"):
            update_weblgsm()
            return
        elif opt in ("-p", "--passwd"):
            # Technically, needs run in app context.
            app = appmain()
            with app.app_context():
                change_password()
            return
        elif opt in ("-f", "--fetch_json"):
            update_gs_list()
            return
        elif opt in ("-t", "--test", "-x", "--test_full"):
            run_tests()
            return

if __name__ == "__main__":
    main(sys.argv[1:])

