# Lab 7 – Kamery cyfrowe (wariant: kamera USB, Windows)

Python + tkinter + OpenCV. Wersja Windows: `kamera.py` + `zad2_*/`; wersja macOS: `macos/`. `kamera.py` = zad. 1 i wspólna baza; każdy wariant zad. 2 w osobnym folderze dziedziczy po `App` z `kamera.py` i dokłada swój panel.

| Program | Zadanie | Windows | macOS |
|---|---|---|---|
| `kamera.py` | zad. 1 | `kamera.bat` | `./run.sh` |
| `zad2_ruch/ruch.py` | wykrywanie ruchu | `zad2_ruch\start.bat` | `./run.sh zad2_ruch/ruch.py` |
| `zad2_www/www.py` | strona WWW z odświeżaniem | `zad2_www\start.bat` | `./run.sh zad2_www/www.py` |
| `zad2_anaglif/anaglif.py` | anaglify | `zad2_anaglif\start.bat` | `./run.sh zad2_anaglif/anaglif.py` |
| `zad2_hdr/hdr.py` | fotografia HDR | `zad2_hdr\start.bat` | `./run.sh zad2_hdr/hdr.py` |

- Pierwsze uruchomienie tworzy `.venv` w `lab7/` i instaluje OpenCV.
- `build_exe.bat` → `dist\kamera.exe`, `ruch.exe`, `www.exe`, `anaglif.exe`, `hdr.exe`.
- Testy bez kamery: dopisz `--test` (np. `python zad2_hdr/hdr.py --test`).
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

## Zad. 2 – warianty
### Wykrywanie ruchu (`zad2_ruch`)
Model tła (ruchoma średnia `accumulateWeighted`) → różnica z bieżącą klatką → progowanie → kontury. Obiekty większe niż „min. pole” obrysowane na czerwono. **Auto-zdjęcie przy ruchu** zapisuje `ruch_*.jpg` najwyżej co 2 s. **Zapamiętaj tło od nowa** po zmianie sceny.

### Strona WWW z odświeżaniem (`zad2_www`)
Wbudowany serwer `http.server`: `/` – strona HTML przeładowująca obraz co N ms (JavaScript; bez JS `meta refresh`), `/frame.jpg` – ostatnia klatka. Domyślnie tylko `127.0.0.1`. **Dostęp z sieci LAN** udostępnia podgląd innym urządzeniom w sieci (np. telefonowi) – adres pokazuje się w oknie. Kamera jest wtedy widoczna dla każdego w tej sieci, bez hasła.

### Anaglify (`zad2_anaglif`)
1. **Lewe oko** – zdjęcie. 2. Przesuń kamerę ok. 6 cm w prawo → **Prawe oko**. 3. **Złóż i zapisz** – kanał R z lewego, G+B z prawego (okulary czerwono-cyjanowe). Suwak przesunięcia wyrównuje obrazy w poziomie. Opcja anaglifu szarego (mniej „duchów”) i podgląd na żywo (lewe zdjęcie + kamera) do ustawienia drugiego ujęcia. Nie włączaj lustra między zdjęciami.

### HDR (`zad2_hdr`)
Seria klatek o różnej ekspozycji → wyrównanie `AlignMTB` → fuzja Mertensa (`createMergeMertens`, bez znajomości czasów naświetlania) → `hdr_*.png` + zapis klatek serii.
- **Seria automatyczna** ustawia `CAP_PROP_EXPOSURE` (DirectShow: log2 sekund, np. `-9,-7,-5,-3`).
- Jeśli kamera ignoruje ekspozycję (program to wykrywa i ostrzega): zmieniaj ekspozycję w **Ustawieniach sterownika kamery** i klikaj **Dodaj klatkę**.
