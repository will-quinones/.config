"""Bounded local transport shared by the native host and layout adapter."""
import json
import os
from pathlib import Path
import re
import socket
import stat
import struct

LIMIT = 900_000
PROFILE = re.compile(r'[a-f0-9]{32}')
ROOT = Path('/tmp') / ('yabai-chrome-' + str(os.getuid()))


def directory():
    ROOT.mkdir(mode=0o700, exist_ok=True)
    info = ROOT.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ValueError('Directorio de conexión Chrome inseguro')
    return ROOT


def address(profile):
    if not isinstance(profile, str) or not PROFILE.fullmatch(profile):
        raise ValueError('Perfil Chrome inválido')
    return directory() / (profile + '.sock')


def pack(value):
    data = json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode()
    if len(data) > LIMIT: raise ValueError('Demasiadas pestañas para un mensaje local')
    return struct.pack('=I', len(data)) + data


def receive(read):
    def exact(size):
        result = b''
        while len(result) < size:
            part = read(size-len(result))
            if not part: raise EOFError('Conexión Chrome cerrada')
            result += part
        return result
    size, = struct.unpack('=I', exact(4))
    if not 0 < size <= LIMIT: raise ValueError('Mensaje Chrome demasiado grande')
    return json.loads(exact(size))


def request(profile, payload, timeout=35):
    with socket.socket(socket.AF_UNIX) as client:
        client.settimeout(timeout)
        client.connect(str(address(profile)))
        client.sendall(pack(payload))
        result = receive(client.recv)
    if not isinstance(result, dict) or not result.get('ok'):
        raise RuntimeError(result.get('error', 'Respuesta Chrome inválida') if isinstance(result, dict) else 'Respuesta Chrome inválida')
    return result['result']


def profiles():
    return [p.stem for p in directory().glob('*.sock') if PROFILE.fullmatch(p.stem)]
