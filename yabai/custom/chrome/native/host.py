#!/opt/homebrew/bin/python3
"""Chrome native host: one private Unix socket per browser profile, no shell execution."""
import fcntl
import json
import os
import re
from pathlib import Path
import select
import socket
import sys
import time
import uuid
from bridge import address, pack, receive


def diagnostic(stage, elapsed):
    path = Path.home() / '.local/state/yabai-desktop-layout/chrome-bridge.log'
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with open(path, 'a') as log:
        log.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] +{elapsed:.1f}s {stage}\n")


def wait_response(incoming, ident, action, report=diagnostic):
    """A progressing restore may exceed 30s; an idle step may not."""
    started = time.monotonic()
    total = started + (120 if action == 'restore' else 30)
    idle = min(total, started + 30)
    stage = 'request-sent'
    report(action + ':' + stage, 0)
    while True:
        def read(size):
            remaining = min(total, idle) - time.monotonic()
            if remaining <= 0 or not select.select([incoming], [], [], remaining)[0]:
                raise TimeoutError('Chrome sin respuesta en ' + stage + '; apertura no repetida')
            return os.read(incoming.fileno(), size)
        response = receive(read)
        if response.get('id') != ident:
            raise ValueError('Respuesta fuera de secuencia')
        if response.get('type') == 'progress':
            value = response.get('stage', '')
            if not isinstance(value, str) or not re.fullmatch(r'[a-zA-Z0-9_.:-]{1,80}', value):
                raise ValueError('Etapa Chrome inválida')
            stage = value
            report(action + ':' + stage, time.monotonic()-started)
            idle = min(total, time.monotonic()+30)
            continue
        report(action + ':finished', time.monotonic()-started)
        return response


def main():
    manifest = json.loads((Path(__file__).parent.parent / 'extension/manifest.json').read_text())
    import base64, hashlib
    raw = hashlib.sha256(base64.b64decode(manifest['key'])).hexdigest()[:32]
    extension_id = ''.join(chr(ord('a') + int(c, 16)) for c in raw)
    if len(sys.argv) < 2 or sys.argv[1].rstrip('/') != 'chrome-extension://' + extension_id:
        raise ValueError('Origen no autorizado')
    incoming = sys.stdin.buffer.raw
    outgoing = sys.stdout.buffer
    hello = receive(incoming.read)
    if hello.get('type') != 'hello': raise ValueError('Falta saludo Chrome')
    path = address(hello.get('profile'))
    with open(path.with_suffix('.lock'), 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        path.unlink(missing_ok=True)
        with socket.socket(socket.AF_UNIX) as server:
            server.bind(str(path)); server.listen(2)
            outgoing.write(pack({'type':'ready'})); outgoing.flush()
            try:
                while True:
                    ready, _, _ = select.select([server, incoming], [], [])
                    if incoming in ready:
                        # EOF or an unsolicited message ends the host; no cached commands.
                        receive(incoming.read)
                        raise ValueError('Respuesta sin solicitud')
                    client, _ = server.accept()
                    with client:
                        client.settimeout(5)
                        try:
                            command = receive(client.recv)
                            if not isinstance(command, dict) or command.get('action') not in ('snapshot','restore'):
                                raise ValueError('Acción no permitida')
                            ident = uuid.uuid4().hex
                            outgoing.write(pack({**command, 'type':'request','id':ident})); outgoing.flush()
                            response = wait_response(incoming, ident, command['action'])
                            client.sendall(pack(response))
                        except (OSError, ValueError, EOFError, TimeoutError) as exc:
                            try: client.sendall(pack({'ok':False, 'error':str(exc)}))
                            except OSError: pass
                            # A timed-out mutation must not run again automatically.
                            if isinstance(exc, (TimeoutError, EOFError)): return
            finally:
                path.unlink(missing_ok=True)

if __name__ == '__main__':
    import os
    os.umask(0o077)
    try: main()
    except (OSError, ValueError, EOFError) as exc:
        print('Chrome bridge: '+str(exc), file=sys.stderr)
        sys.exit(1)
