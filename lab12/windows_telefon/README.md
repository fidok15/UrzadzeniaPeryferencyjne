# Windows → telefon (Android) – Bluetooth OBEX

Osobny program tylko na Windows. Python + tkinter, bez dodatkowych pakietów (Win32 Bluetooth API przez `ctypes`).

## Wymagania
- Windows 10/11 z adapterem Bluetooth (wbudowany albo USB), Bluetooth włączony.
- Python 3.9+ z python.org (instalator ma tkinter; zaznacz „Add python.exe to PATH”).
- Telefon z **Androidem**. iPhone nie obsługuje OBEX Object Push.

## Uruchomienie
- `run.bat` – uruchamia program.
- `run.bat --test` – test protokołu OBEX na symulowanym telefonie (bez Bluetooth).
- `build_exe.bat` – buduje `dist\BT_Telefon.exe` (PyInstaller) do sprawozdania.

## Obsługa (zad. 2)
a) Adapter otwiera się automatycznie na starcie (nazwa i adres u góry okna) i zamyka przy zamknięciu okna.
b) Na telefonie otwórz Ustawienia → Bluetooth → „Sparuj nowe urządzenie” (telefon jest wtedy widoczny). W programie kliknij **Wyszukaj urządzenia** (ok. 10 s).
c) Wybierz telefon → **Sparuj** → potwierdź ten sam kod w oknie Windows i na telefonie.
d) **Wybierz plik** (`.txt`, `.jpg`, `.jpeg`, `.png`, max 1 MB) → **Wyślij plik** → zaakceptuj na telefonie. Plik trafia do `Download`/`Bluetooth` na telefonie.

„Połączony: Nie” po sparowaniu jest normalne – połączenie otwiera się dopiero na czas wysyłania.

## Zad. 1 – przykładowy program
Ustawienia → Bluetooth i urządzenia, albo `fsquirt.exe` (Kreator transferu plików Bluetooth) → Wyślij pliki.

## Dodatki
- Panel informacji o urządzeniu: nazwa, adres MAC, klasa (telefon/komputer/audio…), sparowany, połączony.
- Limit 1 MB i sprawdzenie formatu pliku, z komunikatem błędu.
- Pasek postępu, czas i prędkość transmisji, log zdarzeń.
- Czytelne kody odpowiedzi OBEX, np. `0xC3 Forbidden` = odrzucono na telefonie.

## Typowe błędy
- „Brak adaptera Bluetooth” – włącz Bluetooth w Ustawieniach / podłącz adapter USB.
- „Brak połączenia z usługą OBEX Object Push (WSA 10060/10064)” – telefon zablokowany, poza zasięgiem albo nie przyjmuje plików; odblokuj go i spróbuj ponownie.
- `0xC3 Forbidden` – plik odrzucony na telefonie albo powiadomienie wygasło.
