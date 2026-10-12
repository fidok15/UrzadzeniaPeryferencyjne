"""
GPS NMEA - Cwiczenie 1, Urzadzenia Peryferyjne.

Czyta zdania NMEA 0183 z portu szeregowego (odbiornik GPS przez Bluetooth SPP)
albo z pliku, rozkodowuje RMC/GGA/GLL/ZDA/GSA/GSV i pokazuje pozycje na mapie.

    python gps_app.py          # GUI
    python gps_app.py --test   # test parsera
"""
import queue
import sys
import tempfile
import threading
import time
import webbrowser
from collections import Counter
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

try:
    import serial
    from serial.tools import list_ports
except ImportError:  # bez pyserial dziala tylko tryb pliku
    serial = None


# ---------------------------------------------------------------- NMEA

FIX_QUALITY = {'0': '0 - brak', '1': '1 - GPS', '2': '2 - DGPS', '4': '4 - RTK',
               '5': '5 - RTK float', '6': '6 - estymacja'}
FIX_TYPE = {'1': '1 - brak', '2': '2 - 2D', '3': '3 - 3D'}
STATUS = {'A': 'A - dane wazne', 'V': 'V - dane niewazne'}


def checksum_ok(line):
    """XOR wszystkich znakow miedzy '$' a '*' == liczba hex po '*'."""
    if not line.startswith('$') or '*' not in line:
        return False
    body, cs = line[1:].split('*', 1)
    calc = 0
    for ch in body:
        calc ^= ord(ch)
    try:
        return calc == int(cs[:2], 16)
    except ValueError:
        return False


def to_deg(value, hemi):
    """ddmm.mmmm / dddmm.mmmm -> stopnie dziesietne (S i W ujemne)."""
    if not value:
        return None
    dot = value.find('.')
    if dot < 0:
        dot = len(value)
    deg = int(value[:dot - 2]) + float(value[dot - 2:]) / 60
    return -deg if hemi in ('S', 'W') else deg


def num(s):
    try:
        return float(s)
    except ValueError:
        return None


def fmt_time(t):
    return '%s:%s:%s' % (t[0:2], t[2:4], t[4:6]) if len(t) >= 6 else None


def parse(line):
    """Zwraca (typ, pola) dla zdania z poprawna suma kontrolna, inaczej None.
    Pozycja (lat/lon) jest zwracana tylko gdy dane sa wazne."""
    line = line.strip()
    if not checksum_ok(line):
        return None
    f = line[1:line.index('*')].split(',')
    kind = f[0][2:]
    d = {}
    try:
        if kind == 'RMC':
            d['time'] = fmt_time(f[1])
            d['status'] = STATUS.get(f[2], f[2])
            d['valid'] = f[2] == 'A'
            if d['valid']:
                d['lat'], d['lon'] = to_deg(f[3], f[4]), to_deg(f[5], f[6])
            kn = num(f[7])
            d['speed'] = kn * 1.852 if kn is not None else None
            d['course'] = num(f[8])
            if len(f[9]) == 6:
                yy = int(f[9][4:6])
                d['date'] = '%s.%s.%d' % (f[9][0:2], f[9][2:4], yy + (2000 if yy < 80 else 1900))
        elif kind == 'GGA':
            d['time'] = fmt_time(f[1])
            d['quality'] = FIX_QUALITY.get(f[6], f[6])
            d['valid'] = f[6] not in ('', '0')
            if d['valid']:
                d['lat'], d['lon'] = to_deg(f[2], f[3]), to_deg(f[4], f[5])
                d['alt'] = num(f[9])
                d['geoid'] = num(f[11])
            d['sats'] = int(f[7]) if f[7] else None
            d['hdop'] = num(f[8])
        elif kind == 'GLL':
            d['time'] = fmt_time(f[5])
            d['status'] = STATUS.get(f[6], f[6])
            d['valid'] = f[6] == 'A'
            if d['valid']:
                d['lat'], d['lon'] = to_deg(f[1], f[2]), to_deg(f[3], f[4])
        elif kind == 'ZDA':
            d['time'] = fmt_time(f[1])
            d['date'] = '%s.%s.%s' % (f[2], f[3], f[4])
        elif kind == 'GSA':
            d['fix'] = FIX_TYPE.get(f[2], f[2])
            d['pdop'], d['hdop'], d['vdop'] = num(f[15]), num(f[16]), num(f[17])
        elif kind == 'GSV':
            d['in_view'] = int(f[3]) if f[3] else None
    except (IndexError, ValueError):
        pass  # niepelne zdanie - liczymy typ, pomijamy pola
    return kind, {k: v for k, v in d.items() if v is not None}


# ---------------------------------------------------------------- zrodla danych

def serial_reader(port, baud, q, stop):
    try:
        with serial.Serial(port, baud, timeout=1) as s:
            while not stop.is_set():
                raw = s.readline()
                if raw:
                    q.put(raw.decode('ascii', 'replace').strip())
    except Exception as e:  # zgubione polaczenie BT, zajety port itp.
        q.put(('ERR', str(e)))


def file_reader(path, q, stop, delay=0.1):
    with open(path, errors='replace') as fh:
        for line in fh:
            if stop.is_set():
                return
            if line.strip():
                q.put(line.strip())
                time.sleep(delay)
    q.put(('ERR', 'Koniec pliku'))


# ---------------------------------------------------------------- mapa

MAP_FILE = Path(tempfile.gettempdir()) / 'gps_lab_map.html'

MAP_HTML = """<!doctype html><html><head><meta charset="utf-8">
<meta http-equiv="refresh" content="5"><title>GPS - pozycja</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>html,body,#m{height:100%%;margin:0}</style></head><body><div id="m"></div>
<script>
var p=[%f,%f], track=%s;
var m=L.map('m').setView(p,17);
L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',
  {maxZoom:19, attribution:'&copy; OpenStreetMap'}).addTo(m);
L.polyline(track,{color:'red'}).addTo(m);
L.marker(p).addTo(m).bindPopup(%r).openPopup();
</script></body></html>"""


def write_map(lat, lon, track, popup):
    pts = '[%s]' % ','.join('[%.7f,%.7f]' % t for t in track)
    MAP_FILE.write_text(MAP_HTML % (lat, lon, pts, popup), encoding='utf-8')


# ---------------------------------------------------------------- GUI

FIELDS = [('lat', 'Szerokosc'), ('lon', 'Dlugosc'), ('alt', 'Wysokosc n.p.m. [m]'),
          ('geoid', 'Separacja geoidy [m]'), ('time', 'Czas UTC'), ('date', 'Data'),
          ('status', 'Status (RMC/GLL)'), ('quality', 'Jakosc fixa (GGA)'),
          ('fix', 'Typ fixa (GSA)'), ('sats', 'Satelity uzyte'),
          ('in_view', 'Satelity widoczne'), ('hdop', 'HDOP'), ('pdop', 'PDOP'),
          ('vdop', 'VDOP'), ('speed', 'Predkosc [km/h]'), ('course', 'Kurs [deg]')]


def fmt(key, v):
    if key == 'lat':
        return '%.6f° %s' % (abs(v), 'N' if v >= 0 else 'S')
    if key == 'lon':
        return '%.6f° %s' % (abs(v), 'E' if v >= 0 else 'W')
    if isinstance(v, float):
        return '%.2f' % v
    return str(v)


class App:
    def __init__(self, root):
        self.root = root
        self.q = queue.Queue()
        self.stop = threading.Event()
        self.worker = None
        self.state = {}
        self.counts = Counter()
        self.track = []
        self.map_on = False
        self.map_written = 0
        root.title('GPS NMEA - Lab 1')
        root.geometry('980x640')

        top = ttk.Frame(root, padding=6)
        top.pack(fill='x')
        ttk.Label(top, text='Port:').pack(side='left')
        self.port = ttk.Combobox(top, width=28)
        self.port.pack(side='left', padx=4)
        ttk.Button(top, text='Odswiez', command=self.refresh_ports).pack(side='left')
        ttk.Label(top, text='Baud:').pack(side='left', padx=(10, 0))
        self.baud = ttk.Combobox(top, width=8, values=['4800', '9600', '19200', '38400', '57600', '115200'])
        self.baud.set('9600')
        self.baud.pack(side='left', padx=4)
        self.btn_conn = ttk.Button(top, text='Polacz', command=self.toggle)
        self.btn_conn.pack(side='left', padx=4)
        ttk.Button(top, text='Wczytaj plik NMEA', command=self.open_file).pack(side='left', padx=4)
        ttk.Button(top, text='Zapisz log', command=self.save_log).pack(side='right')

        mid = ttk.Frame(root, padding=6)
        mid.pack(fill='x')
        data = ttk.LabelFrame(mid, text='Dane rozkodowane', padding=6)
        data.pack(side='left', fill='y')
        self.vals = {}
        for i, (key, label) in enumerate(FIELDS):
            ttk.Label(data, text=label + ':').grid(row=i, column=0, sticky='w')
            self.vals[key] = ttk.Label(data, text='-', width=26, font=('TkFixedFont', 11, 'bold'))
            self.vals[key].grid(row=i, column=1, sticky='w', padx=6)
        btns = ttk.Frame(data)
        btns.grid(row=len(FIELDS), column=0, columnspan=2, pady=(8, 0))
        ttk.Button(btns, text='Mapa (OpenStreetMap)', command=self.open_map).pack(side='left')
        ttk.Button(btns, text='Google Maps', command=self.open_google).pack(side='left', padx=4)

        stats = ttk.LabelFrame(mid, text='Statystyka zdan', padding=6)
        stats.pack(side='left', fill='both', expand=True, padx=(6, 0))
        self.stats = ttk.Label(stats, text='', font=('TkFixedFont', 11), justify='left', anchor='nw')
        self.stats.pack(fill='both', expand=True)

        logf = ttk.LabelFrame(root, text='Surowe zdania NMEA (czerwone = bledna suma kontrolna)', padding=6)
        logf.pack(fill='both', expand=True, padx=6, pady=(0, 6))
        self.log = tk.Text(logf, height=12, font=('TkFixedFont', 10))
        sb = ttk.Scrollbar(logf, command=self.log.yview)
        self.log.configure(yscrollcommand=sb.set)
        sb.pack(side='right', fill='y')
        self.log.pack(fill='both', expand=True)
        self.log.tag_configure('bad', foreground='red')

        self.status = ttk.Label(root, text='Rozlaczono', relief='sunken', anchor='w')
        self.status.pack(fill='x', side='bottom')

        self.refresh_ports()
        root.protocol('WM_DELETE_WINDOW', self.close)
        root.after(100, self.poll)

    # --- polaczenie
    def refresh_ports(self):
        ports = [p.device for p in list_ports.comports()] if serial else []
        self.port['values'] = ports
        if ports and not self.port.get():
            self.port.set(ports[0])

    def start(self, target, args, msg):
        self.disconnect()
        self.stop = threading.Event()
        self.worker = threading.Thread(target=target, args=args + (self.q, self.stop), daemon=True)
        self.worker.start()
        self.btn_conn.configure(text='Rozlacz')
        self.status.configure(text=msg)

    def toggle(self):
        if self.worker and self.worker.is_alive():
            self.disconnect()
            return
        if not serial:
            messagebox.showerror('Brak pyserial', 'Zainstaluj: pip install pyserial')
            return
        port = self.port.get()
        if not port:
            messagebox.showwarning('Port', 'Wybierz port (sparuj GPS przez Bluetooth).')
            return
        self.start(serial_reader, (port, int(self.baud.get())), 'Polaczono: %s @ %s' % (port, self.baud.get()))

    def open_file(self):
        path = filedialog.askopenfilename(filetypes=[('NMEA', '*.nmea *.txt *.log'), ('Wszystkie', '*')])
        if path:
            self.start(file_reader, (path,), 'Odtwarzanie pliku: %s' % path)

    def disconnect(self):
        self.stop.set()
        self.btn_conn.configure(text='Polacz')
        self.status.configure(text='Rozlaczono')

    # --- przetwarzanie
    def poll(self):
        try:
            while True:
                item = self.q.get_nowait()
                if isinstance(item, tuple):
                    self.disconnect()
                    self.status.configure(text=item[1])
                else:
                    self.handle(item)
        except queue.Empty:
            pass
        if self.map_on and self.track and time.time() - self.map_written > 2:
            self.update_map()
        self.root.after(100, self.poll)

    def handle(self, line):
        res = parse(line)
        if res is None:
            self.counts['(bledna suma)'] += 1
            self.log.insert('end', line + '\n', 'bad')
        else:
            kind, d = res
            self.counts[line[1:6]] += 1
            if d.pop('valid', True) is False:
                self.counts['%s niewazne' % kind] += 1
            self.state.update(d)
            if 'lat' in d:
                pt = (d['lat'], d['lon'])
                if not self.track or self.track[-1] != pt:
                    self.track.append(pt)
            self.log.insert('end', line + '\n')
        if int(self.log.index('end').split('.')[0]) > 3000:
            self.log.delete('1.0', '1000.0')
        self.log.see('end')
        for key, lbl in self.vals.items():
            if key in self.state:
                lbl.configure(text=fmt(key, self.state[key]))
        self.stats.configure(text='\n'.join('%-16s %6d' % kv for kv in sorted(self.counts.items())))

    # --- mapa
    def need_fix(self):
        if 'lat' not in self.state:
            messagebox.showinfo('Brak pozycji', 'Brak waznej pozycji (status A / fix > 0). Wyjdz pod okno.')
            return False
        return True

    def update_map(self):
        s = self.state
        popup = '%s, %s | wys. %s m | %s UTC' % (fmt('lat', s['lat']), fmt('lon', s['lon']),
                                               s.get('alt', '?'), s.get('time', '?'))
        write_map(s['lat'], s['lon'], self.track[-500:], popup)
        self.map_written = time.time()

    def open_map(self):
        if self.need_fix():
            self.update_map()
            self.map_on = True
            webbrowser.open(MAP_FILE.as_uri())

    def open_google(self):
        if self.need_fix():
            webbrowser.open('https://www.google.com/maps?q=%.7f,%.7f' % (self.state['lat'], self.state['lon']))

    def save_log(self):
        path = filedialog.asksaveasfilename(defaultextension='.nmea', initialfile='gps_log.nmea')
        if path:
            Path(path).write_text(self.log.get('1.0', 'end'), encoding='utf-8')

    def close(self):
        self.stop.set()
        self.root.destroy()


# ---------------------------------------------------------------- test

def selftest():
    assert checksum_ok('$GPRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W*6A')
    assert not checksum_ok('$GPRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W*6B')
    k, d = parse('$GPRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W*6A')
    assert k == 'RMC' and d['valid'] and d['date'] == '23.03.1994'
    assert abs(d['lat'] - 48.1173) < 1e-4 and abs(d['lon'] - 11.516667) < 1e-5
    k, d = parse('$GPGGA,123519,4807.038,N,01131.000,W,1,08,0.9,545.4,M,46.9,M,,*55')
    assert k == 'GGA' and d['sats'] == 8 and d['alt'] == 545.4 and d['lon'] < 0
    k, d = parse('$GPGLL,4916.45,N,12311.12,W,225444,V,*0A')
    assert k == 'GLL' and not d['valid'] and 'lat' not in d
    k, d = parse('$GPZDA,201530.00,04,07,2002,00,00*60')
    assert d['date'] == '04.07.2002' and d['time'] == '20:15:30'
    assert to_deg('5106.474', 'N') == 51 + 6.474 / 60 and to_deg('', 'N') is None
    print('OK')


if __name__ == '__main__':
    if '--test' in sys.argv:
        selftest()
    else:
        root = tk.Tk()
        App(root)
        root.mainloop()
