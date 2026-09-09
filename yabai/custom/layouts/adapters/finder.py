"""Read Finder window targets by window ID and reopen local folders through AppleScript."""
import json
from pathlib import Path
import subprocess
from .vscode import local_path
BUNDLE = 'com.apple.finder'

def identify(windows, hints=()):
    if not any(w.get('bundle_id') == BUNDLE for w in windows): return {}
    script = 'var f=Application("Finder"); if(!f.running()){JSON.stringify([])}else{JSON.stringify(f.finderWindows().map(function(w){try{return {id:w.id(),url:w.target().url()};}catch(e){return {id:w.id()};}}));}'
    r = subprocess.run(['/usr/bin/osascript', '-l', 'JavaScript', '-e', script],capture_output=True,text=True,timeout=15)
    if r.returncode: raise RuntimeError('Finder no permitió leer carpetas; revisa permisos de Automatización')
    live_ids = {w['id'] for w in windows if w.get('bundle_id') == BUNDLE}
    result = {}
    for row in json.loads(r.stdout):
        path = local_path(row.get('url'))
        if row['id'] in live_ids and path and Path(path).is_dir():
            result[row['id']] = dict(kind='finder-folder', path=path)
    return result


def launch(source):
    p = Path(source['path'])
    if not p.is_absolute() or not p.is_dir(): raise ValueError('Carpeta Finder ausente o inválida')
    script = 'on run argv\nset targetFolder to (POSIX file (item 1 of argv)) as alias\ntell application "Finder"\nmake new Finder window to targetFolder\nend tell\nend run'
    r = subprocess.run(['/usr/bin/osascript','-e',script,str(p)],capture_output=True,text=True,timeout=15)
    if r.returncode: raise RuntimeError(r.stderr.strip() or 'Finder no pudo abrir la carpeta')
