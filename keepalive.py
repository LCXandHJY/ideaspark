# -*- coding: utf-8 -*-
"""IdeaSpark 保活守护：
- Flask(5050) 掉线 -> 自动重启 app.py
- Cloudflare 隧道掉线/失效 -> 自动重连，并把最新公网链接写入 CURRENT_URL.txt
用法: pythonw keepalive.py  (无窗口常驻)
"""
import re
import subprocess
import sys
import time
import urllib.request
import pathlib

ROOT = pathlib.Path(r"D:\HuaweiMoveData\Users\Augest\Desktop\trae_test")
APP = ROOT / "ideaspark"
CF = ROOT / "cloudflared.exe"
LOG = APP / "tunnel.log"
OUT = APP / "tunnel_out.log"
URLF = APP / "CURRENT_URL.txt"


def flask_ok():
    try:
        with urllib.request.urlopen("http://127.0.0.1:5050/", timeout=5) as r:
            return r.status == 200
    except Exception:
        return False


def tunnel_url():
    try:
        m = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com",
                      LOG.read_text(encoding="utf-8", errors="ignore"))
        return m.group(0) if m else None
    except Exception:
        return None


def url_ok(url):
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            return r.status == 200
    except Exception:
        return False


def start_flask():
    subprocess.Popen([sys.executable, "app.py"], cwd=str(APP),
                     creationflags=subprocess.CREATE_NO_WINDOW)


def start_tunnel():
    subprocess.run(["taskkill", "/F", "/IM", "cloudflared.exe"], capture_output=True)
    LOG.write_text("", encoding="utf-8")
    return subprocess.Popen(
        [str(CF), "tunnel", "--url", "http://127.0.0.1:5050",
         "--protocol", "http2", "--no-autoupdate"],
        stdout=open(OUT, "w"), stderr=open(LOG, "a"),
        creationflags=subprocess.CREATE_NO_WINDOW)


def cf_running(proc):
    """自己启动的隧道进程是否存活（外部启动的靠 URL 探测兜底）"""
    return proc is not None and proc.poll() is None


def main():
    fails = 0
    tunnel_proc = None
    while True:
        if not flask_ok():
            start_flask()
            time.sleep(6)

        url = tunnel_url()
        alive = bool(url and url_ok(url))
        fails = 0 if alive else fails + 1

        # 仅当 URL 连续探测失败，或自己启动的隧道进程已退出时才重建
        if fails >= 2 or (tunnel_proc is not None and not cf_running(tunnel_proc)):
            tunnel_proc = start_tunnel()
            time.sleep(15)
            new_url = tunnel_url()
            if new_url:
                URLF.write_text(new_url, encoding="utf-8")
                fails = 0
        elif url:
            cur = URLF.read_text().strip() if URLF.exists() else ""
            if cur != url:
                URLF.write_text(url, encoding="utf-8")

        time.sleep(60)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        (APP / "keepalive_err.log").write_text(
            traceback.format_exc(), encoding="utf-8")
        raise
