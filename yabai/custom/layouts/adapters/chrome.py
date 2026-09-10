"""Chrome window shells using the last-used local profile; no extension required."""
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import threading
import time

BUNDLE = 'com.google.Chrome'
CHROME = Path('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')
YABAI = Path('/opt/homebrew/bin/yabai')
LOCAL_STATE = Path.home() / 'Library/Application Support/Google/Chrome/Local State'
STATE = Path.home() / '.local/state/yabai-desktop-layout'
TOKEN = re.compile(r'[a-f0-9]{32}')
MARKER = re.compile(r'YABAI_RESTORE_([a-f0-9]{32})')
PROFILE = re.compile(r'Default|Profile [0-9]+')
KNOWN = {}
LOCK = threading.Lock()
WINDOW_SECONDS = 45


def key(source):
    if not isinstance(source, dict) or source.get('kind') != 'chrome-window': return None
    token = source.get('token')
    if not isinstance(token, str) or not TOKEN.fullmatch(token): return None
    # Old extension layouts remain compatible; profile UUID is intentionally ignored.
    return 'chrome-window', token


def reset_cache():
    KNOWN.clear()


def last_profile():
    if not LOCAL_STATE.is_file():
        raise ValueError('Chrome no tiene Local State; ábrelo una vez y vuelve a intentar')
    data = json.loads(LOCAL_STATE.read_text())
    directory = data.get('profile', {}).get('last_used')
    if not isinstance(directory, str) or not PROFILE.fullmatch(directory):
        raise ValueError('Chrome no informó un último perfil normal (Default/Profile N)')
    return directory


def source_for(token, directory=None):
    if not isinstance(token, str) or not TOKEN.fullmatch(token):
        raise ValueError('Identificador Chrome inválido')
    return {'kind':'chrome-window', 'token':token,
            'profile_directory':directory or last_profile()}


def map_path():
    return STATE / 'chrome-window-map.json'


def marker_dir():
    return STATE / 'chrome-markers'


def read_map():
    path = map_path()
    if not path.is_file(): return []
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return []
    return data.get('windows', []) if isinstance(data, dict) else []


def write_map(records):
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = map_path()
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps({'format':1, 'windows':records}, separators=(',',':')))
    temporary.chmod(0o600)
    os.replace(temporary, path)


def remember(window, source):
    normalized = source_for(key(source)[1], source.get('profile_directory'))
    cache_key = (window.get('pid'), window['id'])
    with LOCK:
        KNOWN[cache_key] = normalized
        records = [r for r in read_map()
                   if not (r.get('pid') == cache_key[0] and r.get('id') == cache_key[1])
                   and r.get('token') != normalized['token']]
        records.append({'pid':cache_key[0], 'id':cache_key[1], **normalized})
        write_map(records)
    return normalized


def chrome_windows():
    result = subprocess.run([str(YABAI), '-m', 'query', '--windows'],
                            capture_output=True, text=True, timeout=5)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or 'yabai no pudo consultar ventanas')
    return [w for w in json.loads(result.stdout)
            if w.get('app') in ('Chrome','Google Chrome')]


def identify(windows, hints=()):
    chrome = [w for w in windows
              if w.get('bundle_id') == BUNDLE or w.get('app') in ('Chrome','Google Chrome')]
    if not chrome:
        with LOCK:
            KNOWN.clear()
            write_map([])
        return {}
    directory = last_profile()
    hint_by_token = {key(h)[1]:h for h in hints if key(h)}
    saved = {(r.get('pid'),r.get('id')):r for r in read_map()
             if isinstance(r,dict) and key(r)}
    output = {}
    valid_records = []
    for window in chrome:
        cache_key = (window.get('pid'),window['id'])
        found = MARKER.search(window.get('title',''))
        if found:
            token = found.group(1)
            source = source_for(token, directory)
        elif cache_key in KNOWN:
            source = KNOWN[cache_key]
        elif cache_key in saved:
            source = source_for(saved[cache_key]['token'], directory)
        else:
            # A normal save can adopt any currently open Chrome window safely.
            source = source_for(secrets.token_hex(16), directory)
        if found and found.group(1) in hint_by_token:
            source = source_for(found.group(1), directory)
        KNOWN[cache_key] = source
        output[window['id']] = source
        valid_records.append({'pid':cache_key[0], 'id':cache_key[1], **source})
    with LOCK:
        write_map(valid_records)
    return output


def marker_page(token):
    directory = marker_dir()
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = directory / (token + '.html')
    # The unique title makes concurrent blank windows unambiguous to yabai.
    path.write_text("""<!doctype html><meta charset=utf-8>
<title>YABAI_RESTORE_%s</title>
<style>html{background:#fff}@media(prefers-color-scheme:dark){html{background:#202124}}</style>
<script>setTimeout(()=>location.replace('chrome://newtab/'),45000)</script>
""" % token)
    path.chmod(0o600)
    return path


def launch(source, readiness=None):
    parsed = key(source)
    if not parsed: raise ValueError('Origen Chrome inválido')
    if not CHROME.is_file(): raise ValueError('No se encontró Google Chrome')
    if not YABAI.is_file(): raise ValueError('No se encontró yabai')
    token = parsed[1]
    directory = last_profile()
    marker = marker_page(token)
    subprocess.Popen([str(CHROME), '--profile-directory=' + directory,
                      '--new-window', '--no-first-run', '--disable-session-crashed-bubble',
                      marker.as_uri()], stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     start_new_session=True)
    deadline = time.monotonic() + WINDOW_SECONDS
    while time.monotonic() < deadline:
        for window in chrome_windows():
            found = MARKER.search(window.get('title',''))
            if found and found.group(1) == token:
                remember(window, source_for(token, directory))
                marker.unlink(missing_ok=True)
                return {'window':window['id'], 'profile_directory':directory}
        time.sleep(min(.25, max(0, deadline-time.monotonic())))
    raise RuntimeError('Chrome no mostró la ventana vacía a tiempo')
