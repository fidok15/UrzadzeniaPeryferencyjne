"""Lab 7, zad. 2 - wykrywanie ruchu.

Model tla (ruchoma srednia) -> roznica z biezaca klatka -> progowanie -> kontury.
Obiekty wieksze niz "min. pole" obrysowane na czerwono; opcjonalne auto-zdjecie.
"""
import os
import sys
import time
import tkinter as tk
from tkinter import ttk

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cv2  # noqa: E402
import numpy as np  # noqa: E402

from kamera import App, run  # noqa: E402


class MotionDetector:
    def __init__(self, min_area=800, threshold=25, learn_rate=0.05):
        self.min_area, self.threshold, self.learn_rate = min_area, threshold, learn_rate
        self.background = None

    def reset(self):
        self.background = None

    def detect(self, frame):
        gray = cv2.GaussianBlur(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), (21, 21), 0)
        if self.background is None or self.background.shape != gray.shape:
            self.background = gray.astype(np.float32)
            return []
        diff = cv2.absdiff(gray, cv2.convertScaleAbs(self.background))
        cv2.accumulateWeighted(gray, self.background, self.learn_rate)
        mask = cv2.dilate(cv2.threshold(diff, self.threshold, 255, cv2.THRESH_BINARY)[1], None, iterations=2)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        return [cv2.boundingRect(c) for c in contours if cv2.contourArea(c) >= self.min_area]


class MotionApp(App):
    TITLE = "Lab 7 - Kamera USB - wykrywanie ruchu"

    def build_extra(self, panel):
        self.detector = MotionDetector()
        self.last_auto = 0.0
        box = ttk.LabelFrame(panel, text="Wykrywanie ruchu")
        box.pack(fill="x", pady=3)
        self.motion_var, self.auto_var = tk.BooleanVar(value=True), tk.BooleanVar()
        ttk.Checkbutton(box, text="Wlacz wykrywanie ruchu", variable=self.motion_var,
                        command=self.detector.reset).pack(anchor="w", padx=4)
        ttk.Checkbutton(box, text="Auto-zdjecie przy ruchu (co 2 s)", variable=self.auto_var).pack(anchor="w", padx=4)
        ttk.Label(box, text="Min. pole obiektu [px] (czulosc)").pack(anchor="w", padx=4)
        self.area_var = tk.IntVar(value=self.detector.min_area)
        tk.Scale(box, variable=self.area_var, from_=100, to=20000, resolution=100,
                 orient="horizontal", length=220).pack(fill="x", padx=4)
        ttk.Button(box, text="Zapamietaj tlo od nowa", command=self.detector.reset).pack(fill="x", padx=4, pady=2)
        self.motion_lbl = tk.Label(box, text="Ruch: -", fg="gray")
        self.motion_lbl.pack(anchor="w", padx=4)

    def overlay(self, view):
        if not self.motion_var.get():
            self.motion_lbl.config(text="Ruch: -", fg="gray")
            return
        self.detector.min_area = self.area_var.get()
        boxes = self.detector.detect(self.frame)
        for x, y, w, h in boxes:
            cv2.rectangle(view, (x, y), (x + w, y + h), (0, 0, 255), 2)
        self.motion_lbl.config(text=f"Ruch: TAK ({len(boxes)})" if boxes else "Ruch: nie",
                               fg="red" if boxes else "green")
        if boxes and self.auto_var.get() and time.time() - self.last_auto > 2:
            self.last_auto = time.time()
            self.take_photo("ruch")


def self_test():
    d = MotionDetector(min_area=200)
    still = np.full((240, 320, 3), 100, np.uint8)
    for _ in range(5):
        assert d.detect(still) == [], "brak ruchu na statycznym obrazie"
    moved = still.copy()
    moved[100:160, 140:200] = 255
    boxes = d.detect(moved)
    assert len(boxes) == 1 and boxes[0][2] >= 60, f"ruch nie wykryty: {boxes}"
    print("OK - testy przeszly")


if __name__ == "__main__":
    run(MotionApp, self_test)
