#!/opt/homebrew/bin/python3
"""Read-only bridge health check; no URLs or page titles printed."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent/'native'))
import bridge
connected=0
for profile in bridge.profiles():
    try:
        windows=bridge.request(profile,{'action':'snapshot'},timeout=5)
        print('Conectado: %d ventanas, %d pestañas, %d grupos' %
              (len(windows),sum(len(w['source']['tabs']) for w in windows),sum(len(w['source']['groups']) for w in windows)))
        connected+=1
    except (OSError,ValueError,RuntimeError,EOFError): pass
if not connected:
    print('Pendiente: carga la extensión en Chrome y pulsa su icono para conectar.')
    sys.exit(1)
