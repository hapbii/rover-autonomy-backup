"""Local deployment helper. Credentials are prompted, never saved or printed."""

import getpass
import json
import sys
import time
from pathlib import Path

import paramiko


def run(client, request, password=None):
    command = request.get("command", "python3 -u -")
    remote_in, remote_out, _ = client.exec_command(command)
    channel = remote_out.channel
    try:
        if request.get("sudo"):
            if password is None or "sudo -k -S" not in command:
                raise ValueError("Sudo requests must force password consumption with sudo -k -S")
            remote_in.write(password + "\n")
            remote_in.flush()
        if request.get("script"):
            remote_in.write(Path(request["script"]).read_text(encoding="utf-8"))
            remote_in.flush()
        channel.shutdown_write()
        deadline = time.monotonic() + request.get("timeout", 300)
        while True:
            if channel.recv_ready():
                print(channel.recv(32768).decode("utf-8", errors="replace"), end="", flush=True)
            if channel.recv_stderr_ready():
                print(channel.recv_stderr(32768).decode("utf-8", errors="replace"), end="", flush=True)
            if channel.exit_status_ready() and not channel.recv_ready() and not channel.recv_stderr_ready():
                print(json.dumps({"exit_code": channel.recv_exit_status()}), flush=True)
                return
            if time.monotonic() > deadline:
                raise TimeoutError("Remote command exceeded its deadline")
            time.sleep(0.1)
    finally:
        channel.close()


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    client = paramiko.SSHClient()
    client.load_system_host_keys(str(Path.home() / ".ssh/known_hosts"))
    try:
        password = getpass.getpass("SSH password: ")
        client.connect("192.168.50.34", username="takyeji", password=password,
                       timeout=12, auth_timeout=12, look_for_keys=False, allow_agent=False)
        client.get_transport().set_keepalive(15)
        print(json.dumps({"connected": "takyeji@192.168.50.34"}), flush=True)
        for line in sys.stdin:
            if not line.strip():
                continue
            try:
                request = json.loads(line)
                if request.get("op") == "close":
                    break
                if request.get("op") == "put":
                    with client.open_sftp() as transfer:
                        transfer.put(request["local"], request["remote"])
                    print(json.dumps({"uploaded": request["remote"]}), flush=True)
                elif request.get("op") == "get":
                    Path(request["local"]).parent.mkdir(parents=True, exist_ok=True)
                    with client.open_sftp() as transfer:
                        transfer.get(request["remote"], request["local"])
                    print(json.dumps({"downloaded": request["local"]}), flush=True)
                else:
                    run(client, request, password)
            except Exception as error:
                print(json.dumps({"error": type(error).__name__, "detail": str(error)}), flush=True)
    finally:
        client.close()


if __name__ == "__main__":
    main()
