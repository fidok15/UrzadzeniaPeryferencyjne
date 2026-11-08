"""
Transmisja Bluetooth Windows <-> Windows - Cwiczenie 12, Urzadzenia Peryferyjne.

Ten sam program na obu komputerach:
  - nadawca:  wyszukanie urzadzen, parowanie, wyslanie pliku (tekst, zdjecie),
  - odbiorca: przycisk "Odbieraj pliki" - serwer OBEX na kanale RFCOMM,
              wlasna usluga SDP (APP_UUID), pliki trafiaja do Pobrane\\bluetooth.

Bluetooth: Win32 API (bthprops.cpl, ws2_32) przez ctypes + gniazdo RFCOMM z biblioteki
standardowej. Protokol OBEX zaimplementowany recznie (obex_put - klient, obex_serve - serwer).

    python bt_windows.py          # GUI (tylko Windows)
    python bt_windows.py --test   # test OBEX klient <-> serwer, bez Bluetooth (dowolny system)
"""
import ctypes
import mimetypes
import queue
import socket
import struct
import sys
import threading
import time
import uuid
from ctypes import (byref, sizeof, c_void_p, c_uint8, c_uint16, c_uint32, c_uint64, c_int,
                    c_wchar, c_wchar_p, Structure)
from dataclasses import dataclass, field
from pathlib import Path

MAX_FILE = 1_000_000                         # limit 1 MB
ALLOWED = {'.txt', '.jpg', '.jpeg', '.png'}  # tekst + fotografie
INQUIRY_SECONDS = 10                         # dlugosc wyszukiwania, mozna zwiekszyc
APP_UUID = uuid.UUID('b1e7a0c2-12f4-4c55-9a3e-5e1a7c0b0d12')   # usluga odbiornika bt_windows
RECEIVE_DIR = Path.home() / 'Downloads' / 'bluetooth'


class BtError(Exception):
    pass


@dataclass
class Device:
    name: str
    address: str
    paired: bool
    connected: bool
    cod: int = 0                             # Class of Device
    raw: object = field(default=None, repr=False)


MAJOR_CLASS = {1: 'Komputer', 2: 'Telefon', 3: 'Siec LAN', 4: 'Audio/Wideo',
               5: 'Peryferyjne', 6: 'Obrazowanie', 7: 'Wearable', 8: 'Zabawka', 9: 'Zdrowie'}


def major_class(cod):
    return MAJOR_CLASS.get((cod >> 8) & 0x1F, 'Inne')


def fmt_addr(a):
    return ':'.join(f'{(a >> s) & 0xFF:02X}' for s in range(40, -1, -8))


class SockLink:
    """Transport OBEX na gniezdzie RFCOMM."""

    def __init__(self, sock):
        self.sock = sock

    def send(self, data):
        self.sock.sendall(data)

    def recv_exact(self, n):
        buf = b''
        while len(buf) < n:
            chunk = self.sock.recv(n - len(buf))
            if not chunk:
                raise BtError('Polaczenie zerwane')
            buf += chunk
        return buf

    def close(self):
        self.sock.close()


# ---------------------------------------------------------------- OBEX

OBEX_CONNECT, OBEX_DISCONNECT, OBEX_PUT, OBEX_PUT_FINAL = 0x80, 0x81, 0x02, 0x82
OK, CONTINUE, BAD_REQUEST, TOO_LARGE = 0xA0, 0x90, 0xC0, 0xCD
H_NAME, H_TYPE, H_LENGTH, H_BODY, H_END_BODY, H_CONN_ID = 0x01, 0x42, 0xC3, 0x48, 0x49, 0xCB
MY_MAX_PACKET = 0x2000
RESPONSES = {0x90: 'Continue', 0xA0: 'OK', 0xC0: 'Bad Request', 0xC3: 'Forbidden',
             0xC4: 'Not Found', 0xCD: 'Request Entity Too Large (plik za duzy)',
             0xD0: 'Internal Server Error', 0xD3: 'Service Unavailable'}


class ObexError(BtError):
    def __init__(self, code):
        super().__init__(f'OBEX: odpowiedz 0x{code:02X} {RESPONSES.get(code, "")}')
        self.code = code


def packet(opcode, payload=b''):
    return bytes([opcode]) + struct.pack('>H', len(payload) + 3) + payload


def hdr_bytes(hid, value):
    return bytes([hid]) + struct.pack('>H', len(value) + 3) + value


def hdr_unicode(hid, text):
    return hdr_bytes(hid, text.encode('utf-16-be') + b'\0\0')


def read_packet(link):
    """Pakiet OBEX (zadanie lub odpowiedz): opcode/kod + dlugosc 2B + reszta."""
    head = link.recv_exact(3)
    length = struct.unpack('>H', head[1:])[0]
    if length < 3:
        raise BtError('Uszkodzony pakiet OBEX')
    return head[0], link.recv_exact(length - 3)


def parse_headers(h):
    """Naglowki OBEX; typ wynika z 2 najstarszych bitow ID: tekst, bajty, 1 B, 4 B."""
    out = []
    while h:
        hid, kind = h[0], h[0] & 0xC0
        if kind == 0x80:
            out.append((hid, h[1]))
            h = h[2:]
        elif kind == 0xC0:
            out.append((hid, struct.unpack('>I', h[1:5])[0]))
            h = h[5:]
        else:
            n = struct.unpack('>H', h[1:3])[0]
            if n < 3 or n > len(h):
                raise BtError('Uszkodzony naglowek OBEX')
            v = h[3:n]
            out.append((hid, v.decode('utf-16-be').rstrip('\0') if kind == 0 else v))
            h = h[n:]
    return out


def obex_put(link, name, data, mime=None, progress=lambda sent, total: None):
    """Klient: CONNECT -> PUT (kilka pakietow Body, ostatni End-of-Body) -> DISCONNECT."""
    link.send(packet(OBEX_CONNECT, bytes([0x10, 0x00]) + struct.pack('>H', MY_MAX_PACKET)))
    code, rest = read_packet(link)
    if code != OK:
        raise ObexError(code)
    max_packet = min(struct.unpack('>H', rest[2:4])[0], MY_MAX_PACKET)
    first = (hdr_unicode(H_NAME, name) + bytes([H_LENGTH]) + struct.pack('>I', len(data))
             + (hdr_bytes(H_TYPE, mime.encode() + b'\0') if mime else b''))
    sent = 0
    try:
        while True:
            room = max_packet - 3 - len(first) - 3
            chunk = data[sent:sent + room]
            sent += len(chunk)
            last = sent >= len(data)
            link.send(packet(OBEX_PUT_FINAL if last else OBEX_PUT,
                             first + hdr_bytes(H_END_BODY if last else H_BODY, chunk)))
            first = b''
            code, _ = read_packet(link)
            if code != (OK if last else CONTINUE):
                raise ObexError(code)
            progress(sent, len(data))
            if last:
                return
    finally:
        try:
            link.send(packet(OBEX_DISCONNECT))
            read_packet(link)
        except Exception:
            pass


def save_unique(folder, name, data):
    """Zapis pod nazwa od nadawcy, ale bez sciezek (../) i bez nadpisywania."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    base = Path(str(name).replace('\\', '/')).name
    if base in ('', '.', '..'):
        base = 'plik.bin'
    p, i = folder / base, 1
    while p.exists():
        p, i = folder / f'{Path(base).stem}({i}){Path(base).suffix}', i + 1
    p.write_bytes(data)
    return p


def obex_serve(link, folder, log=print, progress=lambda got, total: None):
    """Serwer: obsluguje jedna sesje OBEX (CONNECT ... DISCONNECT), zapisuje odebrane pliki."""
    name, total, body, saved = None, 0, bytearray(), []
    while True:
        op, payload = read_packet(link)
        if op == OBEX_CONNECT:
            link.send(packet(OK, bytes([0x10, 0x00]) + struct.pack('>H', MY_MAX_PACKET)))
        elif op == OBEX_DISCONNECT:
            link.send(packet(OK))
            return saved
        elif op in (OBEX_PUT, OBEX_PUT_FINAL):
            for hid, val in parse_headers(payload):
                if hid == H_NAME:
                    name = val
                elif hid == H_LENGTH:
                    total = val
                elif hid in (H_BODY, H_END_BODY):
                    body += val
            if total > MAX_FILE or len(body) > MAX_FILE:
                link.send(packet(TOO_LARGE))
                raise BtError(f'Odrzucono plik wiekszy niz {MAX_FILE} B')
            progress(len(body), total or len(body))
            if op == OBEX_PUT:
                link.send(packet(CONTINUE))
                continue
            p = save_unique(folder, name or 'plik.bin', bytes(body))
            saved.append(p)
            log(f'Odebrano {p.name} ({len(body)} B) -> {p}')
            link.send(packet(OK))
            name, total, body = None, 0, bytearray()
        else:
            link.send(packet(BAD_REQUEST))


def check_file(path):
    """Walidacja przed wyslaniem: format i rozmiar."""
    p = Path(path)
    if p.suffix.lower() not in ALLOWED:
        raise BtError(f'Nieprawidlowy format {p.suffix or "(brak)"}; dozwolone: {", ".join(sorted(ALLOWED))}')
    size = p.stat().st_size
    if size > MAX_FILE:
        raise BtError(f'Plik za duzy: {size} B (max {MAX_FILE} B)')
    return p


# ---------------------------------------------------------------- Win32 Bluetooth API

class SYSTEMTIME(Structure):
    _fields_ = [(n, c_uint16) for n in
                ('wYear', 'wMonth', 'wDayOfWeek', 'wDay', 'wHour', 'wMinute', 'wSecond', 'wMs')]


class BLUETOOTH_DEVICE_INFO(Structure):
    _fields_ = [('dwSize', c_uint32), ('Address', c_uint64), ('ulClassofDevice', c_uint32),
                ('fConnected', c_int), ('fRemembered', c_int), ('fAuthenticated', c_int),
                ('stLastSeen', SYSTEMTIME), ('stLastUsed', SYSTEMTIME), ('szName', c_wchar * 248)]


class BLUETOOTH_DEVICE_SEARCH_PARAMS(Structure):
    _fields_ = [('dwSize', c_uint32), ('fReturnAuthenticated', c_int), ('fReturnRemembered', c_int),
                ('fReturnUnknown', c_int), ('fReturnConnected', c_int), ('fIssueInquiry', c_int),
                ('cTimeoutMultiplier', c_uint8), ('hRadio', c_void_p)]


class BLUETOOTH_FIND_RADIO_PARAMS(Structure):
    _fields_ = [('dwSize', c_uint32)]


class BLUETOOTH_RADIO_INFO(Structure):
    _fields_ = [('dwSize', c_uint32), ('address', c_uint64), ('szName', c_wchar * 248),
                ('ulClassofDevice', c_uint32), ('lmpSubversion', c_uint16), ('manufacturer', c_uint16)]


class GUID(Structure):
    _fields_ = [('Data1', c_uint32), ('Data2', c_uint16), ('Data3', c_uint16), ('Data4', c_uint8 * 8)]


class SOCKADDR_BTH(Structure):
    _pack_ = 1
    _layout_ = 'ms'                          # uklad jak w MSVC (ws2bth.h, pshpack1)
    _fields_ = [('addressFamily', c_uint16), ('btAddr', c_uint64),
                ('serviceClassId', GUID), ('port', c_uint32)]


class SOCKET_ADDRESS(Structure):
    _fields_ = [('lpSockaddr', c_void_p), ('iSockaddrLength', c_int)]


class CSADDR_INFO(Structure):
    _fields_ = [('LocalAddr', SOCKET_ADDRESS), ('RemoteAddr', SOCKET_ADDRESS),
                ('iSocketType', c_int), ('iProtocol', c_int)]


class WSAQUERYSETW(Structure):
    _fields_ = [('dwSize', c_uint32), ('lpszServiceInstanceName', c_wchar_p), ('lpServiceClassId', c_void_p),
                ('lpVersion', c_void_p), ('lpszComment', c_wchar_p), ('dwNameSpace', c_uint32),
                ('lpNSProviderId', c_void_p), ('lpszContext', c_wchar_p), ('dwNumberOfProtocols', c_uint32),
                ('lpafpProtocols', c_void_p), ('lpszQueryString', c_wchar_p), ('dwNumberOfCsAddrs', c_uint32),
                ('lpcsaBuffer', c_void_p), ('dwOutputFlags', c_uint32), ('lpBlob', c_void_p)]


AF_BTH, BTHPROTO_RFCOMM, NS_BTH, BT_PORT_ANY = 32, 3, 16, 0xFFFFFFFF
RNRSERVICE_REGISTER, RNRSERVICE_DELETE = 0, 2
MITM_REQUIRED_GENERAL_BONDING = 5


def guid(u):
    return GUID(u.time_low, u.time_mid, u.time_hi_version, (c_uint8 * 8)(*u.bytes[8:]))


class WinBluetooth:
    def open(self):
        """Otwarcie adaptera: uchwyt pierwszego radia Bluetooth."""
        self.bt = bt = ctypes.WinDLL('bthprops.cpl')
        self.ws2 = ws2 = ctypes.WinDLL('ws2_32')
        self.k32 = ctypes.WinDLL('kernel32')
        bt.BluetoothFindFirstRadio.restype = c_void_p
        bt.BluetoothFindFirstRadio.argtypes = [c_void_p, c_void_p]
        bt.BluetoothFindRadioClose.argtypes = [c_void_p]
        bt.BluetoothGetRadioInfo.argtypes = [c_void_p, c_void_p]
        bt.BluetoothFindFirstDevice.restype = c_void_p
        bt.BluetoothFindFirstDevice.argtypes = [c_void_p, c_void_p]
        bt.BluetoothFindNextDevice.argtypes = [c_void_p, c_void_p]
        bt.BluetoothFindDeviceClose.argtypes = [c_void_p]
        bt.BluetoothAuthenticateDeviceEx.argtypes = [c_void_p, c_void_p, c_void_p, c_void_p, c_int]
        bt.BluetoothEnableDiscovery.argtypes = [c_void_p, c_int]
        bt.BluetoothEnableIncomingConnections.argtypes = [c_void_p, c_int]
        self.k32.CloseHandle.argtypes = [c_void_p]
        ws2.connect.argtypes = ws2.bind.argtypes = [ctypes.c_size_t, c_void_p, c_int]
        ws2.getsockname.argtypes = [ctypes.c_size_t, c_void_p, c_void_p]
        ws2.WSASetServiceW.argtypes = [c_void_p, c_int, c_uint32]

        params = BLUETOOTH_FIND_RADIO_PARAMS(sizeof(BLUETOOTH_FIND_RADIO_PARAMS))
        self.radio = c_void_p()
        find = bt.BluetoothFindFirstRadio(byref(params), byref(self.radio))
        if not find:
            raise BtError('Brak adaptera Bluetooth (lub wylaczony)')
        bt.BluetoothFindRadioClose(find)
        info = BLUETOOTH_RADIO_INFO()
        info.dwSize = sizeof(info)
        bt.BluetoothGetRadioInfo(self.radio, byref(info))
        return f'{info.szName} ({fmt_addr(info.address)})'

    def close(self):
        if getattr(self, 'radio', None):
            self.k32.CloseHandle(self.radio)
            self.radio = None

    def discover(self):
        p = BLUETOOTH_DEVICE_SEARCH_PARAMS(sizeof(BLUETOOTH_DEVICE_SEARCH_PARAMS), 1, 1, 1, 1, 1,
                                           round(INQUIRY_SECONDS / 1.28), self.radio)
        info = BLUETOOTH_DEVICE_INFO()
        info.dwSize = sizeof(info)
        found = {}
        h = self.bt.BluetoothFindFirstDevice(byref(p), byref(info))
        if not h:
            return []
        try:
            while True:
                raw = BLUETOOTH_DEVICE_INFO.from_buffer_copy(info)
                found[raw.Address] = Device(raw.szName or fmt_addr(raw.Address), fmt_addr(raw.Address),
                                            bool(raw.fAuthenticated), bool(raw.fConnected),
                                            raw.ulClassofDevice, raw)
                if not self.bt.BluetoothFindNextDevice(h, byref(info)):
                    break
        finally:
            self.bt.BluetoothFindDeviceClose(h)
        return list(found.values())

    def pair(self, dev):
        """Okno parowania Windows (SSP: ten sam kod na obu komputerach)."""
        r = self.bt.BluetoothAuthenticateDeviceEx(None, self.radio, byref(dev.raw), None,
                                                  MITM_REQUIRED_GENERAL_BONDING)
        if r != 0:
            raise BtError(f'Parowanie nieudane (blad Win32 {r})')

    def connect(self, dev):
        sock = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)
        # port=0 + serviceClassId: Windows sam robi zapytanie SDP i wybiera kanal RFCOMM odbiornika
        addr = SOCKADDR_BTH(AF_BTH, dev.raw.Address, guid(APP_UUID), 0)
        if self.ws2.connect(sock.fileno(), byref(addr), sizeof(addr)) != 0:
            err = self.ws2.WSAGetLastError()
            sock.close()
            raise BtError(f'Brak polaczenia z odbiornikiem (WSA {err}). '
                          'Czy na drugim komputerze wlaczono "Odbieraj pliki"?')
        sock.settimeout(60)
        return SockLink(sock)

    # --- odbior (serwer OBEX)
    def _service(self, action):
        """Rejestracja / usuniecie rekordu SDP, zeby nadawca znalazl nasz kanal RFCOMM."""
        q = WSAQUERYSETW()
        q.dwSize = sizeof(q)
        q.lpszServiceInstanceName = 'bt_windows OBEX'
        q.lpServiceClassId = ctypes.addressof(self._guid)
        q.dwNameSpace = NS_BTH
        q.dwNumberOfCsAddrs = 1
        q.lpcsaBuffer = ctypes.addressof(self._csa)
        if self.ws2.WSASetServiceW(byref(q), action, 0) != 0:
            raise BtError(f'Rejestracja uslugi SDP nieudana (WSA {self.ws2.WSAGetLastError()})')

    def start_server(self):
        self.bt.BluetoothEnableDiscovery(self.radio, 1)
        self.bt.BluetoothEnableIncomingConnections(self.radio, 1)
        srv = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)
        self._addr = SOCKADDR_BTH(AF_BTH, 0, GUID(), BT_PORT_ANY)
        n = c_int(sizeof(self._addr))
        if (self.ws2.bind(srv.fileno(), byref(self._addr), n) != 0
                or self.ws2.getsockname(srv.fileno(), byref(self._addr), byref(n)) != 0):
            srv.close()
            raise BtError(f'Nie mozna otworzyc gniazda RFCOMM (WSA {self.ws2.WSAGetLastError()})')
        srv.listen(1)
        self._guid = guid(APP_UUID)            # struktury musza zyc do wyrejestrowania
        self._csa = CSADDR_INFO(SOCKET_ADDRESS(ctypes.addressof(self._addr), sizeof(self._addr)),
                                SOCKET_ADDRESS(), socket.SOCK_STREAM, BTHPROTO_RFCOMM)
        self._service(RNRSERVICE_REGISTER)
        return srv, self._addr.port

    def stop_server(self, srv):
        try:
            self._service(RNRSERVICE_DELETE)
        finally:
            srv.close()


# ---------------------------------------------------------------- GUI

def run_gui():
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox

    if sys.platform != 'win32':
        print('bt_windows.py dziala tylko na Windows (na macOS uzyj bt_telefon.py)')
        return

    root = tk.Tk()
    root.title('Bluetooth Windows <-> Windows')
    root.geometry('800x540')
    events = queue.Queue()
    bt = WinBluetooth()
    state = {'devices': [], 'file': None, 'busy': False, 'server': None, 'ok': False}

    def log(msg):
        events.put(('log', msg))

    def background(fn):
        """Operacje Bluetooth blokuja - wykonujemy je w watku, wynik przez kolejke events."""
        def run():
            events.put(('busy', True))
            try:
                fn()
            except Exception as e:
                events.put(('error', str(e)))
            events.put(('busy', False))
        threading.Thread(target=run, daemon=True).start()

    def do_discover():
        log(f'Wyszukiwanie urzadzen ({INQUIRY_SECONDS} s)...')
        devs = bt.discover()
        events.put(('devices', devs))
        log(f'Znaleziono {len(devs)} urzadzen')

    def do_pair(dev):
        if dev.paired:
            log(f'{dev.name} jest juz sparowany')
            return
        log(f'Parowanie z {dev.name}: potwierdz kod na obu komputerach')
        bt.pair(dev)
        dev.paired = True
        events.put(('info', dev))
        log('Sparowano')

    def do_send(dev, path):
        p = check_file(path)
        data = p.read_bytes()
        log(f'Wysylanie {p.name} ({len(data)} B) do {dev.name}')
        link = bt.connect(dev)
        t0 = time.time()
        try:
            obex_put(link, p.name, data, mimetypes.guess_type(p.name)[0],
                     lambda s, n: events.put(('progress', 100 * s // max(n, 1))))
        finally:
            link.close()
        dt = time.time() - t0
        log(f'Wyslano w {dt:.1f} s ({len(data) / 1024 / max(dt, 1e-3):.1f} KiB/s)')

    def receiver(stop):
        """Watek nasluchujacy; kazde polaczenie = jedna sesja OBEX."""
        try:
            srv, port = bt.start_server()
        except Exception as e:
            events.put(('error', str(e)))
            events.put(('server', False))
            return
        log(f'Odbior wlaczony: kanal RFCOMM {port}, pliki w {RECEIVE_DIR}')
        srv.settimeout(1)
        try:
            while not stop.is_set():
                try:
                    conn, peer = srv.accept()
                except socket.timeout:
                    continue
                log(f'Polaczenie przychodzace od {peer[0]}')
                conn.settimeout(60)
                try:
                    obex_serve(SockLink(conn), RECEIVE_DIR, log,
                               lambda g, n: events.put(('progress', 100 * g // max(n, 1))))
                except Exception as e:
                    log(f'BLAD odbioru: {e}')
                finally:
                    conn.close()
        finally:
            bt.stop_server(srv)
            log('Odbior wylaczony')
            events.put(('server', False))

    # --- widok
    adapter_var = tk.StringVar(value='Adapter: otwieranie...')
    ttk.Label(root, textvariable=adapter_var).pack(anchor='w', padx=8, pady=4)
    top = ttk.Frame(root)
    top.pack(fill='both', expand=True, padx=8)
    left = ttk.LabelFrame(top, text='Znalezione urzadzenia')
    left.pack(side='left', fill='both', expand=True)
    lst = tk.Listbox(left, height=12, exportselection=False)
    lst.pack(fill='both', expand=True, padx=4, pady=4)
    right = ttk.LabelFrame(top, text='Informacje o urzadzeniu')
    right.pack(side='left', fill='both', padx=(8, 0))
    info_vars = {}
    for i, label in enumerate(('Nazwa', 'Adres', 'Klasa', 'Sparowany', 'Polaczony')):
        ttk.Label(right, text=label + ':').grid(row=i, column=0, sticky='w', padx=4, pady=2)
        info_vars[label] = tk.StringVar()
        ttk.Entry(right, textvariable=info_vars[label], state='readonly', width=28).grid(row=i, column=1, padx=4)
    file_var = tk.StringVar(value='Plik: (nie wybrano)')
    ttk.Label(right, textvariable=file_var, wraplength=260).grid(row=5, column=0, columnspan=2, sticky='w', padx=4, pady=6)

    bar = ttk.Frame(root)
    bar.pack(fill='x', padx=8, pady=6)
    btn_find = ttk.Button(bar, text='Wyszukaj urzadzenia', command=lambda: background(do_discover))
    btn_pair = ttk.Button(bar, text='Sparuj', command=lambda: background(lambda d=selected(): do_pair(d)))
    btn_file = ttk.Button(bar, text='Wybierz plik', command=lambda: choose_file())
    btn_send = ttk.Button(bar, text='Wyslij plik',
                          command=lambda: background(lambda d=selected(), f=state['file']: do_send(d, f)))
    btn_recv = ttk.Button(bar, text='Odbieraj pliki', command=lambda: toggle_receive())
    for b in (btn_find, btn_pair, btn_file, btn_send, btn_recv):
        b.pack(side='left', padx=(0, 6))
    progress = ttk.Progressbar(bar, maximum=100)
    progress.pack(side='left', fill='x', expand=True)

    logbox = tk.Text(root, height=8, state='disabled')
    logbox.pack(fill='both', padx=8, pady=(0, 8))

    def selected():
        sel = lst.curselection()
        return state['devices'][sel[0]] if sel else None

    def show_info(dev):
        for k, v in (('Nazwa', dev.name), ('Adres', dev.address), ('Klasa', major_class(dev.cod)),
                     ('Sparowany', 'Tak' if dev.paired else 'Nie'), ('Polaczony', 'Tak' if dev.connected else 'Nie')):
            info_vars[k].set(v)

    def choose_file():
        path = filedialog.askopenfilename(filetypes=[('Tekst i zdjecia', ' '.join('*' + e for e in sorted(ALLOWED))),
                                                     ('Wszystkie', '*.*')])
        if not path:
            return
        try:
            p = check_file(path)
        except Exception as e:
            messagebox.showerror('Plik', str(e))
            return
        state['file'] = str(p)
        file_var.set(f'Plik: {p.name} ({p.stat().st_size} B)')
        refresh_buttons()

    def toggle_receive():
        if state['server']:
            state['server'].set()
            btn_recv['text'] = 'Zatrzymywanie...'
            return
        stop = threading.Event()
        state['server'] = stop
        btn_recv['text'] = 'Zatrzymaj odbior'
        threading.Thread(target=receiver, args=(stop,), daemon=True).start()

    def refresh_buttons():
        busy, dev, ok = state['busy'], selected(), state['ok']
        btn_find['state'] = 'normal' if ok and not busy else 'disabled'
        btn_pair['state'] = 'normal' if ok and dev and not busy else 'disabled'
        btn_file['state'] = 'disabled' if busy else 'normal'
        btn_send['state'] = 'normal' if ok and dev and state['file'] and not busy else 'disabled'
        btn_recv['state'] = 'normal' if ok else 'disabled'

    def on_select(_):
        if selected():
            show_info(selected())
        refresh_buttons()

    lst.bind('<<ListboxSelect>>', on_select)

    def write_log(msg):
        logbox['state'] = 'normal'
        logbox.insert('end', time.strftime('%H:%M:%S ') + msg + '\n')
        logbox.see('end')
        logbox['state'] = 'disabled'

    def poll():
        while not events.empty():
            kind, *arg = events.get()
            if kind == 'log':
                write_log(arg[0])
            elif kind == 'error':
                write_log('BLAD: ' + arg[0])
                messagebox.showerror('Bluetooth', arg[0])
            elif kind == 'devices':
                state['devices'] = arg[0]
                lst.delete(0, 'end')
                for d in arg[0]:
                    lst.insert('end', f'{d.name}  [{d.address}]')
            elif kind == 'info':
                show_info(arg[0])
            elif kind == 'progress':
                progress['value'] = arg[0]
            elif kind == 'server':
                state['server'] = None
                btn_recv['text'] = 'Odbieraj pliki'
            elif kind == 'busy':
                state['busy'] = arg[0]
                if arg[0]:
                    progress['value'] = 0
            refresh_buttons()
        root.after(100, poll)

    def on_close():
        if state['server']:
            state['server'].set()    # watek odbioru wyrejestruje usluge SDP
            time.sleep(1.2)
        bt.close()                   # zamkniecie adaptera
        root.destroy()

    try:                             # otwarcie adaptera na starcie
        adapter_var.set(f'Adapter: {bt.open()}')
        state['ok'] = True
        write_log('Adapter otwarty')
    except Exception as e:
        adapter_var.set('Adapter: niedostepny')
        messagebox.showerror('Bluetooth', str(e))

    root.protocol('WM_DELETE_WINDOW', on_close)
    refresh_buttons()
    poll()
    root.mainloop()


# ---------------------------------------------------------------- test

def self_test():
    """Klient <-> serwer OBEX przez socketpair (jak Windows -> Windows, tylko bez radia)."""
    import tempfile
    big = bytes(range(256)) * 200            # 51 kB = kilka pakietow 8 kB
    with tempfile.TemporaryDirectory() as d:
        for name, payload in (('foto.jpg', big), ('../../zlo.txt', b'x'), ('foto.jpg', b'drugi'), ('pusty.txt', b'')):
            a, b = socket.socketpair()
            got, steps = [], []
            t = threading.Thread(target=lambda: got.extend(obex_serve(SockLink(b), d, log=lambda m: None)))
            t.start()
            obex_put(SockLink(a), name, payload, progress=lambda s, n: steps.append(s))
            t.join(5)
            a.close()
            b.close()
            assert got and got[0].read_bytes() == payload and got[0].parent == Path(d), got
            assert steps[-1] == len(payload)
        assert sorted(p.name for p in Path(d).iterdir()) == ['foto(1).jpg', 'foto.jpg', 'pusty.txt', 'zlo.txt']

        a, b = socket.socketpair()           # za duzy plik -> 0xCD, serwer zamyka polaczenie

        def serve_and_close():
            try:
                obex_serve(SockLink(b), d, log=lambda m: None)
            except BtError:
                pass
            finally:
                b.close()
        threading.Thread(target=serve_and_close, daemon=True).start()
        try:
            obex_put(SockLink(a), 'duzy.jpg', b'0' * (MAX_FILE + 1))
            raise AssertionError('serwer przyjal za duzy plik')
        except ObexError as e:
            assert e.code == TOO_LARGE
        a.close()
    try:
        parse_headers(bytes([H_NAME, 0, 0]))
        raise AssertionError('przyjeto uszkodzony naglowek')
    except BtError:
        pass
    assert major_class(0x10010C) == 'Komputer' and fmt_addr(0xC89F0C0E41BE) == 'C8:9F:0C:0E:41:BE'
    print('OBEX test OK')


if __name__ == '__main__':
    self_test() if '--test' in sys.argv else run_gui()
