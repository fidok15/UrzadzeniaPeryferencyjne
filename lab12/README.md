# Lab 12 – Transmisja Bluetooth (OBEX)

Dwa niezależne programy (Python + tkinter). Protokół OBEX (CONNECT → PUT/Body… → PUT-final/End-of-Body → DISCONNECT) jest zaimplementowany ręcznie, bez bibliotek.

| Program | Kierunek | System | Uruchomienie |
|---|---|---|---|
| `bt_telefon.py` | komputer → telefon z Androidem (OBEX Object Push) | macOS, Windows | Mac: `./run.sh`, Windows: `telefon.bat` |
| `bt_windows.py` | Windows ↔ Windows (wysyłanie + odbiór) | Windows | `windows.bat` na obu komputerach |

- Windows: Win32 Bluetooth API (`bthprops.cpl`, `ws2_32`) przez `ctypes` + gniazdo RFCOMM. Wystarczy Python 3.9+ z python.org, bez dodatkowych pakietów.
- macOS: IOBluetooth przez PyObjC (`run.sh` sam instaluje `requirements.txt`). Potrzebny Python z Tk: `brew install python-tk@3.15`. Przy pierwszym uruchomieniu zezwól Terminalowi na Bluetooth (Ustawienia → Prywatność i ochrona → Bluetooth).
- `python bt_telefon.py --test` / `python bt_windows.py --test` – testy OBEX bez Bluetooth.

**iPhone nie obsługuje OBEX Object Push**, więc nie przyjmie pliku. Wyszukiwanie i parowanie z iPhonem działa.

## bt_telefon.py – komputer → Android (zad. 2)
a) Adapter otwiera się automatycznie na starcie (nazwa i adres u góry okna) i zamyka przy zamknięciu okna.
b) **Wyszukaj urządzenia** – inquiry ok. 10 s (+ urządzenia już sparowane).
c) Wybierz telefon z listy → **Sparuj** → potwierdź kod na telefonie (na Windows także w oknie systemowym).
d) **Wybierz plik** (`.txt`, `.jpg`, `.jpeg`, `.png`, max 1 MB) → **Wyślij plik** → zaakceptuj na telefonie.

Na Androidzie włącz Bluetooth i zostaw otwarty ekran Bluetooth (widoczność).

## bt_windows.py – Windows ↔ Windows
1. Na obu komputerach włącz Bluetooth i uruchom `windows.bat`.
2. Odbiorca: **Odbieraj pliki**. Program rejestruje własną usługę SDP (`APP_UUID`) na kanale RFCOMM i staje się widoczny.
3. Nadawca: **Wyszukaj urządzenia** → wybierz komputer odbiorcy → **Sparuj** → potwierdź ten sam kod na obu komputerach.
4. Nadawca: **Wybierz plik** → **Wyślij plik**.
5. Odbiorca: w logu „Odebrano …”, plik w `Pobrane\bluetooth`.

Odbiornik: bezpieczna nazwa pliku (bez `../`), bez nadpisywania (`foto(1).jpg`), odrzuca pliki > 1 MB kodem OBEX `0xCD`.

## Zad. 1 – przykładowy program
- macOS: *Narzędzia → Bluetooth File Exchange* albo Ustawienia → Bluetooth.
- Windows: Ustawienia → Bluetooth, albo `fsquirt.exe` (Kreator transferu plików Bluetooth).

## Dodatki (wzorowane na sprawozdaniu innej grupy i rozszerzone)
- Panel informacji o urządzeniu: nazwa, adres MAC, klasa (telefon/komputer/audio…), sparowany, połączony.
- Limit rozmiaru 1 MB i sprawdzenie formatu pliku, z komunikatem błędu.
- Pasek postępu, czas i prędkość transmisji, log zdarzeń.
- Czytelne kody odpowiedzi OBEX, np. `0xC3 Forbidden` = odrzucono na telefonie.
