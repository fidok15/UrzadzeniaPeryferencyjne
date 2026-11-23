"""Lab 7 - wersja na macOS (MacBook): zad. 1.

Wszystko z kamera.py, plus:
- lista kamer z nazwami (AVFoundation), np. "MacBook Air Camera", "iPhone (Continuity Camera)",
- jakosc kamery = prawdziwe formaty sensora (np. 640x480 ... 1920x1080 @ 30/60 fps),
  ustawiane przez AVCaptureDevice.activeFormat (OpenCV na macOS sam tego nie potrafi),
- prosba o dostep do kamery (Ustawienia -> Prywatnosc i ochrona -> Kamera).
Nasycenie, jasnosc, kontrast, gamma - suwaki z kamera.py; jakosc JPEG - suwak w "Zapis".

Uruchomienie: ./start.sh   |  testy: ./start.sh --test
"""
import os
import sys
import time
from tkinter import messagebox

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cv2  # noqa: E402

from kamera import App, run, self_test as base_test  # noqa: E402

AUTHORIZED, DENIED_STATES = 3, (1, 2)  # AVAuthorizationStatus: 0 nieustalony, 1 ograniczony, 2 odmowa


def av_devices():
    """Kamery w tej samej kolejnosci co indeksy OpenCV (OpenCV sortuje po uniqueID)."""
    import AVFoundation as AVF

    devs = list(AVF.AVCaptureDevice.devicesWithMediaType_(AVF.AVMediaTypeVideo)) + \
        list(AVF.AVCaptureDevice.devicesWithMediaType_(AVF.AVMediaTypeMuxed))
    return sorted(devs, key=lambda d: d.uniqueID())


def device_formats(device):
    """[(szer, wys, max_fps, AVCaptureDeviceFormat)] dla kamery."""
    import CoreMedia as CM

    out = []
    for f in device.formats():
        dim = CM.CMVideoFormatDescriptionGetDimensions(f.formatDescription())
        fps = max((r.maxFrameRate() for r in f.videoSupportedFrameRateRanges()), default=0)
        out.append((dim.width, dim.height, round(fps), f))
    return out


def pick_format(formats, w, h):
    """Format o danym rozmiarze z najwiekszym fps albo None."""
    match = [f for f in formats if f[0] == w and f[1] == h]
    return max(match, key=lambda f: f[2]) if match else None


def resolution_labels(formats):
    """Unikalne poziome rozmiary od najmniejszego, np. ['640x480', '1280x720'].
    Formaty pionowe (Center Stage w MacBookach) pomijamy - OpenCV nie ustawia ich poprawnie."""
    sizes = {(f[0], f[1]) for f in formats if f[0] >= f[1]}
    return [f"{w}x{h}" for w, h in sorted(sizes, key=lambda s: s[0] * s[1])]


def ensure_camera_access(root):
    """Pyta system o dostep do kamery. Zwraca True, gdy dostep jest."""
    import AVFoundation as AVF

    status = AVF.AVCaptureDevice.authorizationStatusForMediaType_(AVF.AVMediaTypeVideo)
    if status == 0:
        AVF.AVCaptureDevice.requestAccessForMediaType_completionHandler_(AVF.AVMediaTypeVideo, lambda ok: None)
        deadline = time.time() + 60
        while status == 0 and time.time() < deadline:
            root.update()
            time.sleep(0.1)
            status = AVF.AVCaptureDevice.authorizationStatusForMediaType_(AVF.AVMediaTypeVideo)
    if status != AUTHORIZED:
        messagebox.showerror("Kamera", "Brak dostepu do kamery.\nUstawienia systemowe -> Prywatnosc i ochrona -> "
                                       "Kamera -> wlacz dla Terminala, potem uruchom program ponownie.")
        return False
    return True


class MacApp(App):
    TITLE = "Lab 7 - Kamera (macOS)"

    def detect_cameras(self):
        if self.cap:
            messagebox.showinfo("Kamera", "Najpierw rozlacz kamere.")
            return
        self.devices = []
        if ensure_camera_access(self.root):
            self.devices = av_devices()
        self.cameras = [(i, d.localizedName()) for i, d in enumerate(self.devices)]
        names = [f"{i}: {name}" for i, name in self.cameras]
        self.cam_combo.config(values=names)
        if names:
            self.cam_combo.current(0)
        self.status.config(text=f"Znaleziono kamer: {len(names)}")

    def toggle_connect(self):
        if not self.cap and self.cameras and self.cam_combo.current() >= 0:
            self.device = self.devices[self.cam_combo.current()]
            self.formats = device_formats(self.device)
            labels = resolution_labels(self.formats)
            self.res_combo.config(values=labels)
            if self.res_var.get() not in labels:
                self.res_var.set("1280x720" if "1280x720" in labels else labels[-1])
        super().toggle_connect()
        if self.cap:
            self.status.config(text=f"Polaczono: {self.device.localizedName()}")

    def apply_resolution(self):
        if not self.cap or self.writer:
            return super().apply_resolution()
        w, h = map(int, self.res_var.get().split("x"))
        fmt = pick_format(self.formats, w, h)
        with self.cap_lock:
            if fmt:
                ok, _ = self.device.lockForConfiguration_(None)
                if ok:
                    self.device.setActiveFormat_(fmt[3])  # sesja przechodzi na preset InputPriority
                    self.device.unlockForConfiguration()
                else:
                    self.status.config(text="Kamera zajeta - nie mozna zmienic formatu")
            # OpenCV dopasowuje bufor wyjsciowy do aktywnego formatu urzadzenia
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)


def self_test():
    base_test()
    fake = [(640, 480, 30, "a"), (1280, 720, 30, "b"), (1280, 720, 60, "c"), (1080, 1920, 30, "d")]
    assert pick_format(fake, 1280, 720)[3] == "c", "wybiera najwiekszy fps"
    assert pick_format(fake, 800, 600) is None
    assert resolution_labels(fake) == ["640x480", "1280x720"], resolution_labels(fake)
    print("OK - testy macOS przeszly")


if __name__ == "__main__":
    run(MacApp, self_test)
