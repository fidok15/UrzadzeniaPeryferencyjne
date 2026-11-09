"""
Transmisja Bluetooth Windows -> telefon (Android) - Cwiczenie 12, Urzadzenia Peryferyjne.

a) otwarcie adaptera na starcie programu, zamkniecie przy wyjsciu,
b) wyszukiwanie aktywnych urzadzen Bluetooth Classic (BR/EDR) w poblizu,
c) parowanie z wybranym urzadzeniem (okno parowania Windows, SSP),
d) wyslanie pliku (tekst, zdjecie, max 1 MB) usluga OBEX Object Push (OPP, UUID 0x1105)
   po kanale RFCOMM. Protokol OBEX zaimplementowany recznie (obex_put).

Bluetooth: Win32 API (bthprops.cpl, ws2_32) przez ctypes + gniazdo RFCOMM z biblioteki
standardowej - bez dodatkowych pakietow. iPhone nie obsluguje OBEX Object Push.

    python bt_telefon_windows.py          # GUI (Windows)
    python bt_telefon_windows.py --test   # test protokolu OBEX na symulowanym telefonie
"""
import ctypes
import mimetypes
import queue
import random
import socket
import struct
import sys
import threading
import time
from ctypes import byref, sizeof, c_void_p, c_uint8, c_uint16, c_uint32, c_uint64, c_int, c_wchar, Structure
from dataclasses import dataclass, field
from pathlib import Path

MAX_FILE = 1_000_000                         # limit 1 MB (jak w sprawozdaniu innej grupy)
ALLOWED = {'.txt', '.jpg', '.jpeg', '.png'}  # tekst + fotografie
INQUIRY_SECONDS = 10                         # dlugosc wyszukiwania, mozna zwiekszyc
OPP_UUID16 = 0x1105                          # OBEX Object Push


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


# ---------------------------------------------------------------- OBEX (klient)

OBEX_CONNECT, OBEX_DISCONNECT, OBEX_PUT, OBEX_PUT_FINAL = 0x80, 0x81, 0x02, 0x82
OK, CONTINUE = 0xA0, 0x90
H_NAME, H_TYPE, H_LENGTH, H_BODY, H_END_BODY, H_CONN_ID = 0x01, 0x42, 0xC3, 0x48, 0x49, 0xCB
MY_MAX_PACKET = 0x2000
RESPONSES = {0x90: 'Continue', 0xA0: 'OK', 0xC0: 'Bad Request', 0xC1: 'Unauthorized',
             0xC3: 'Forbidden (odrzucono na telefonie)', 0xC4: 'Not Found',
             0xCD: 'Request Entity Too Large', 0xCF: 'Unsupported Media Type',
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


def read_response(link):
    head = link.recv_exact(3)
    length = struct.unpack('>H', head[1:])[0]
    if length < 3:
        raise BtError('Uszkodzona odpowiedz OBEX')
    return head[0], link.recv_exact(length - 3)


def obex_put(link, name, data, mime=None, progress=lambda sent, total: None):
    """CONNECT -> PUT (kilka pakietow Body, ostatni End-of-Body) -> DISCONNECT."""
    link.send(packet(OBEX_CONNECT, bytes([0x10, 0x00]) + struct.pack('>H', MY_MAX_PACKET)))
    code, rest = read_response(link)
    if code != OK:
        raise ObexError(code)
    max_packet = min(struct.unpack('>H', rest[2:4])[0], MY_MAX_PACKET)
    conn = rest[4:9] if rest[4:5] == bytes([H_CONN_ID]) else b''   # Connection-Id, jesli telefon go nadal
    first = (hdr_unicode(H_NAME, name) + bytes([H_LENGTH]) + struct.pack('>I', len(data))
             + (hdr_bytes(H_TYPE, mime.encode() + b'\0') if mime else b''))
    sent = 0
    try:
        while True:
            room = max_packet - 3 - len(conn) - len(first) - 3
            chunk = data[sent:sent + room]
            sent += len(chunk)
            last = sent >= len(data)
            link.send(packet(OBEX_PUT_FINAL if last else OBEX_PUT,
                             conn + first + hdr_bytes(H_END_BODY if last else H_BODY, chunk)))
            first = b''
            code, _ = read_response(link)
            if code != (OK if last else CONTINUE):
                raise ObexError(code)
            progress(sent, len(data))
            if last:
                return
    finally:
        try:
            link.send(packet(OBEX_DISCONNECT, conn))
            read_response(link)
        except Exception:
            pass


def check_file(path):
    """Walidacja przed wyslaniem: format i rozmiar."""
    p = Path(path)
    if p.suffix.lower() not in ALLOWED:
        raise BtError(f'Nieprawidlowy format {p.suffix or "(brak)"}; dozwolone: {", ".join(sorted(ALLOWED))}')
    size = p.stat().st_size
    if size > MAX_FILE:
        raise BtError(f'Plik za duzy: {size} B (max {MAX_FILE} B)')
    return p


# ---------------------------------------------------------------- Windows

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


AF_BTH = 32
MITM_REQUIRED_GENERAL_BONDING = 5
AUTH_LEGACY, AUTH_OOB, AUTH_NUMERIC, AUTH_PASSKEY_NOTIFICATION, AUTH_PASSKEY = 1, 2, 3, 4, 5


class BLUETOOTH_AUTHENTICATION_CALLBACK_PARAMS(Structure):
    _fields_ = [('deviceInfo', BLUETOOTH_DEVICE_INFO), ('authenticationMethod', c_int),
                ('ioCapability', c_int), ('authenticationRequirements', c_int), ('value', c_uint32)]


class BLUETOOTH_PIN_INFO(Structure):
    _fields_ = [('pin', c_uint8 * 16), ('pinLength', c_uint8)]


class AUTH_RESPONSE_UNION(ctypes.Union):
    _fields_ = [('pinInfo', BLUETOOTH_PIN_INFO), ('oobInfo', c_uint8 * 32), ('value', c_uint32)]


class BLUETOOTH_AUTHENTICATE_RESPONSE(Structure):
    _fields_ = [('bthAddressRemote', c_uint64), ('authMethod', c_int), ('u', AUTH_RESPONSE_UNION),
                ('negativeResponse', c_uint8)]


AUTH_CALLBACK = getattr(ctypes, 'WINFUNCTYPE', ctypes.CFUNCTYPE)(
    c_int, c_void_p, ctypes.POINTER(BLUETOOTH_AUTHENTICATION_CALLBACK_PARAMS))
OPP_GUID = (OPP_UUID16, 0, 0x1000, (0x80, 0, 0, 0x80, 0x5F, 0x9B, 0x34, 0xFB))  # 00001105-0000-1000-8000-00805F9B34FB


class SockLink:
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


class WinBackend:
    def open(self):
        self.bt = bt = ctypes.WinDLL('bthprops.cpl')
        self.ws2 = ctypes.WinDLL('ws2_32')
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
        bt.BluetoothRegisterForAuthenticationEx.argtypes = [c_void_p, c_void_p, AUTH_CALLBACK, c_void_p]
        bt.BluetoothUnregisterAuthentication.argtypes = [c_void_p]
        bt.BluetoothSendAuthenticationResponseEx.argtypes = [c_void_p, c_void_p]
        self.k32.CloseHandle.argtypes = [c_void_p]
        self.ws2.connect.argtypes = [ctypes.c_size_t, c_void_p, c_int]

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

    def idle(self):
        time.sleep(0.05)

    def discover(self, log):
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

    def pair(self, dev, log):
        """Parowanie z wlasnym callbackiem zamiast okna Windows: program sam odpowiada
        na zadanie uwierzytelnienia (PIN dla starych telefonow, kod 6 cyfr dla SSP)."""
        pin = f'{random.randint(0, 9999):04d}'

        def on_auth(_, params):
            prm = params.contents
            resp = BLUETOOTH_AUTHENTICATE_RESPONSE()
            resp.bthAddressRemote = prm.deviceInfo.Address
            resp.authMethod = method = prm.authenticationMethod
            if method == AUTH_LEGACY:
                log(f'Telefon wymaga PIN-u. Wpisz na telefonie PIN: {pin}')
                for i, ch in enumerate(pin.encode()):
                    resp.u.pinInfo.pin[i] = ch
                resp.u.pinInfo.pinLength = len(pin)
            elif method == AUTH_NUMERIC:
                log(f'Kod parowania {prm.value:06d} - potwierdz go na telefonie')
                resp.u.value = prm.value
            elif method == AUTH_PASSKEY_NOTIFICATION:
                log(f'Wpisz na telefonie kod {prm.value:06d}')
                resp.u.value = prm.value
            else:
                log(f'Nieobslugiwana metoda parowania {method}')
                resp.negativeResponse = 1
            r = self.bt.BluetoothSendAuthenticationResponseEx(self.radio, byref(resp))
            if r != 0:
                log(f'Odpowiedz parowania: blad Win32 {r}')
            return 1

        callback = AUTH_CALLBACK(on_auth)        # referencja musi zyc do wyrejestrowania
        reg = c_void_p()
        r = self.bt.BluetoothRegisterForAuthenticationEx(byref(dev.raw), byref(reg), callback, None)
        if r != 0:
            raise BtError(f'Nie mozna zarejestrowac obslugi parowania (blad Win32 {r})')
        log('Parowanie... odblokuj telefon i obserwuj ekran / powiadomienia')
        try:
            r = self.bt.BluetoothAuthenticateDeviceEx(None, self.radio, byref(dev.raw), None,
                                                      MITM_REQUIRED_GENERAL_BONDING)
        finally:
            self.bt.BluetoothUnregisterAuthentication(reg)
        if r != 0:
            raise BtError(f'Parowanie nieudane (blad Win32 {r}). Odrzucono na telefonie albo minal czas')

    def connect_opp(self, dev, log):
        sock = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)
        # port=0 + serviceClassId: Windows sam robi zapytanie SDP i wybiera kanal RFCOMM uslugi OPP
        d1, d2, d3, d4 = OPP_GUID
        addr = SOCKADDR_BTH(AF_BTH, dev.raw.Address, GUID(d1, d2, d3, (c_uint8 * 8)(*d4)), 0)
        if self.ws2.connect(sock.fileno(), byref(addr), sizeof(addr)) != 0:
            err = self.ws2.WSAGetLastError()
            sock.close()
            raise BtError(f'Brak polaczenia z usluga OBEX Object Push (WSA {err})')
        sock.settimeout(60)
        return SockLink(sock)


def make_backend():
    if not hasattr(ctypes, 'WinDLL'):
        raise BtError('Ten program dziala tylko na Windows')
    return WinBackend()


# ---------------------------------------------------------------- GUI

def run_gui():
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox

    root = tk.Tk()
    root.title('Bluetooth Windows -> telefon (OBEX)')
    root.geometry('760x520')
    jobs, events = queue.Queue(), queue.Queue()
    state = {'devices': [], 'file': None, 'busy': False}

    def log(msg):
        events.put(('log', msg))

    def worker():
        """Jeden watek dla operacji Bluetooth (blokujacych), GUI dostaje wyniki przez kolejke events."""
        try:
            backend = make_backend()
            events.put(('adapter', backend.open()))
        except Exception as e:
            events.put(('adapter', None))
            events.put(('error', str(e)))
            return
        log('Adapter otwarty')
        while True:
            try:
                job = jobs.get_nowait()
            except queue.Empty:
                backend.idle()
                continue
            if job is None:
                backend.close()
                return
            events.put(('busy', True))
            try:
                job(backend)
            except Exception as e:
                events.put(('error', str(e)))
            events.put(('busy', False))

    # --- akcje (wykonywane w watku worker)
    def do_discover(b):
        log(f'Wyszukiwanie urzadzen ({INQUIRY_SECONDS} s)...')
        devs = b.discover(log)
        events.put(('devices', devs))
        log(f'Znaleziono {len(devs)} urzadzen')

    def do_pair(dev):
        def job(b):
            if dev.paired:
                log(f'{dev.name} jest juz sparowany')
                return
            log(f'Parowanie z {dev.name}...')
            b.pair(dev, log)
            dev.paired = True
            events.put(('info', dev))
            log('Sparowano')
        return job

    def do_send(dev, path):
        def job(b):
            p = check_file(path)
            data = p.read_bytes()
            log(f'Wysylanie {p.name} ({len(data)} B) do {dev.name} - zaakceptuj na telefonie')
            link = b.connect_opp(dev, log)
            t0 = time.time()
            try:
                obex_put(link, p.name, data, mimetypes.guess_type(p.name)[0],
                         lambda s, n: events.put(('progress', 100 * s // max(n, 1))))
            finally:
                link.close()
            dt = time.time() - t0
            log(f'Wyslano w {dt:.1f} s ({len(data) / 1024 / max(dt, 1e-3):.1f} KiB/s)')
        return job

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
    btn_find = ttk.Button(bar, text='Wyszukaj urzadzenia', command=lambda: jobs.put(do_discover))
    btn_pair = ttk.Button(bar, text='Sparuj', command=lambda: selected() and jobs.put(do_pair(selected())))
    btn_file = ttk.Button(bar, text='Wybierz plik', command=lambda: choose_file())
    btn_send = ttk.Button(bar, text='Wyslij plik',
                          command=lambda: selected() and jobs.put(do_send(selected(), state['file'])))
    for b in (btn_find, btn_pair, btn_file, btn_send):
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

    def refresh_buttons():
        busy, dev = state['busy'], selected()
        btn_find['state'] = 'disabled' if busy else 'normal'
        btn_pair['state'] = 'normal' if dev and not busy else 'disabled'
        btn_file['state'] = 'disabled' if busy else 'normal'
        btn_send['state'] = 'normal' if dev and state['file'] and not busy else 'disabled'

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
            elif kind == 'adapter':
                adapter_var.set(f'Adapter: {arg[0]}' if arg[0] else 'Adapter: niedostepny')
            elif kind == 'devices':
                state['devices'] = arg[0]
                lst.delete(0, 'end')
                for d in arg[0]:
                    lst.insert('end', f'{d.name}  [{d.address}]')
            elif kind == 'info':
                show_info(arg[0])
            elif kind == 'progress':
                progress['value'] = arg[0]
            elif kind == 'busy':
                state['busy'] = arg[0]
                if arg[0]:
                    progress['value'] = 0
            refresh_buttons()
        root.after(100, poll)

    def on_close():
        jobs.put(None)               # zamkniecie adaptera w watku Bluetooth
        th.join(timeout=3)
        root.destroy()

    root.protocol('WM_DELETE_WINDOW', on_close)
    th = threading.Thread(target=worker, daemon=True)
    th.start()
    refresh_buttons()
    poll()
    root.mainloop()


# ---------------------------------------------------------------- test

class FakePhone:
    """Udaje serwer OBEX OPP telefonu (max pakiet 255 B, Connection-Id), zbiera odebrany plik."""

    def __init__(self, reject=False):
        self.reject, self.out, self.name, self.body, self.length = reject, b'', None, b'', None
        self.ops = []

    def send(self, pkt):
        op, n = pkt[0], struct.unpack('>H', pkt[1:3])[0]
        assert n == len(pkt), 'zla dlugosc pakietu'
        self.ops.append(op)
        if op == OBEX_CONNECT:
            self.out += bytes([OK]) + struct.pack('>H', 12) + bytes([0x10, 0]) + struct.pack('>H', 255) \
                + bytes([H_CONN_ID]) + struct.pack('>I', 7)
            return
        if op in (OBEX_PUT, OBEX_PUT_FINAL):
            assert len(pkt) <= 255, 'pakiet wiekszy niz max telefonu'
            h = pkt[3:]
            assert h[:5] == bytes([H_CONN_ID]) + struct.pack('>I', 7), 'brak Connection-Id'
            h = h[5:]
            while h:
                hid = h[0]
                if hid == H_LENGTH:
                    self.length = struct.unpack('>I', h[1:5])[0]
                    h = h[5:]
                    continue
                ln = struct.unpack('>H', h[1:3])[0]
                val, h = h[3:ln], h[ln:]
                if hid == H_NAME:
                    self.name = val[:-2].decode('utf-16-be')
                elif hid in (H_BODY, H_END_BODY):
                    self.body += val
            code = 0xC3 if self.reject else OK if op == OBEX_PUT_FINAL else CONTINUE
            self.out += bytes([code, 0, 3])
            return
        self.out += bytes([OK, 0, 3])          # DISCONNECT

    def recv_exact(self, n):
        r, self.out = self.out[:n], self.out[n:]
        assert len(r) == n
        return r


def self_test():
    data = bytes(range(256)) * 10
    phone = FakePhone()
    steps = []
    obex_put(phone, 'zdjęcie.jpg', data, 'image/jpeg', lambda s, n: steps.append(s))
    assert phone.name == 'zdjęcie.jpg' and phone.body == data and phone.length == len(data)
    assert phone.ops[0] == OBEX_CONNECT and phone.ops[-2] == OBEX_PUT_FINAL and phone.ops[-1] == OBEX_DISCONNECT
    assert steps[-1] == len(data) and len(steps) > 10
    empty = FakePhone()
    obex_put(empty, 'pusty.txt', b'')
    assert empty.body == b'' and empty.ops == [OBEX_CONNECT, OBEX_PUT_FINAL, OBEX_DISCONNECT]
    rej = FakePhone(reject=True)
    try:
        obex_put(rej, 'a.txt', b'abc')
        raise AssertionError('brak bledu przy odrzuceniu')
    except ObexError as e:
        assert e.code == 0xC3 and rej.ops[-1] == OBEX_DISCONNECT
    assert major_class(0x5A020C) == 'Telefon' and fmt_addr(0xC89F0C0E41BE) == 'C8:9F:0C:0E:41:BE'
    print('OBEX test OK')


if __name__ == '__main__':
    self_test() if '--test' in sys.argv else run_gui()
