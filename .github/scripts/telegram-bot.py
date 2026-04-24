#!/usr/bin/env python3
import json
import os
import subprocess
import time
import urllib.parse
import urllib.request

TOKEN = os.environ["TG_TOKEN"]
CHAT_ID = str(os.environ["TG_CHAT_ID"])
PANEL_URL = os.environ.get("PANEL_URL", "")
TMATE_URL = os.environ.get("TMATE_URL", "")
API = f"https://api.telegram.org/bot{TOKEN}"


def tg(method, **params):
    data = urllib.parse.urlencode(params).encode()
    try:
        with urllib.request.urlopen(f"{API}/{method}", data=data, timeout=30) as r:
            return json.loads(r.read())
    except Exception as e:
        print("tg err:", e)
        return {}


def send(text):
    for i in range(0, len(text), 3500):
        tg("sendMessage", chat_id=CHAT_ID, text=text[i:i + 3500])


def sh(cmd, timeout=30):
    try:
        r = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=timeout
        )
        return (r.stdout + r.stderr).strip() or "(no output)"
    except subprocess.TimeoutExpired:
        return "(timeout)"


def cmd_start():
    send(
        "Bot Pterodactyl siap.\n\n"
        "/url   - URL panel\n"
        "/ssh   - SSH tmate\n"
        "/status - cek wings/docker/nginx\n"
        "/fix   - regenerate config + restart wings\n"
        "/log   - 40 baris log wings\n"
        "/restart - restart semua service\n"
        "/info  - resource runner"
    )


def cmd_url():
    send(f"Panel: {PANEL_URL or '(belum siap)'}")


def cmd_ssh():
    send(f"SSH: {TMATE_URL or '(belum siap)'}")


def cmd_status():
    out = []
    out.append("== Wings ==")
    out.append(sh("ps aux | grep -i '[w]ings' | head -3 || echo MATI"))
    out.append("\n== Port 8080 ==")
    out.append(sh("ss -tlnp 2>/dev/null | grep :8080 || echo NOT LISTEN"))
    out.append("\n== Docker ==")
    out.append(sh("docker info 2>&1 | head -3"))
    out.append("\n== Nginx ==")
    out.append(sh("systemctl is-active nginx"))
    send("\n".join(out))


def cmd_log():
    send("== /tmp/wings.log ==\n" + sh("tail -40 /tmp/wings.log"))


def cmd_fix():
    send("Memulai fix... (regenerate config + restart wings)")
    steps = []

    nid = sh(
        "cd /var/www/pterodactyl && php artisan tinker "
        "--execute=\"echo \\Pterodactyl\\Models\\Node::value('id');\" 2>/dev/null "
        "| tail -1 | tr -dc '0-9'"
    )
    if not nid:
        send("Gagal: gak ada node di DB. Bikin manual via panel dulu.")
        return
    steps.append(f"Node ID: {nid}")

    sh("pkill -9 wings 2>/dev/null; sleep 2")
    steps.append("Wings di-stop")

    sh(
        f"cd /var/www/pterodactyl && php artisan p:node:configuration {nid} "
        "| tee /etc/pterodactyl/config.yml > /dev/null"
    )
    head = sh("head -3 /etc/pterodactyl/config.yml")
    if "uuid" not in head and "debug" not in head:
        send(f"Config gagal generate:\n{head}")
        return
    steps.append("Config OK")

    sh("systemctl start docker 2>/dev/null; (dockerd > /tmp/docker.log 2>&1 &) ; sleep 3")
    steps.append("Docker started")

    sh(
        "nohup /usr/local/bin/wings --config /etc/pterodactyl/config.yml "
        "> /tmp/wings.log 2>&1 &"
    )
    time.sleep(6)

    if "wings" in sh("ps aux | grep -v grep | grep -i wings"):
        steps.append("Wings hidup")
    else:
        steps.append("Wings GAGAL hidup")

    steps.append("\n== tail wings.log ==")
    steps.append(sh("tail -15 /tmp/wings.log"))
    send("\n".join(steps))


def cmd_restart():
    send("Restart nginx + php-fpm + redis + mariadb...")
    sh("systemctl restart nginx php8.2-fpm redis-server mariadb")
    cmd_fix()


def cmd_info():
    out = sh("uptime; echo; free -h; echo; df -h /")
    send(out)


HANDLERS = {
    "/start": cmd_start,
    "/url": cmd_url,
    "/ssh": cmd_ssh,
    "/status": cmd_status,
    "/log": cmd_log,
    "/fix": cmd_fix,
    "/restart": cmd_restart,
    "/info": cmd_info,
}


def main():
    send("Bot Pterodactyl ON. Ketik /start untuk daftar perintah.")
    offset = 0
    while True:
        try:
            data = tg("getUpdates", offset=offset, timeout=25)
            for upd in data.get("result", []):
                offset = upd["update_id"] + 1
                msg = upd.get("message") or {}
                if str(msg.get("chat", {}).get("id")) != CHAT_ID:
                    continue
                text = (msg.get("text") or "").strip().split()[0].lower()
                fn = HANDLERS.get(text)
                if fn:
                    try:
                        fn()
                    except Exception as e:
                        send(f"Error: {e}")
                elif text.startswith("/"):
                    send("Perintah tidak dikenal. /start")
        except Exception as e:
            print("loop err:", e)
            time.sleep(3)


if __name__ == "__main__":
    main()
