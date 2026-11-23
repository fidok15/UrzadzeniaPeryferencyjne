"""Lab 7, zad. 2 - fotografia HDR.

Seria zdjec o roznej ekspozycji -> wyrownanie (AlignMTB) -> fuzja ekspozycji Mertensa
(nie wymaga znajomosci czasow naswietlania) -> wynik 8-bit zapisany jako png/jpg.

Seria automatyczna: program ustawia CAP_PROP_EXPOSURE (DirectShow: log2 sekund, np. -8 = 1/256 s).
Jesli kamera ignoruje ekspozycje: seria reczna - zmieniaj ekspozycje w "Ustawieniach
sterownika kamery" i klikaj "Dodaj klatke".
"""
import os
import sys
import tkinter as tk
from tkinter import messagebox, ttk

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cv2  # noqa: E402
import numpy as np  # noqa: E402

from kamera import App, run, save_image, show_image_window  # noqa: E402

DROP_FRAMES = 6  # kamera potrzebuje kilku klatek, zeby zastosowac nowa ekspozycje
AUTO_EXP_MANUAL, AUTO_EXP_AUTO = 0.25, 0.75  # wartosci CAP_PROP_AUTO_EXPOSURE w OpenCV (DSHOW/V4L2)


def fuse(frames, align=True):
    """Fuzja Mertensa listy klatek BGR uint8 -> obraz uint8."""
    frames = [f.copy() for f in frames]
    if align:
        cv2.createAlignMTB().process(frames, frames)
    merged = cv2.createMergeMertens().process(frames)
    return np.clip(merged * 255, 0, 255).astype(np.uint8)


class HdrApp(App):
    TITLE = "Lab 7 - Kamera USB - HDR"

    def build_extra(self, panel):
        self.series = []
        box = ttk.LabelFrame(panel, text="HDR (fuzja ekspozycji)")
        box.pack(fill="x", pady=3)
        ttk.Label(box, text="Ekspozycje (log2 s, po przecinku):").pack(anchor="w", padx=4)
        self.exp_var = tk.StringVar(value="-9,-7,-5,-3")
        ttk.Entry(box, textvariable=self.exp_var).pack(fill="x", padx=4, pady=2)
        ttk.Button(box, text="Seria automatyczna", command=self.auto_series).pack(fill="x", padx=4, pady=2)
        row = ttk.Frame(box)
        row.pack(fill="x")
        ttk.Button(row, text="Dodaj klatke", command=self.add_frame).pack(side="left", expand=True, fill="x", padx=2)
        ttk.Button(row, text="Wyczysc", command=self.clear).pack(side="left", expand=True, fill="x", padx=2)
        self.align_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(box, text="Wyrownaj klatki (AlignMTB)", variable=self.align_var).pack(anchor="w", padx=4)
        ttk.Button(box, text="Zloz i zapisz HDR", command=self.make).pack(fill="x", padx=4, pady=2)
        self.hdr_lbl = ttk.Label(box, text="Klatek w serii: 0", foreground="gray")
        self.hdr_lbl.pack(anchor="w", padx=4)

    def update_label(self):
        means = ", ".join(f"{f.mean():.0f}" for f in self.series)
        self.hdr_lbl.config(text=f"Klatek w serii: {len(self.series)}" + (f"\nsr. jasnosc: {means}" if means else ""),
                            foreground="green" if len(self.series) >= 2 else "gray")

    def add_frame(self):
        if self.raw is None:
            messagebox.showwarning("HDR", "Brak obrazu z kamery.")
            return
        self.series.append(self.raw.copy())  # surowa klatka - bez programowej jasnosci/kontrastu
        self.update_label()

    def clear(self):
        self.series = []
        self.update_label()

    def auto_series(self):
        if not self.cap:
            messagebox.showwarning("HDR", "Polacz kamere.")
            return
        try:
            exposures = [float(x) for x in self.exp_var.get().split(",")]
        except ValueError:
            messagebox.showerror("HDR", "Ekspozycje: liczby oddzielone przecinkami, np. -9,-7,-5,-3")
            return
        with self.cap_lock:
            old_exp = self.cap.get(cv2.CAP_PROP_EXPOSURE)
            self.cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, AUTO_EXP_MANUAL)
            self.series = []
            for e in exposures:
                self.status.config(text=f"Ekspozycja {e}...")
                self.root.update_idletasks()
                self.cap.set(cv2.CAP_PROP_EXPOSURE, e)
                frame = None
                for _ in range(DROP_FRAMES):
                    ok, f = self.cap.read()
                    if ok:
                        frame = f
                if frame is not None:
                    self.series.append(frame)
            self.cap.set(cv2.CAP_PROP_EXPOSURE, old_exp)
            self.cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, AUTO_EXP_AUTO)
        self.update_label()
        means = [f.mean() for f in self.series]
        if len(means) < 2 or max(means) - min(means) < 15:
            messagebox.showwarning("HDR", "Klatki maja prawie te sama jasnosc - kamera prawdopodobnie ignoruje "
                                          "CAP_PROP_EXPOSURE.\nUzyj serii recznej: zmieniaj ekspozycje w "
                                          "ustawieniach sterownika i klikaj 'Dodaj klatke'.")
        else:
            self.status.config(text=f"Seria gotowa: {len(self.series)} klatek")

    def make(self):
        if len(self.series) < 2:
            messagebox.showwarning("HDR", "Potrzeba co najmniej 2 klatek o roznej ekspozycji.")
            return
        if len({f.shape for f in self.series}) > 1:
            messagebox.showerror("HDR", "Klatki maja rozne rozdzielczosci - wyczysc serie.")
            return
        for i, f in enumerate(self.series):
            save_image(f, f"hdr_ekspozycja{i}", "png")
        out = fuse(self.series, self.align_var.get())
        path = save_image(out, "hdr", "png")
        self.status.config(text=f"Zapisano: {os.path.basename(path)}")
        show_image_window(self.root, out, "HDR - wynik fuzji")


def self_test():
    # scena z gradientem: ciemna klatka ma detale w jasnej czesci, jasna w ciemnej
    scene = np.tile(np.linspace(0, 1, 160, dtype=np.float32), (120, 1))
    scene = cv2.merge([scene, scene, scene])
    frames = [np.clip(scene * k * 255, 0, 255).astype(np.uint8) for k in (0.5, 1.0, 3.0)]
    out = fuse(frames)
    assert out.shape == frames[0].shape and out.dtype == np.uint8, "ksztalt/typ wyniku"
    assert frames[0].mean() < out.mean() < frames[2].mean(), "wynik miedzy skrajnymi ekspozycjami"
    assert (out[:, -1] < 250).all() or (out[:, 0] > frames[0][:, 0]).all(), "fuzja nie jest kopia klatki"
    print("OK - testy przeszly")


if __name__ == "__main__":
    run(HdrApp, self_test)
