# Lab 1 – GPS / NMEA

Python + tkinter + pyserial. Ten sam `gps_app.py` w obu folderach, różnią się tylko skrypty uruchomienia i budowania.

## Windows (`windows/`)
1. Sparuj GPS przez Bluetooth → Ustawienia → Bluetooth → Więcej opcji Bluetooth → zakładka **Porty COM**: zapamiętaj port *Wychodzący*.
2. `run.bat` – instaluje pyserial i uruchamia program.
3. `build_exe.bat` – buduje `dist\GPS_NMEA.exe` (PyInstaller) do sprawozdania.

## macOS (`mac/`)
1. Potrzebny Python z Tk 8.6+: instalator z python.org albo `brew install python-tk@3.14` (systemowy `/usr/bin/python3` ma Tk 8.5 i się zawiesza).
2. Sparuj GPS w Ustawieniach systemowych → Bluetooth; port pojawi się jako `/dev/cu.<nazwa>` (używaj `cu`, nie `tty`).
3. `./run.sh` (inny interpreter: `PY=/sciezka/do/python3 ./run.sh`).
4. `./build_app.sh` – buduje `dist/GPS_NMEA.app`.

## Obsługa
- Port + baud (zwykle 4800 lub 9600) → **Polacz**. Bez urządzenia: **Wczytaj plik NMEA** → `sample.nmea` (celowo zawiera jedno zdanie z błędną sumą kontrolną).
- Lewy panel: rozkodowane RMC/GGA/GLL/ZDA/GSA/GSV. Prawy: liczba zdań wg typu + nieważne (`V` / fix 0) + błędne sumy kontrolne.
- **Mapa (OpenStreetMap)** – strona Leaflet z markerem i trasą, odświeża się co 5 s. **Google Maps** – otwiera bieżący punkt.
- **Zapisz log** – zapisuje surowe NMEA do sprawozdania.
- `python gps_app.py --test` – test parsera.

Pozycja brana tylko z ważnych danych: RMC/GLL status `A`, GGA jakość fixa > 0.
