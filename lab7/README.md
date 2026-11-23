# Lab 7 – Kamery cyfrowe (wariant: kamera USB, Windows)

Python + tkinter + OpenCV. `kamera.py` = zad. 1 i wspólna baza (Windows/macOS). `macos/` = wersja na MacBooka; `macos/ruch/` = wersja z wykrywaniem ruchu (ocena wyższa). Raport i sprawozdanie: `raport/`.

| Program | Zadanie | Windows | macOS |
|---|---|---|---|
| `kamera.py` | zad. 1 | `kamera.bat` | `./run.sh` |

- Pierwsze uruchomienie tworzy `.venv` w `lab7/` i instaluje OpenCV.
- `build_exe.bat` → `dist\kamera.exe`.
- Testy bez kamery: dopisz `--test` (np. `./macos/ruch/start.sh --test`).
- Wszystkie pliki trafiają do `lab7/nagrania/`.

## macOS (MacBook) – folder `macos/`
| Program | Uruchomienie |
|---|---|
| `macos/kamera_mac.py` – zad. 1 | `./macos/start.sh` |
| `macos/ruch/ruch_mac.py` – zad. 1 + wykrywanie ruchu (ocena dodatkowa) | `./macos/ruch/start.sh` |

- Wymaga Pythona z Tk: `brew install python-tk@3.15`. `start.sh` sam instaluje OpenCV i PyObjC (AVFoundation).
- Pierwsze uruchomienie: zezwól Terminalowi na kamerę (Ustawienia systemowe → Prywatność i ochrona → Kamera).
- **Wybór kamery** – lista z nazwami z AVFoundation (np. `Microsoft® LifeCam HD-3000`, `USB2.0 Camera`, `MacBook Air Camera`, iPhone jako Continuity Camera). Kolejność ta sama co indeksy OpenCV (sortowanie po `uniqueID`).
- **Jakość kamery** – lista prawdziwych formatów danej kamery (np. LifeCam 160x120 … 1280x800, MacBook 640x480 … 1920x1080). Program ustawia `AVCaptureDevice.activeFormat`. Samo OpenCV na macOS nie zmienia formatu sensora.
- **Nasycenie**, jasność, kontrast, gamma – suwaki; **jakość JPEG** (10–100 %) – suwak w „Zapis”.
- Testy bez kamery: `./macos/start.sh --test`, `./macos/ruch/start.sh --test`.
- Kamery USB przez przejściówkę USB-C działają. Kamera Megapixel zgłasza się jako `USB2.0 Camera`.

## Zad. 1 (wspólne dla wszystkich programów)
- **Wykryj kamery** – sprawdza indeksy 0–5 (DirectShow na Windows), lista z rozdzielczością.
- **Połącz / Rozłącz** wybraną kamerę.
- Rozdzielczość: 640x480 … 1920x1080. Windows: **Ustawienia sterownika kamery** otwiera systemowe okno właściwości (ekspozycja, balans bieli, ostrość).
- Parametry programowe: jasność, kontrast, nasycenie, gamma, skala szarości, lustro. Działają na podglądzie, zdjęciach i filmach.
- **Zrób zdjęcie** – `jpg`/`png`/`bmp`; **Start/Stop nagrywania** – `mp4` (mp4v) / `avi` (MJPG).

## Wykrywanie ruchu (`macos/ruch/`, ocena wyższa)
Model tła (ruchoma średnia `accumulateWeighted`) → różnica z bieżącą klatką → progowanie → kontury. Obiekty większe niż „min. pole” obrysowane na czerwono (tylko na podglądzie). **Auto-zdjęcie przy ruchu** zapisuje `ruch_*.jpg` najwyżej co 2 s. **Zapamiętaj tło od nowa** po zmianie sceny.
