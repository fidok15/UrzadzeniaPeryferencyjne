"""Lab 7 - Kamery cyfrowe (wariant: kamera USB, Windows) - zad. 1, wspolna baza.

Wykrywanie kamer, polaczenie, zdjecie (jpg/png/bmp), film (mp4/avi),
zmiana parametrow obrazu (programowe + rozdzielczosc + okno sterownika).
Warianty zad. 2 (zad2_*/) dziedzicza po App i dokladaja build_extra()/overlay().

Uruchomienie: python kamera.py        |  testy bez kamery: python kamera.py --test
"""
import os
import subprocess
import sys
import threading
import time
import tkinter as tk
from datetime import datetime
from tkinter import messagebox, ttk

import cv2
import numpy as np

# DirectShow na Windows: szybsze otwieranie i dziala CAP_PROP_SETTINGS (okno sterownika)
BACKEND = cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY
OUT_DIR = os.path.abspath("nagrania")
RESOLUTIONS = ["640x480", "800x600", "1280x720", "1920x1080"]
VIDEO_CODECS = {"mp4": "mp4v", "avi": "MJPG"}
PREVIEW_MAX = (960, 720)


def find_cameras(max_index=6):
    """Zwraca liste (indeks, szerokosc, wysokosc) kamer, ktore oddaja klatke."""
    found = []
    for i in range(max_index):
        cap = cv2.VideoCapture(i, BACKEND)
        if cap.isOpened():
            ok, frame = cap.read()
            if ok and frame is not None:
                found.append((i, frame.shape[1], frame.shape[0]))
        cap.release()
    return found


def adjust(frame, brightness=0, contrast=1.0, saturation=1.0, gamma=1.0, gray=False, mirror=False):
    """Programowa obrobka klatki BGR. Wynik zawsze 3-kanalowy (dla VideoWriter)."""
    out = frame
    if contrast != 1.0 or brightness != 0:
        out = cv2.convertScaleAbs(out, alpha=contrast, beta=brightness)
    if saturation != 1.0 and not gray:
        hsv = cv2.cvtColor(out, cv2.COLOR_BGR2HSV).astype(np.float32)
        hsv[..., 1] = np.clip(hsv[..., 1] * saturation, 0, 255)
        out = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)
    if gamma != 1.0:
        lut = np.array([((i / 255.0) ** (1.0 / gamma)) * 255 for i in range(256)], np.uint8)
        out = cv2.LUT(out, lut)
    if gray:
        out = cv2.cvtColor(cv2.cvtColor(out, cv2.COLOR_BGR2GRAY), cv2.COLOR_GRAY2BGR)
    if mirror:
        out = cv2.flip(out, 1)
    return out


def stamp():
    return datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]


def save_image(img, prefix, ext="png", jpeg_quality=95):
    """Zapisuje obraz w OUT_DIR, zwraca sciezke albo None."""
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, f"{prefix}_{stamp()}.{ext}")
    return path if cv2.imwrite(path, img, [cv2.IMWRITE_JPEG_QUALITY, int(jpeg_quality)]) else None


def to_photo(img, max_size=PREVIEW_MAX):
    """BGR -> tk.PhotoImage (przez PPM, obslugiwany natywnie przez Tk - bez Pillow)."""
    h, w = img.shape[:2]
    scale = min(max_size[0] / w, max_size[1] / h, 1.0)
    if scale < 1.0:
        img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    return tk.PhotoImage(data=cv2.imencode(".ppm", img)[1].tobytes(), format="PPM")


def show_image_window(root, img, title):
    """Okno z podgladem wyniku (anaglif, HDR)."""
    win = tk.Toplevel(root)
    win.title(title)
    photo = to_photo(img)
    lbl = ttk.Label(win, image=photo)
    lbl.image = photo
    lbl.pack()


class App:
    TITLE = "Lab 7 - Kamera USB"

    def __init__(self, root):
        self.root = root
        root.title(self.TITLE)
        self.cap = None
        self.writer = None
        self.rec_path = None
        self.raw = None    # klatka z kamery bez obrobki
        self.frame = None  # klatka po obrobce (zapisywana)
        self.fps = 0.0
        self.last_t = time.time()
        self.cameras = []
        # odczyt klatek w osobnym watku: cap.read() blokuje, a na macOS w watku GUI potrafi zawiesic Tk
        self.cap_lock = threading.Lock()
        self.grabber = None
        self.latest = None
        self.seq = self.shown_seq = 0

        self.preview = ttk.Label(root, text="Brak obrazu - wykryj i polacz kamere", anchor="center")
        self.preview.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)

        p = ttk.Frame(root)
        p.grid(row=0, column=1, sticky="ns", padx=6, pady=6)

        # --- kamera ---
        box = ttk.LabelFrame(p, text="Kamera")
        box.pack(fill="x", pady=3)
        self.cam_var = tk.StringVar()
        self.cam_combo = ttk.Combobox(box, textvariable=self.cam_var, state="readonly", width=28)
        self.cam_combo.pack(fill="x", padx=4, pady=2)
        row = ttk.Frame(box)
        row.pack(fill="x")
        ttk.Button(row, text="Wykryj kamery", command=self.detect_cameras).pack(side="left", padx=2, pady=2)
        self.conn_btn = ttk.Button(row, text="Polacz", command=self.toggle_connect)
        self.conn_btn.pack(side="left", padx=2)
        row = ttk.Frame(box)
        row.pack(fill="x")
        ttk.Label(row, text="Rozdzielczosc:").pack(side="left", padx=2)
        self.res_var = tk.StringVar(value=RESOLUTIONS[0])
        self.res_combo = ttk.Combobox(row, textvariable=self.res_var, values=RESOLUTIONS, state="readonly", width=10)
        self.res_combo.pack(side="left", padx=2, pady=2)
        self.res_combo.bind("<<ComboboxSelected>>", lambda e: self.apply_resolution())
        if sys.platform == "win32":
            ttk.Button(box, text="Ustawienia sterownika kamery",
                       command=lambda: self.cap and self.cap.set(cv2.CAP_PROP_SETTINGS, 1)).pack(fill="x", padx=4, pady=2)

        # --- parametry obrazu ---
        box = ttk.LabelFrame(p, text="Parametry obrazu")
        box.pack(fill="x", pady=3)
        self.params = {}
        for key, label, lo, hi, default in [
            ("brightness", "Jasnosc", -100, 100, 0),
            ("contrast", "Kontrast", 0.2, 3.0, 1.0),
            ("saturation", "Nasycenie", 0.0, 3.0, 1.0),
            ("gamma", "Gamma", 0.2, 3.0, 1.0),
        ]:
            ttk.Label(box, text=label).pack(anchor="w", padx=4)
            var = tk.DoubleVar(value=default)
            tk.Scale(box, variable=var, from_=lo, to=hi, resolution=1 if key == "brightness" else 0.05,
                     orient="horizontal", length=220).pack(fill="x", padx=4)
            self.params[key] = (var, default)
        self.gray_var, self.mirror_var = tk.BooleanVar(), tk.BooleanVar()
        ttk.Checkbutton(box, text="Skala szarosci", variable=self.gray_var).pack(anchor="w", padx=4)
        ttk.Checkbutton(box, text="Odbicie lustrzane", variable=self.mirror_var).pack(anchor="w", padx=4)
        ttk.Button(box, text="Resetuj parametry", command=self.reset_params).pack(fill="x", padx=4, pady=2)

        # --- zapis ---
        box = ttk.LabelFrame(p, text="Zapis")
        box.pack(fill="x", pady=3)
        row = ttk.Frame(box)
        row.pack(fill="x")
        self.photo_fmt = tk.StringVar(value="jpg")
        ttk.Combobox(row, textvariable=self.photo_fmt, values=["jpg", "png", "bmp"], state="readonly",
                     width=5).pack(side="left", padx=2, pady=2)
        ttk.Button(row, text="Zrob zdjecie", command=self.take_photo).pack(side="left", fill="x", expand=True, padx=2)
        ttk.Label(box, text="Jakosc JPEG [%]").pack(anchor="w", padx=4)
        self.jpeg_var = tk.IntVar(value=95)
        tk.Scale(box, variable=self.jpeg_var, from_=10, to=100, orient="horizontal", length=220).pack(fill="x", padx=4)
        row = ttk.Frame(box)
        row.pack(fill="x")
        self.video_fmt = tk.StringVar(value="mp4")
        ttk.Combobox(row, textvariable=self.video_fmt, values=list(VIDEO_CODECS), state="readonly",
                     width=5).pack(side="left", padx=2, pady=2)
        self.rec_btn = ttk.Button(row, text="Start nagrywania", command=self.toggle_record)
        self.rec_btn.pack(side="left", fill="x", expand=True, padx=2)
        ttk.Button(box, text="Otworz folder z plikami", command=self.open_folder).pack(fill="x", padx=4, pady=2)

        self.build_extra(p)

        self.status = ttk.Label(p, text="Rozlaczono", wraplength=240)
        self.status.pack(fill="x", pady=6)

        root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.detect_cameras()
        self.loop()

    # --- haki dla wariantow zad. 2 ---
    def build_extra(self, panel):
        """Dodatkowy panel po prawej stronie."""

    def overlay(self, view):
        """Rysowanie na podgladzie (view to kopia self.frame, nie trafia do plikow)."""

    # --- kamera ---
    def detect_cameras(self):
        if self.cap:
            messagebox.showinfo("Kamera", "Najpierw rozlacz kamere.")
            return
        self.status.config(text="Szukam kamer...")
        self.root.update_idletasks()
        self.cameras = find_cameras()
        names = [f"Kamera {i} ({w}x{h})" for i, w, h in self.cameras]
        self.cam_combo.config(values=names)
        if names:
            self.cam_combo.current(0)
        self.status.config(text=f"Znaleziono kamer: {len(names)}")

    def toggle_connect(self):
        if self.cap:
            self.disconnect()
            return
        if not self.cameras or self.cam_combo.current() < 0:
            messagebox.showwarning("Kamera", "Brak wybranej kamery.")
            return
        index = self.cameras[self.cam_combo.current()][0]
        self.cap = cv2.VideoCapture(index, BACKEND)
        if not self.cap.isOpened():
            self.cap = None
            messagebox.showerror("Kamera", f"Nie mozna otworzyc kamery {index}.")
            return
        self.apply_resolution()
        self.latest = None
        self.grabber = threading.Thread(target=self.grab_loop, args=(self.cap,), daemon=True)
        self.grabber.start()
        self.conn_btn.config(text="Rozlacz")

    def grab_loop(self, cap):
        while self.cap is cap:
            with self.cap_lock:
                ok, frame = cap.read()
            if ok and frame is not None:
                self.latest = frame
                self.seq += 1
            else:
                time.sleep(0.02)

    def disconnect(self):
        self.stop_record()
        cap, self.cap = self.cap, None
        self.grabber.join(timeout=2)
        cap.release()
        self.raw = self.frame = None
        self.preview.config(image="", text="Rozlaczono")
        self.conn_btn.config(text="Polacz")
        self.status.config(text="Rozlaczono")

    def apply_resolution(self):
        if not self.cap:
            return
        if self.writer:
            messagebox.showinfo("Kamera", "Nie mozna zmienic rozdzielczosci podczas nagrywania.")
            return
        w, h = map(int, self.res_var.get().split("x"))
        with self.cap_lock:
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)

    def reset_params(self):
        for var, default in self.params.values():
            var.set(default)
        self.gray_var.set(False)
        self.mirror_var.set(False)

    def process(self, raw):
        p = {k: v.get() for k, (v, _) in self.params.items()}
        return adjust(raw, gray=self.gray_var.get(), mirror=self.mirror_var.get(), **p)

    # --- zapis ---
    def take_photo(self, prefix="foto"):
        if self.frame is None:
            messagebox.showwarning("Zdjecie", "Brak obrazu z kamery.")
            return None
        path = save_image(self.frame, prefix, self.photo_fmt.get(), self.jpeg_var.get())
        if not path:
            messagebox.showerror("Zdjecie", "Nie udalo sie zapisac zdjecia.")
            return None
        self.status.config(text=f"Zapisano: {os.path.basename(path)}")
        return path

    def toggle_record(self):
        if self.writer:
            self.stop_record()
            return
        if self.frame is None:
            messagebox.showwarning("Film", "Brak obrazu z kamery.")
            return
        os.makedirs(OUT_DIR, exist_ok=True)
        ext = self.video_fmt.get()
        h, w = self.frame.shape[:2]
        # ponytail: fps nagrania = zmierzone fps podgladu; przy mocno zmiennym fps film moze lekko przyspieszac
        fps = self.fps if 1 <= self.fps <= 60 else 20.0
        self.rec_path = os.path.join(OUT_DIR, f"film_{stamp()}.{ext}")
        self.writer = cv2.VideoWriter(self.rec_path, cv2.VideoWriter_fourcc(*VIDEO_CODECS[ext]), fps, (w, h))
        if not self.writer.isOpened():
            self.writer = None
            messagebox.showerror("Film", f"Nie mozna utworzyc pliku {ext}.")
            return
        self.rec_btn.config(text="Stop nagrywania")
        self.res_combo.config(state="disabled")

    def stop_record(self):
        if self.writer:
            self.writer.release()
            self.writer = None
            self.status.config(text=f"Zapisano: {os.path.basename(self.rec_path)}")
        self.rec_btn.config(text="Start nagrywania")
        self.res_combo.config(state="readonly")

    def open_folder(self):
        os.makedirs(OUT_DIR, exist_ok=True)
        if sys.platform == "win32":
            os.startfile(OUT_DIR)
        else:
            subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", OUT_DIR])

    # --- petla obrazu ---
    def loop(self):
        if self.cap and self.seq != self.shown_seq and self.latest is not None:
            self.shown_seq = self.seq
            now = time.time()
            dt = now - self.last_t
            self.last_t = now
            if dt > 0:
                self.fps = 0.9 * self.fps + 0.1 * (1 / dt)
            self.raw = self.latest
            self.frame = self.process(self.raw)
            if self.writer:
                self.writer.write(self.frame)
            self.show(self.frame.copy())
        self.root.after(10, self.loop)

    def show(self, view):
        self.overlay(view)
        h, w = view.shape[:2]
        if self.writer:
            cv2.circle(view, (20, 20), 8, (0, 0, 255), -1)
            cv2.putText(view, "REC", (34, 27), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
        img = to_photo(view)
        self.preview.config(image=img, text="")
        self.preview.image = img
        if not str(self.status.cget("text")).startswith("Zapisano"):
            self.status.config(text=f"{w}x{h}  {self.fps:.1f} fps" + ("  REC" if self.writer else ""))

    def on_close(self):
        if self.cap:
            self.disconnect()
        self.root.destroy()


def run(app_class, test):
    """Wspolny main dla bazy i wariantow."""
    if "--test" in sys.argv:
        test()
    else:
        root = tk.Tk()
        app_class(root)
        root.mainloop()


def self_test():
    rng = np.random.default_rng(0)
    img = rng.integers(0, 256, (120, 160, 3), dtype=np.uint8)
    assert np.array_equal(adjust(img), img), "parametry domyslne nie moga zmieniac obrazu"
    g = adjust(img, gray=True)
    assert g.shape == img.shape and np.array_equal(g[..., 0], g[..., 2]), "szarosc: 3 rowne kanaly"
    assert adjust(img, brightness=50).mean() > img.mean(), "jasnosc"
    assert np.array_equal(adjust(img, mirror=True)[:, 0], img[:, -1]), "lustro"
    print("OK - testy przeszly")


if __name__ == "__main__":
    run(App, self_test)
