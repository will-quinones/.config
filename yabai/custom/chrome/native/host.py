#!/opt/homebrew/bin/python3
"""Chrome native host: one private Unix socket per browser profile, no shell execution."""
import fcntl
import json
from pathlib import Path
import select
import socket
import sys
import time
import uuid
from bridge import address, pack, receive


def main():
    manifest = json.loads((Path(__file__).parent.parent / 'extension/manifest.json').read_text())
    import base64, hashlib
    raw = hashlib.sha256(base64.b64decode(manifest['key'])).hexdigest()[:32]
    extension_id = ''.join(chr(ord('a') + int(c, 16)) for c in raw)
    if len(sys.argv) < 2 or sys.argv[1].rstrip('/') != 'chrome-extension://' + extension_id:
        raise ValueError('Origen no autorizado')
    incoming = sys.stdin.buffer
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
                            if not select.select([incoming], [], [], 30)[0]:
                                raise TimeoutError('Chrome no respondió; no se reintentó la apertura')
                            response = receive(incoming.read)
                            if response.get('id') != ident: raise ValueError('Respuesta fuera de secuencia')
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
