"""Lab 7 - macOS, ocena dodatkowa: wykrywanie ruchu.

Wersja macOS (wybor kamery, jakosc, nasycenie) + panel wykrywania ruchu z zad2_ruch/ruch.py.
Uruchomienie: ./start.sh   |  testy: ./start.sh --test
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.dirname(HERE), os.path.dirname(os.path.dirname(HERE))]  # lab7/macos, lab7

from kamera import run  # noqa: E402
from kamera_mac import MacApp, self_test as mac_test  # noqa: E402
from zad2_ruch.ruch import MotionApp, self_test as motion_test  # noqa: E402


class MacMotionApp(MacApp, MotionApp):
    TITLE = "Lab 7 - Kamera (macOS) - wykrywanie ruchu"


def self_test():
    mac_test()
    motion_test()


if __name__ == "__main__":
    run(MacMotionApp, self_test)
