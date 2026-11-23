"""Lab 7, zad. 2 - strona internetowa z odswiezaniem.

Wbudowany serwer HTTP (http.server) udostepnia:
  /           - strona HTML, ktora co N ms przeladowuje obraz (JS; bez JS: meta refresh)
  /frame.jpg  - ostatnia klatka z kamery (JPEG)
Domyslnie tylko localhost; "Dostep z sieci LAN" otwiera serwer dla innych urzadzen.
"""
import os
import socket
import sys
import threading
import time
import tkinter as tk
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from tkinter import messagebox, ttk

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cv2  # noqa: E402

from kamera import App, run  # noqa: E402

PAGE = """<!doctype html>
<html lang="pl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<noscript><meta http-equiv="refresh" content="{sec}"></noscript>
<title>Kamera USB - podglad</title>
<style>body{{background:#111;color:#eee;font-family:sans-serif;text-align:center;margin:0;padding:12px}}
img{{max-width:100%;border:1px solid #444}}</style></head>
<body><h1>Kamera USB - podglad na zywo</h1>
<img id="cam" src="frame.jpg" alt="obraz z kamery">
<p>Odswiezanie co {ms} ms &middot; ostatnia klatka: <span id="t">-</span></p>
<script>
const img = document.getElementById('cam'), t = document.getElementById('t');
setInterval(() => {{
  const next = new Image();
  next.onload = () => {{ img.src = next.src; t.textContent = new Date().toLocaleTimeString(); }};
  next.src = 'frame.jpg?t=' + Date.now();
}}, {ms});
</script></body></html>"""


class Server:
    """Serwer HTTP w osobnym watku; klatke podaje GUI przez set_frame()."""

    def __init__(self, host, port, refresh_ms):
        self.jpeg = None
        self.refresh_ms = refresh_ms
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                path = self.path.split("?")[0]
                if path == "/":
                    ms = outer.refresh_ms
                    self.reply(PAGE.format(ms=ms, sec=max(1, round(ms / 1000))).encode(), "text/html; charset=utf-8")
                elif path == "/frame.jpg" and outer.jpeg:
                    self.reply(outer.jpeg, "image/jpeg")
                else:
                    self.send_error(404)

            def reply(self, body, ctype):
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        self.httpd = ThreadingHTTPServer((host, port), Handler)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    @property
    def port(self):
        return self.httpd.server_address[1]

    def set_frame(self, frame, quality=80):
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
        if ok:
            self.jpeg = buf.tobytes()

    def stop(self):
        self.httpd.shutdown()
        self.httpd.server_close()


def lan_ip():
    # UDP connect nie wysyla pakietow - tylko wybiera interfejs z trasa
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
        except OSError:
            return "127.0.0.1"


class WwwApp(App):
    TITLE = "Lab 7 - Kamera USB - strona WWW"

    def build_extra(self, panel):
        self.server = None
        self.last_push = 0.0
        box = ttk.LabelFrame(panel, text="Strona internetowa")
        box.pack(fill="x", pady=3)
        row = ttk.Frame(box)
        row.pack(fill="x")
        ttk.Label(row, text="Port:").pack(side="left", padx=2)
        self.port_var = tk.IntVar(value=8080)
        ttk.Entry(row, textvariable=self.port_var, width=7).pack(side="left", padx=2, pady=2)
        ttk.Label(box, text="Odswiezanie strony [ms]").pack(anchor="w", padx=4)
        self.refresh_var = tk.IntVar(value=500)
        tk.Scale(box, variable=self.refresh_var, from_=100, to=5000, resolution=100, orient="horizontal",
                 length=220, command=self.on_refresh).pack(fill="x", padx=4)
        self.lan_var = tk.BooleanVar()
        ttk.Checkbutton(box, text="Dostep z sieci LAN", variable=self.lan_var).pack(anchor="w", padx=4)
        self.srv_btn = ttk.Button(box, text="Uruchom serwer", command=self.toggle_server)
        self.srv_btn.pack(fill="x", padx=4, pady=2)
        self.url_lbl = ttk.Label(box, text="Serwer wylaczony", foreground="gray", wraplength=230)
        self.url_lbl.pack(anchor="w", padx=4, pady=2)

    def on_refresh(self, _=None):
        if self.server:
            self.server.refresh_ms = self.refresh_var.get()

    def toggle_server(self):
        if self.server:
            self.server.stop()
            self.server = None
            self.srv_btn.config(text="Uruchom serwer")
            self.url_lbl.config(text="Serwer wylaczony", foreground="gray")
            return
        host = "0.0.0.0" if self.lan_var.get() else "127.0.0.1"
        try:
            self.server = Server(host, self.port_var.get(), self.refresh_var.get())
        except (OSError, tk.TclError) as e:
            messagebox.showerror("Serwer", f"Nie mozna uruchomic serwera: {e}")
            return
        ip = lan_ip() if self.lan_var.get() else "127.0.0.1"
        self.srv_btn.config(text="Zatrzymaj serwer")
        self.url_lbl.config(text=f"http://{ip}:{self.server.port}/", foreground="green")

    def overlay(self, view):
        # ponytail: max 15 klatek/s do serwera - JPEG kosztuje CPU, strona i tak odswieza rzadziej
        if self.server and time.time() - self.last_push > 1 / 15:
            self.last_push = time.time()
            self.server.set_frame(self.frame)

    def on_close(self):
        if self.server:
            self.server.stop()
        super().on_close()


def self_test():
    import urllib.request
    import numpy as np

    srv = Server("127.0.0.1", 0, 300)
    base = f"http://127.0.0.1:{srv.port}"
    try:
        urllib.request.urlopen(base + "/frame.jpg")
        raise AssertionError("bez klatki powinno byc 404")
    except urllib.error.HTTPError as e:
        assert e.code == 404
    srv.set_frame(np.full((48, 64, 3), 128, np.uint8))
    html = urllib.request.urlopen(base + "/").read().decode()
    assert "setInterval" in html and "300" in html, "strona z odswiezaniem"
    jpg = urllib.request.urlopen(base + "/frame.jpg?t=1").read()
    assert cv2.imdecode(np.frombuffer(jpg, np.uint8), cv2.IMREAD_COLOR).shape == (48, 64, 3)
    srv.stop()
    print("OK - testy przeszly")


if __name__ == "__main__":
    run(WwwApp, self_test)
