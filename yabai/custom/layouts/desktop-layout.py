#!/opt/homebrew/bin/python3
"""Save and restore named yabai layouts across login/reboot.
restore uses open windows only; restore-open also launches missing apps.
No service restart, Space creation, or native fullscreen support.
Uses bundle ID + title digest (never historical window IDs) for conservative matching.
"""
import argparse
import copy
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from contextlib import ExitStack
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import adapters
ENGINE = ROOT.parent / 'restart' / 'restart_preserving.py'
spec = importlib.util.spec_from_file_location('layout_engine', ENGINE)
e = importlib.util.module_from_spec(spec)
spec.loader.exec_module(e)
DATA = Path.home() / '.local/state/yabai-desktop-layout'
CONFIG = ROOT / 'desktop-layout.json'
ERROR = e.RestoreError


# Read-only WindowServer IDs distinguish closed Chrome entries cached by yabai.
WINDOW_IDENTITIES = DATA / 'bin/window-identities'
raw_engine_windows = e.windows


def is_chrome(w):
    return w.get('bundle_id') == 'com.google.Chrome' or w.get('app') in ('Chrome', 'Google Chrome')


def is_chrome_picker(w):
    return is_chrome(w) and w.get('title') in ("¿Quién usa Chrome?", "Who's using Chrome?")


def filter_closed_chrome(windows, pairs):
    return {i:w for i,w in windows.items() if not is_chrome(w) or (i,w['pid']) in pairs}


def verified_windows():
    windows = raw_engine_windows()
    if not any(is_chrome(w) for w in windows.values()): return windows
    proc = subprocess.run([str(WINDOW_IDENTITIES)], capture_output=True, text=True, timeout=5)
    if proc.returncode: raise ERROR('No se pudo comprobar qué ventanas Chrome siguen abiertas.')
    pairs = {tuple(x) for x in json.loads(proc.stdout)}
    if not pairs: raise ERROR('macOS devolvió una lista de ventanas vacía; no se descartan ventanas a ciegas.')
    return filter_closed_chrome(windows, pairs)


e.windows = verified_windows


def prepare_chrome_picker():
    # Exact native picker titles only; real Chrome pages have an application/profile suffix.
    for w in e.windows().values():
        if is_chrome_picker(w) and not w.get('is-floating'):
            e.set_float(w['id'], True)


def digest(title):
    return hashlib.sha256((title or '').encode()).hexdigest()


def is_auxiliary(w):
    # DBeaver reports this startup dialog as AXStandardWindow/root-window.
    return (w.get('app') == 'DBeaver Community' and
            w.get('title', '').strip() in ('Tip of the day', 'Consejo del día'))


def eligible(w):
    return (not is_auxiliary(w) and not is_chrome_picker(w) and w.get('subrole') == 'AXStandardWindow'
            and w.get('has-ax-reference', True) and w.get('root-window', True)
            and not any(w.get(k) for k in ('is-minimized', 'is-hidden',
                        'is-native-fullscreen', 'is-sticky', 'scratchpad')))


def focus_state(spaces, ws):
    return dict(visible_spaces=[s['index'] for s in spaces if s.get('is-visible')],
                focused_space=next((s['index'] for s in spaces if s.get('has-focus')), None),
                focus=next((w['id'] for w in ws if w.get('has-focus')), None))


def select_spaces(value, spaces):
    available = {s['index'] for s in spaces if not s.get('is-native-fullscreen')}
    if value == 'all':
        return sorted(available)
    if value == 'current':
        result = [s['index'] for s in spaces if s.get('has-focus')]
    elif isinstance(value, list):
        result = value
    else:
        result = [int(x.strip()) for x in value.split(',')]
    if not result or any(type(i) is not int or i not in available for i in result):
        raise ERROR('Escritorio inexistente o pantalla completa nativa: ' + str(result))
    return sorted(set(result))


def settings(spaces):
    keys = ('top_padding', 'bottom_padding', 'left_padding', 'right_padding', 'window_gap')
    return {str(s['index']): {k: e.cmd('-m', 'config', '--space', s['index'], k)
                             for k in keys} for s in spaces}


def running_apps():
    script = 'ObjC.import("AppKit"); var a=$.NSWorkspace.sharedWorkspace.runningApplications; var out=[]; for(var i=0;i<a.count;i++){var x=a.objectAtIndex(i); out.push({pid:Number(x.processIdentifier),bundle_id:ObjC.unwrap(x.bundleIdentifier)});} JSON.stringify(out);'
    result = subprocess.run(['/usr/bin/osascript', '-l', 'JavaScript', '-e', script],
                            capture_output=True, text=True, timeout=15)
    if result.returncode:
        raise ERROR('No se pudieron consultar los identificadores de aplicaciones.')
    return {x['pid']: x.get('bundle_id') for x in json.loads(result.stdout)}


def same_app(saved, live):
    # Prefer stable bundle IDs; legacy snapshots can still use the display name.
    if saved.get('bundle_id') and live.get('bundle_id'):
        return saved['bundle_id'] == live['bundle_id']
    return saved['app'] == live['app']


def with_bundles(windows):
    try:
        bundles = running_apps()
    except (ERROR, OSError, ValueError, subprocess.TimeoutExpired):
        bundles = {}
    return [{**w, 'bundle_id': bundles.get(w['pid']) or w.get('bundle_id')} for w in windows]


def open_missing_apps(document, current, config, wait_seconds, wait_ready=True):
    if document.get('format') != 1:
        raise ERROR('Formato de layout incompatible.')
    saved = document['state']['windows']
    missing = sorted({w['app'] for w in saved
                      if not any(same_app(w, now) for now in current)})
    launched = []
    warnings = []
    # No shell interpolation, no -n (duplicate process), no -F (discard app state).
    for app in missing:
        if any(is_chrome(w) for w in saved if w['app'] == app):
            warnings.append(app + ': apertura genérica desactivada; usa el adaptador del perfil guardado')
            continue
        bundles = {w.get('bundle_id') for w in saved if w['app'] == app and w.get('bundle_id')}
        override = config.get('app_bundle_ids', {}).get(app)
        if len(bundles) > 1 and not override:
            warnings.append(app + ': varios identificadores de aplicación; no se abre por ambigüedad')
            continue
        bundle = override or next(iter(bundles), None)
        if bundle and (not isinstance(bundle, str) or not re.fullmatch(r'[A-Za-z0-9_.-]+', bundle)):
            warnings.append(app + ': identificador inválido')
            continue
        command = ['/usr/bin/open', '-g', '-b', bundle] if bundle else ['/usr/bin/open', '-g', '-a', app]
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=15)
            if result.returncode:
                warnings.append(app + ': no se pudo abrir: ' + result.stderr.strip())
            else:
                launched.append(app)
        except (OSError, subprocess.TimeoutExpired) as exc:
            warnings.append(app + ': ' + str(exc))
    if launched and wait_ready:
        deadline = time.monotonic() + wait_seconds
        previous = None
        stable = 0
        while time.monotonic() < deadline:
            live, _ = adapters.annotate(with_bundles(list(e.windows().values())))
            matches, _ = match(saved, live)
            signature = tuple(sorted((w['id'], w['pid'], w['app'], digest(w.get('title')))
                                     for w in live if eligible(w) and any(same_app(old, w) for old in saved if old['app'] in launched)))
            stable = stable + 1 if signature == previous else 0
            previous = signature
            needed = [w for w in saved if w['app'] in launched]
            if all(w['id'] in matches for w in needed) and stable >= 2:
                break
            time.sleep(min(.5, max(0, deadline - time.monotonic())))
        else:
            warnings.append('Terminó la espera: algunas ventanas no aparecieron o no se pudieron identificar. '
                            'Abre los documentos/ventanas pendientes y usa restore.')
    return dict(opened=launched, warnings=warnings)


def capture(selected):
    # Filter before tree inference. Keep title digests from fresh visible-Space queries.
    original_windows = e.windows
    initial_focus = focus_state(e.query('spaces'), list(original_windows().values()))
    observed = {}
    def filtered():
        ws = {i: w for i, w in original_windows().items() if eligible(w)}
        observed.update(ws)
        return ws
    e.windows = filtered
    try:
        state = e.capture(only_spaces=selected)
    finally:
        e.windows = original_windows
        e.restore_focus(initial_focus)
    state['spaces'] = [s for s in state['spaces'] if s['index'] in selected]
    state['windows'] = [w for w in state['windows'] if w['space'] in selected]
    if not state['windows']:
        raise ERROR('No hay ventanas normales para guardar; se conserva el layout anterior.')
    try:
        bundles = running_apps()
    except (ERROR, OSError, ValueError, subprocess.TimeoutExpired):
        bundles = {}
        print('AVISO: sin identificadores de app; restore-open intentará abrir por nombre.', file=sys.stderr)
    described, source_warnings = adapters.annotate([{**w, 'bundle_id': bundles.get(w['pid'])} for w in observed.values()])
    descriptors = {w['id']: w.get('reopen') for w in described}
    for w in state['windows']:
        if descriptors.get(w['id']): w['reopen'] = descriptors[w['id']]
        elif bundles.get(w['pid']) in ('com.microsoft.VSCode', 'com.google.Chrome'):
            source_warnings.append(w['app'] + ': no se identificó un origen único para reabrir esta ventana')
        w['bundle_id'] = bundles.get(w['pid'])
        w['title_digest'] = digest(observed[w['id']].get('title'))
        if w['kind'] == 'free' and not w['is-floating']:
            raise ERROR('Ventana no gestionada/no flotante: ' + w['app'])
    occupied = {w['space'] for w in state['windows']}
    state['spaces'] = [s for s in state['spaces'] if s['index'] in occupied]
    return dict(format=1, state=state, displays=e.query('displays'),
                settings=settings(state['spaces']), source_warnings=source_warnings)


def match(saved, current):
    """Stable app identity, unique titles; never pair indistinguishable windows by order."""
    result = {}
    reasons = {}
    groups = {}
    for w in saved:
        key = ('bundle', w['bundle_id']) if w.get('bundle_id') else ('name', w['app'])
        groups.setdefault(key, []).append(w)
    for all_old in groups.values():
        all_new = [w for w in current if same_app(all_old[0], w) and eligible(w)]
        for w in [x for x in all_old if x.get('reopen')]:
            source = adapters.key(w['reopen'])
            peers = [x for x in all_old if adapters.key(x.get('reopen')) == source]
            candidates = [x for x in all_new if source and adapters.key(x.get('reopen')) == source]
            if len(peers) == len(candidates) == 1:
                result[w['id']] = candidates[0]
            else:
                reasons[w['id']] = w['app'] + ': origen de ventana ausente, excluido o ambiguo'
        old = [w for w in all_old if not w.get('reopen')]
        if not old: continue
        used = {w['id'] for w in result.values()}
        new = [w for w in all_new if w['id'] not in used]
        if len(old) == len(new) == 1:
            result[old[0]['id']] = new[0]
            continue
        for w in old:
            peers = [x for x in old if x['title_digest'] == w['title_digest']]
            candidates = [x for x in new if digest(x.get('title')) == w['title_digest']]
            if len(peers) == len(candidates) == 1:
                result[w['id']] = candidates[0]
            else:
                excluded = [x for x in current if same_app(w, x) and not eligible(x)]
                detail = ': ventana excluida (scratchpad, oculta o minimizada)' if excluded and not new else (
                    ': no hay ventanas abiertas compatibles' if not new else
                    f': {len(old)} guardadas, {len(new)} abiertas; título ausente o ambiguo')
                reasons[w['id']] = w['app'] + detail
    # Mixed legacy/new identities must never assign one live window twice.
    for wid, live in list(result.items()):
        if sum(x['id'] == live['id'] for x in result.values()) > 1:
            ids = [i for i, x in result.items() if x['id'] == live['id']]
            for i in ids:
                reasons[i] = live['app'] + ': identidad de ventana duplicada'
                del result[i]
    return result, reasons


def plan(document, current, spaces, displays, current_settings=None):
    if document.get('format') != 1:
        raise ERROR('Formato de layout incompatible.')
    original = document['state']
    targets = {s['index']: s for s in spaces}
    old_displays = {d['index']: d for d in document['displays']}
    new_displays = {d['index']: d for d in displays}
    matches, reasons = match(original['windows'], current)
    selected = []
    skipped = []
    for s in original['spaces']:
        index = s['index']
        ws = [w for w in original['windows'] if w['space'] == index]
        reason = None
        now = targets.get(index)
        if not now or now.get('is-native-fullscreen'):
            reason = 'el escritorio no existe o es fullscreen nativo'
        elif s['display'] not in old_displays or now['display'] not in new_displays:
            reason = 'pantalla no disponible'
        else:
            a, b = old_displays[s['display']], new_displays[now['display']]
            if a['uuid'] != b['uuid'] or not e.near(a['frame'], b['frame']):
                reason = 'cambió la pantalla, su posición o resolución'
        missing = [reasons[w['id']] for w in ws if w['id'] not in matches]
        if not reason and missing:
            reason = '; '.join(sorted(set(missing)))
        if not reason and current_settings is not None:
            if document['settings'].get(str(index)) != current_settings.get(str(index)):
                reason = 'cambiaron márgenes/separación; no se modifica tu configuración'
        if reason:
            skipped.append(dict(space=index, reason=reason))
        else:
            selected.append(s)
    # Fixed point: a window in a skipped space cannot be assumed to move away.
    while True:
        chosen = {s['index'] for s in selected}
        moving = {matches[w['id']]['id'] for w in original['windows']
                  if w['space'] in chosen}
        blocked = []
        for s in selected:
            extras = [w['app'] for w in current if w['space'] == s['index']
                      and w['id'] not in moving and e.managed(w, targets[s['index']])]
            if extras:
                blocked.append(s['index'])
                skipped.append(dict(space=s['index'], reason='otras ventanas en mosaico: '+', '.join(extras)))
        if not blocked:
            break
        selected = [s for s in selected if s['index'] not in blocked]
    state = copy.deepcopy(original)
    state['spaces'] = copy.deepcopy(selected)
    chosen = {s['index'] for s in selected}
    state['windows'] = [w for w in state['windows'] if w['space'] in chosen]
    for w in state['windows']:
        live = matches[w['id']]
        w.update(id=live['id'], pid=live['pid'], app=live['app'], display=targets[w['space']]['display'])
    for s in state['spaces']:
        now = targets[s['index']]
        for k in ('id', 'uuid', 'display'):
            s[k] = now[k]
        for group in e.leaves(s['tree']):
            group['ids'] = [matches[i]['id'] for i in group['ids']]
    state['display_ids'] = [d['uuid'] for d in displays]
    state.update(focus_state(spaces, current))
    report = dict(restore=[dict(app=w['app'], window=w['id'], space=w['space'],
                               zoom=bool(w['has-fullscreen-zoom'] or w['has-parent-zoom']))
                           for w in state['windows']], skipped=skipped)
    return state, report


def inventory(include_chrome=True):
    # Metadata only: never activate Spaces here. Geometry is refreshed by
    # the capture/restore engine while it visits and verifies each Space.
    spaces = e.query('spaces')
    allowed = {s['index'] for s in spaces if not s.get('is-native-fullscreen')}
    current = [dict(w) for w in e.windows().values() if w['space'] in allowed]
    described, warnings = adapters.annotate(with_bundles(current), include_chrome=include_chrome)
    if warnings: print(json.dumps({'warnings': warnings}, ensure_ascii=False), flush=True)
    return described, spaces, e.query('displays')


def reopen_windows(document, current, wait_seconds, wait_ready=True):
    saved = document['state']['windows']
    if wait_ready: adapters.set_hints(saved)
    opened = []
    warnings = []
    sources = {}
    chrome_ready = {}
    for w in saved:
        source = adapters.key(w.get('reopen'))
        if source: sources.setdefault(source, []).append(w)
    for source, slots in sources.items():
        app = slots[0]['app']
        if len(slots) != 1:
            warnings.append(app + ': varias ventanas guardadas del mismo proyecto/carpeta; no se duplican')
            continue
        # An excluded scratchpad/hidden window must not be duplicated to bypass its rules.
        if any(same_app(slots[0], w) and adapters.key(w.get('reopen')) == source for w in current):
            continue
        # Chrome verifies existing content through its profile-specific API, not stale AX titles.
        if source[0] != 'chrome-window' and any(same_app(slots[0], w) and eligible(w) and not w.get('reopen') for w in current):
            warnings.append(app + ': hay ventanas sin ruta identificable; no se abren duplicados a ciegas')
            continue
        try:
            adapters.launch(slots[0]['reopen'], chrome_ready=chrome_ready)
            opened.append(app + ': ' + source[1])
        except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
            warnings.append(app + ': ' + str(exc))
    if opened and wait_ready:
        deadline = time.monotonic() + wait_seconds
        previous = None
        stable = 0
        while time.monotonic() < deadline:
            current, _ = adapters.annotate(with_bundles(list(e.windows().values())))
            matches, _ = match(saved, current)
            signature = tuple(sorted((w['id'], w['pid'], str(adapters.key(w.get('reopen')))) for w in current if w.get('reopen')))
            stable = stable + 1 if signature == previous else 0
            previous = signature
            if all(w['id'] in matches for w in saved if w.get('reopen')) and stable >= 2: break
            time.sleep(min(.5, max(0, deadline-time.monotonic())))
        else:
            warnings.append('Algunos orígenes no produjeron una ventana identificable a tiempo.')
    return dict(reopened_windows=opened, warnings=warnings)


def progress(message, started):
    # The shell wrapper buffers stdout until exit; write progress immediately.
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] +{time.monotonic()-started:.1f}s {message}"
    with open(DATA / 'run.log', 'a') as log:
        log.write(line + '\n')


def run_open_jobs(jobs, limit, report):
    results = []
    started = time.monotonic()
    def run(label, operation):
        began = time.monotonic()
        return operation(), time.monotonic()-began
    with ThreadPoolExecutor(max_workers=limit) as pool:
        pending = {pool.submit(run, label, operation):label for label,operation in jobs}
        while pending:
            finished, _ = wait(pending, timeout=5, return_when=FIRST_COMPLETED)
            if not finished:
                report('Esperando aperturas: ' + ', '.join(sorted(set(pending.values()))), started)
            for task in finished:
                label = pending.pop(task)
                try:
                    result, elapsed = task.result()
                except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
                    result, elapsed = {'warnings':[label + ': ' + str(exc)]}, None
                results.append(result)
                suffix = f' ({elapsed:.1f}s)' if elapsed is not None else ' (error)'
                report('Terminó apertura: ' + label + suffix, started)
    return results


def open_parallel(document, current, config, wait_seconds):
    """Concurrent app starts; a single serial job owns each Chrome profile."""
    limit = config.get('launch_concurrency', 3)
    if type(limit) is not int or not 1 <= limit <= 3:
        raise ERROR('launch_concurrency debe ser un entero entre 1 y 3.')
    saved = document['state']['windows']
    adapters.set_hints(saved)  # Immutable during worker execution.
    jobs = []
    missing = sorted({w['app'] for w in saved if not w.get('reopen') and not is_chrome(w)
                      and not any(same_app(w, other) and other.get('reopen') for other in saved)
                      and not any(same_app(w, now) for now in current)})
    for app in missing:
        subset = {**document, 'state':{**document['state'], 'windows':[w for w in saved if w['app']==app]}}
        jobs.append((app, lambda doc=subset: open_missing_apps(doc, current, config, wait_seconds, wait_ready=False)))
    groups = {}
    for w in saved:
        source = adapters.key(w.get('reopen'))
        if source:
            group = ('Chrome', w['reopen']['profile']) if source[0]=='chrome-window' else ('Code', w['app'])
            groups.setdefault(group, []).append(w)
    for group, windows in groups.items():
        subset = {**document, 'state':{**document['state'], 'windows':windows}}
        jobs.append((group[0], lambda doc=subset: reopen_windows(doc, current, wait_seconds, wait_ready=False)))
    started = time.monotonic()
    progress(f'Abriendo apps (máximo {limit} tareas simultáneas)', started)
    results = run_open_jobs(jobs, limit, progress)
    warnings = [message for result in results for message in result.get('warnings', [])]
    # One shared stabilization pass, not one deadline per app or window.
    deadline = time.monotonic() + wait_seconds
    previous = None
    stable = 0
    described = current
    last_progress = -float('inf')
    while time.monotonic() < deadline:
        described, notes = adapters.annotate(with_bundles(list(e.windows().values())))
        matches, _ = match(saved, described)
        signature = tuple(sorted((w['id'], w['pid'], digest(w.get('title'))) for w in described if eligible(w)))
        stable = stable + 1 if signature == previous else 0
        previous = signature
        if all(w['id'] in matches for w in saved) and stable >= 2:
            break
        if time.monotonic()-last_progress >= 5:
            progress(f'Identificando ventanas: {len(matches)}/{len(saved)}', started)
            last_progress = time.monotonic()
        time.sleep(min(1, max(0, deadline-time.monotonic())))
    else:
        warnings.append('Terminó la espera compartida: faltan ventanas identificables; consulta los escritorios omitidos.')
    progress('Aperturas terminadas; preparando posiciones y tamaños', started)
    return dict(opened=[app for result in results for app in result.get('opened', [])],
                reopened_windows=[app for result in results for app in result.get('reopened_windows', [])],
                warnings=warnings)


def create_recovery():
    # This raw journal requires no BSP inference and is explicitly NOT an engine checkpoint.
    current, spaces, displays = inventory()
    raw = dict(format='diagnostic-positions-v1', created=time.time(),
               note='Posiciones de diagnóstico; no garantiza reconstrucción del árbol BSP anterior.',
               windows=[{k: v for k, v in w.items() if k != 'title'} for w in current],
               spaces=spaces, displays=displays)
    e.save(raw, DATA / 'before-restore-positions.json')
    try:
        recovery = e.capture()
    except ERROR as exc:
        # Only geometric inference failures permit this documented fallback.
        geometry_errors = ('BSP geometry cannot be reconstructed safely.',
                           'Overlapping non-stack windows; cannot safely infer the BSP tree.',
                           'Stack layout reports inconsistent frames.')
        if str(exc) not in geometry_errors:
            raise
        e.save(dict(format='diagnostic-only', reason=str(exc),
                    positions_file=str(DATA / 'before-restore-positions.json')),
               DATA / 'before-restore.json')
        # Expected fallback: details stay in the recovery file, not user warnings.
        return
    recovery['phase'] = 'before-layout-restore'
    e.save(recovery, DATA / 'before-restore.json')


def execute_restore(state, document, report):
    started = time.monotonic()
    progress('Preparando respaldo y verificando destinos', started)
    if not state['windows']:
        raise ERROR('No hay escritorios completos y seguros que restaurar. Consulta preview.')
    # Recovery snapshot is separate from the named layout, which is never overwritten here.
    create_recovery()
    current, current_spaces, current_displays = inventory()
    expected = {w['id']: w for w in state['windows']}
    for w in current:
        if w['id'] in expected:
            target = expected[w['id']]
            if w['pid'] != target['pid'] or not same_app(target, w) or not eligible(w):
                raise ERROR('Cambió una ventana durante la preparación; vuelve a previsualizar.')
    if not set(expected).issubset({w['id'] for w in current}):
        raise ERROR('Una ventana desapareció durante la preparación.')
    # Recheck destinations before the first movement, after taking the recovery snapshot.
    available = {s['index'] for s in current_spaces}
    relevant = [s for s in document['state']['spaces'] if s['index'] in available]
    _, fresh_report = plan(document, current, current_spaces, current_displays,
                           settings(relevant))
    if fresh_report != report:
        raise ERROR('Cambió el plan durante la captura de seguridad; vuelve a intentarlo.')
    e.validate_identity(state)
    mouse = e.cmd('-m', 'config', 'mouse_follows_focus')
    e.cmd('-m', 'config', 'mouse_follows_focus', 'off')
    try:
        # First float ALL matched windows, then move, so circular Space swaps are safe.
        for w in state['windows']:
            e.zoom_to(w['id'], {**w, 'has-fullscreen-zoom': False, 'has-parent-zoom': False})
            e.set_float(w['id'], True)
        for w in state['windows']:
            if e.windows()[w['id']]['space'] != w['space']:
                e.win(w['id'], '--space', w['space'])
        progress('Restaurando posiciones, tamaños y zoom', started)
        e.restore(state, verify_result=True)
        progress('Posiciones, tamaños y zoom verificados', started)
    finally:
        e.restore_focus(state)
        e.cmd('-m', 'config', 'mouse_follows_focus', mouse)


def main():
    os.umask(0o077)
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['save', 'preview', 'restore', 'restore-open'])
    p.add_argument('--name', help='Nombre del layout; predeterminado en desktop-layout.json')
    p.add_argument('--spaces', help='Al guardar: all, current o índices separados por coma')
    p.add_argument('--wait', type=int, help='restore-open: espera por ventanas en segundos (1–300)')
    args = p.parse_args()
    config = json.loads(CONFIG.read_text()) if CONFIG.exists() else {}
    name = args.name or config.get('name', 'default')
    wait_seconds = args.wait if args.wait is not None else config.get('launch_wait_seconds', 30)
    if type(wait_seconds) is not int or not 1 <= wait_seconds <= 300:
        raise ERROR('La espera debe ser un entero entre 1 y 300 segundos.')
    if args.wait is not None and args.action != 'restore-open':
        raise ERROR('--wait solo corresponde a restore-open.')
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', name):
        raise ERROR('Nombre inválido: usa letras, números, guion o guion bajo.')
    DATA.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = DATA / (name + '.json')
    with ExitStack() as stack:
        # Share the existing restart lock so shortcuts cannot overlap operations.
        for lockpath in (DATA / 'operation.lock', e.DEFAULT_STATE.with_suffix('.lock')):
            lockpath.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            lock = stack.enter_context(open(lockpath, 'a'))
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise ERROR('Ya hay otra operación de yabai en curso.')
        if args.action == 'save':
            selected = select_spaces(args.spaces or config.get('spaces', 'all'), e.query('spaces'))
            document = capture(selected)
            if path.exists():
                e.save(json.loads(path.read_text()), DATA / (name + '.previous.json'))
            e.save(document, path)
            print(json.dumps(dict(saved=str(path), reopenable=sum(bool(w.get('reopen')) for w in document['state']['windows']), warnings=document.get('source_warnings', []), **e.summary(document['state'])), indent=2))
        else:
            if args.spaces:
                raise ERROR('--spaces se usa solo con save; restore usa el layout guardado.')
            if not path.exists():
                raise ERROR('No existe el layout '+name+'. Ejecuta save primero.')
            document = json.loads(path.read_text())
            adapters.set_hints(document['state']['windows'])
            if args.action in ('restore', 'restore-open'): prepare_chrome_picker()
            current, spaces, displays = inventory(include_chrome=args.action != 'restore-open')
            if args.action == 'restore-open':
                opened = open_parallel(document, current, config, wait_seconds)
                print(json.dumps(opened, ensure_ascii=False), flush=True)
                current, spaces, displays = inventory()
            available = {s['index'] for s in spaces}
            relevant = [s for s in document['state']['spaces'] if s['index'] in available]
            state, report = plan(document, current, spaces, displays, settings(relevant))
            print(json.dumps(report, indent=2, ensure_ascii=False), flush=True)
            if args.action in ('restore', 'restore-open'):
                execute_restore(state, document, report)
                print('Restauradas '+str(len(state['windows']))+' ventanas; omitidos '+str(len(report['skipped']))+' escritorios.')
            else:
                print('Previsualización: no se movieron ni redimensionaron ventanas.')


if __name__ == '__main__':
    try:
        main()
    except (ERROR, OSError, ValueError, KeyError, subprocess.TimeoutExpired) as exc:
        print('ERROR: '+str(exc), file=sys.stderr)
        sys.exit(1)
