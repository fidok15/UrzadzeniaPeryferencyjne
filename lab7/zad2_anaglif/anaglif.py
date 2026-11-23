"""Lab 7, zad. 2 - anaglify (okulary czerwono-cyjanowe).

Jedna kamera, dwa zdjecia: lewe, potem kamera przesunieta ok. 6 cm w prawo -> prawe.
Anaglif: kanal R z lewego obrazu, kanaly G i B z prawego.
Suwak "przesuniecie" wyrownuje obrazy w poziomie (ustawia glebie / plaszczyzne ekranu).
"""
import os
import sys
import tkinter as tk
from tkinter import messagebox, ttk

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cv2  # noqa: E402
import numpy as np  # noqa: E402

from kamera import App, run, save_image, show_image_window  # noqa: E402


def anaglyph(left, right, shift=0, gray=False):
    """Czerwono-cyjanowy anaglif z pary BGR. shift>0 przesuwa prawy obraz w prawo (przycina krawedzie)."""
    if left.shape != right.shape:
        right = cv2.resize(right, (left.shape[1], left.shape[0]))
    if shift > 0:
        left, right = left[:, shift:], right[:, :-shift]
    elif shift < 0:
        left, right = left[:, :shift], right[:, -shift:]
    if gray:
        lg = cv2.cvtColor(left, cv2.COLOR_BGR2GRAY)
        rg = cv2.cvtColor(right, cv2.COLOR_BGR2GRAY)
        return cv2.merge([rg, rg, lg])  # B, G z prawego, R z lewego
    out = right.copy()
    out[..., 2] = left[..., 2]
    return out


class AnaglyphApp(App):
    TITLE = "Lab 7 - Kamera USB - anaglify"

    def build_extra(self, panel):
        self.left = self.right = None
        box = ttk.LabelFrame(panel, text="Anaglif (czerwony-cyjan)")
        box.pack(fill="x", pady=3)
        row = ttk.Frame(box)
        row.pack(fill="x")
        ttk.Button(row, text="1. Lewe oko", command=lambda: self.grab("left")).pack(side="left", expand=True,
                                                                                    fill="x", padx=2, pady=2)
        ttk.Button(row, text="2. Prawe oko", command=lambda: self.grab("right")).pack(side="left", expand=True,
                                                                                      fill="x", padx=2)
        ttk.Label(box, text="Po lewym zdjeciu przesun kamere ok. 6 cm w prawo.", wraplength=230).pack(anchor="w",
                                                                                                    padx=4)
        ttk.Label(box, text="Przesuniecie poziome [px]").pack(anchor="w", padx=4)
        self.shift_var = tk.IntVar(value=0)
        tk.Scale(box, variable=self.shift_var, from_=-150, to=150, orient="horizontal",
                 length=220).pack(fill="x", padx=4)
        self.gray_ana = tk.BooleanVar()
        ttk.Checkbutton(box, text="Anaglif szary (mniej duchow)", variable=self.gray_ana).pack(anchor="w", padx=4)
        self.live_var = tk.BooleanVar()
        ttk.Checkbutton(box, text="Podglad: lewe zdjecie + kamera na zywo", variable=self.live_var).pack(anchor="w",
                                                                                                    padx=4)
        ttk.Button(box, text="3. Zloz i zapisz anaglif", command=self.make).pack(fill="x", padx=4, pady=2)
        self.ana_lbl = ttk.Label(box, text="Lewe: -  Prawe: -", foreground="gray")
        self.ana_lbl.pack(anchor="w", padx=4)

    def grab(self, side):
        if self.frame is None:
            messagebox.showwarning("Anaglif", "Brak obrazu z kamery.")
            return
        setattr(self, side, self.frame.copy())
        save_image(self.frame, f"anaglif_{side}", "png")
        self.ana_lbl.config(text=f"Lewe: {'OK' if self.left is not None else '-'}  "
                                 f"Prawe: {'OK' if self.right is not None else '-'}", foreground="green")

    def make(self):
        if self.left is None or self.right is None:
            messagebox.showwarning("Anaglif", "Zrob najpierw lewe i prawe zdjecie.")
            return
        out = anaglyph(self.left, self.right, self.shift_var.get(), self.gray_ana.get())
        path = save_image(out, "anaglif", "png")
        self.status.config(text=f"Zapisano: {os.path.basename(path)}")
        show_image_window(self.root, out, "Anaglif - zaloz okulary czerwono-cyjanowe")

    def overlay(self, view):
        # podglad na zywo ulatwia ustawienie prawego zdjecia
        if self.live_var.get() and self.left is not None:
            view[:] = cv2.resize(anaglyph(self.left, self.frame, self.shift_var.get(), self.gray_ana.get()),
                                 (view.shape[1], view.shape[0]))


def self_test():
    left = np.zeros((40, 60, 3), np.uint8)
    right = np.zeros((40, 60, 3), np.uint8)
    left[..., 2] = 200   # R lewego
    right[..., 0] = 50   # B prawego
    right[..., 1] = 100  # G prawego
    a = anaglyph(left, right)
    assert (a[..., 2] == 200).all() and (a[..., 0] == 50).all() and (a[..., 1] == 100).all(), "kanaly R/GB"
    assert anaglyph(left, right, shift=10).shape == (40, 50, 3), "przesuniecie przycina"
    assert anaglyph(left, right, shift=-10).shape == (40, 50, 3)
    g = anaglyph(left, right, gray=True)
    assert np.array_equal(g[..., 0], g[..., 1]) and g[..., 2].mean() > 0, "anaglif szary"
    print("OK - testy przeszly")


if __name__ == "__main__":
    run(AnaglyphApp, self_test)
