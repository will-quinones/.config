"""Chrome sources via the opt-in local extension. No activation or tab scraping."""
import importlib.util
from pathlib import Path
import re
import subprocess
import time

BUNDLE = 'com.google.Chrome'
NATIVE = Path(__file__).resolve().parents[2] / 'chrome/native/bridge.py'
spec = importlib.util.spec_from_file_location('chrome_local_bridge', NATIVE)
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)
TOKEN = re.compile(r'[a-f0-9]{32}')


def key(source):
    if not isinstance(source, dict) or source.get('kind') != 'chrome-window': return None
    if not all(isinstance(source.get(k), str) and TOKEN.fullmatch(source[k]) for k in ('profile','token')):
        return None
    return 'chrome-window', source['profile'] + ':' + source['token']


def title(value):
    # Chrome's native AX title adds application/profile decorations.
    return re.split(r" [–—-] Google Chrome(?: [–—-] |$)", (value or '').strip(), maxsplit=1)[0]


def title_matches(native, snapshot):
    native, plain = title(native), title(snapshot.get('title'))
    if not plain: return False
    variants = {plain, plain + ': Error de red'}
    for group in snapshot.get('source', {}).get('groups', []):
        label = group.get('title')
        if label:
            decorated = plain + ': Parte del grupo ' + label
            variants.update((decorated, decorated + ': Error de red'))
    return native in variants


def pair(windows, snapshots):
    # Bidirectional uniqueness; never infer ordering from changed native IDs.
    candidates = {}
    for w in windows:
        matches = [s for s in snapshots if not s.get('unsupported') and title_matches(w.get('title'), s)]
        if len(matches) > 1:
            frame = w.get('frame', {})
            matches = [s for s in matches if all(isinstance(frame.get(k), (int,float)) and
                       isinstance(s.get('frame',{}).get(k), (int,float)) and
                       abs(frame[k]-s['frame'][k]) <= 6 for k in ('x','y','w','h'))]
        if len(matches) == 1 and not matches[0].get('incomplete'):
            candidates[w['id']] = matches[0]['source']
    return {wid:source for wid,source in candidates.items()
            if sum(key(other)==key(source) for other in candidates.values()) == 1}


def snapshot_probe(profile, hints, timeout=15):
    try:
        return bridge.request(profile, {'action':'snapshot', 'hints':hints}, timeout=timeout)
    except RuntimeError as exc:
        # The host returns its response timeout as a structured error.
        if str(exc) == 'Chrome no respondió; no se reintentó la apertura':
            raise TimeoutError(str(exc)) from exc
        raise


def identify(windows, hints=()):
    chrome = [w for w in windows if w.get('bundle_id') == BUNDLE or w.get('app') in ('Chrome','Google Chrome')]
    if not chrome: return {}
    snapshots=[]
    connected=0
    for profile in bridge.profiles():
        try:
            response = snapshot_probe(profile, [h for h in hints if key(h) and h['profile']==profile])
            connected += 1
            snapshots.extend(response)
        except (OSError, EOFError): continue  # Old socket or browser not yet ready.
    if not connected:
        raise RuntimeError('Chrome: extensión local no conectada; no se guardarán/reabrirán grupos. Actívala en el perfil correcto.')
    result = pair(chrome, snapshots)
    # Missing/ambiguous windows get their own save warning; no destructive fallback.
    config_path = NATIVE.parent.parent / 'profiles.json'
    import json
    mapping = json.loads(config_path.read_text()) if config_path.exists() else {}
    for source in result.values():
        directory = mapping.get(source['profile'])
        if isinstance(directory, str) and re.fullmatch(r'Default|Profile [0-9]+', directory):
            source['profile_directory'] = directory
    return result


# The native host reconnect alarm can take up to one minute after startup.
READ_TIMEOUT = 15
READY_SECONDS = 75


def await_profile(source):
    """Only read-only probes may be retried; never retry a restore mutation."""
    profile = source['profile']
    try:
        snapshot_probe(profile, [source], timeout=READ_TIMEOUT)
        return
    except (OSError, EOFError):
        pass
    directory = source.get('profile_directory')
    if not isinstance(directory, str) or not re.fullmatch(r'Default|Profile [0-9]+', directory):
        raise RuntimeError('Falta el perfil Chrome guardado; abre el perfil correcto y guarda el layout')
    subprocess.Popen(['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
                      '--profile-directory=' + directory, '--no-startup-window'],
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True)
    deadline = time.monotonic() + READY_SECONDS
    while time.monotonic() < deadline:
        try:
            snapshot_probe(profile, [source],
                           timeout=min(READ_TIMEOUT, max(.1, deadline-time.monotonic())))
            return
        except (OSError, EOFError):
            time.sleep(min(.5, max(0, deadline-time.monotonic())))
    raise RuntimeError('El puente Chrome no se conectó tras 75 s; revisa la extensión en ' + directory)


def launch(source, readiness=None):
    if not key(source): raise ValueError('Origen Chrome inválido')
    profile = source['profile']
    if readiness is not None and isinstance(readiness.get(profile), Exception):
        raise RuntimeError('Perfil omitido tras un fallo previo: ' + str(readiness[profile]))
    try:
        if readiness is None or profile not in readiness:
            await_profile(source)
            if readiness is not None: readiness[profile] = True
        # Never retry this mutation, including after an uncertain timeout.
        return bridge.request(profile, {'action':'restore','source':source}, timeout=35)
    except (OSError, EOFError, RuntimeError) as exc:
        if readiness is not None: readiness[profile] = exc
        raise
