"""Local VS Code folders/workspaces. Internal storage is a hint, never the authority alone."""
import json
from pathlib import Path
import re
import subprocess
import sqlite3
from urllib.parse import unquote, urlparse

BUNDLE = 'com.microsoft.VSCode'
CLI = Path('/Applications/Visual Studio Code.app/Contents/Resources/app/bin/code')

def local_path(uri):
    if not isinstance(uri, str): return None
    u = urlparse(uri)
    if u.scheme != 'file' or u.netloc not in ('', 'localhost'): return None
    p = Path(unquote(u.path))
    return str(p.resolve()) if p.is_absolute() and p.exists() else None


def candidates(hints=()):
    result = {}
    def add(uri, kind):
        target = local_path(uri)
        if not target: return
        path = Path(target)
        if kind == 'code-folder' and not path.is_dir(): return
        if kind == 'code-workspace' and (not path.is_file() or path.suffix != '.code-workspace'): return
        result[(kind, target)] = dict(kind=kind, path=target)
    for hint in hints:
        if hint.get('kind') in ('code-folder', 'code-workspace') and isinstance(hint.get('path'), str):
            path = Path(hint['path'])
            if path.is_absolute(): add(path.as_uri(), hint['kind'])
    base = Path.home() / 'Library/Application Support/Code/User/globalStorage'
    path = base / 'storage.json'
    if path.exists():
        data = json.loads(path.read_text())
        state = data.get('windowsState', {})
        for entry in [state.get('lastActiveWindow', {}), *state.get('openedWindows', [])]:
            add(entry.get('folder'), 'code-folder')
            workspace = entry.get('workspace')
            if isinstance(workspace, dict): add(workspace.get('configPath'), 'code-workspace')
        backups = data.get('backupWorkspaces', {})
        for entry in backups.get('folders', []):
            if isinstance(entry, dict): add(entry.get('folderUri'), 'code-folder')
        for entry in backups.get('workspaces', []):
            if isinstance(entry, dict): add(entry.get('configPath'), 'code-workspace')
    # Read only the recent-project index, not editor contents or arbitrary database keys.
    database = base / 'state.vscdb'
    if database.exists():
        try:
            connection = sqlite3.connect(database.as_uri() + '?mode=ro', uri=True, timeout=1)
            try:
                row = connection.execute('SELECT value FROM ItemTable WHERE key=?',
                                         ('history.recentlyOpenedPathsList',)).fetchone()
                if row:
                    for entry in json.loads(row[0]).get('entries', []):
                        if not isinstance(entry, dict): continue
                        add(entry.get('folderUri'), 'code-folder')
                        workspace = entry.get('workspace')
                        if isinstance(workspace, dict): add(workspace.get('configPath'), 'code-workspace')
            finally:
                connection.close()
        except sqlite3.Error as exc:
            raise ValueError('No se pudo leer el índice de proyectos recientes de Code: ' + str(exc))
    return list(result.values())


def identify(windows, hints=()):
    known = candidates(hints)
    output = {}
    for w in windows:
        if w.get('bundle_id') != BUNDLE: continue
        # Default title: "file — workspace". Refuse custom/ambiguous titles.
        tokens = re.split(r'\s+[—–]\s+', w.get('title', ''))
        tokens = [t.strip().removesuffix(' (Workspace)') for t in tokens]
        if tokens and tokens[-1] == 'Visual Studio Code': tokens.pop()
        if not tokens: continue
        # Code can show only the workspace name when no editor is active.
        workspace = tokens[-1]
        matches = []
        for source in known:
            p = Path(source['path'])
            label = p.name if source['kind'] == 'code-folder' else p.stem
            if label == workspace:
                matches.append(source)
        if len(matches) == 1: output[w['id']] = matches[0]
    return output


def launch(source):
    path = Path(source['path'])
    if not path.is_absolute() or not path.exists(): raise ValueError('Ruta de Code ausente o inválida')
    if source['kind'] == 'code-folder' and not path.is_dir(): raise ValueError('Se esperaba carpeta')
    if source['kind'] == 'code-workspace' and (not path.is_file() or path.suffix != '.code-workspace'):
        raise ValueError('Se esperaba archivo .code-workspace')
    if not CLI.is_file(): raise ValueError('No se encontró el CLI de VS Code')
    r = subprocess.run([str(CLI), '--new-window', str(path)], capture_output=True, text=True, timeout=20)
    if r.returncode: raise RuntimeError(r.stderr.strip() or 'Code no pudo abrir la ruta')
