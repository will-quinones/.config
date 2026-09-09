#!/opt/homebrew/bin/python3
"""Save and restore named yabai layouts across login/reboot.
restore uses open windows only; restore-open also launches missing apps.
No service restart, Space creation, or native fullscreen support.
Uses app + title digest (never historical window IDs) for conservative matching.
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

ROOT = Path(__file__).resolve().parent
ENGINE = ROOT / 'restart_preserving.py'
# Allows running staged tests without copying/changing the installed engine.
if not ENGINE.exists():
    ENGINE = Path.home() / '.config/yabai/custom/restart_preserving.py'
spec = importlib.util.spec_from_file_location('layout_engine', ENGINE)
e = importlib.util.module_from_spec(spec)
spec.loader.exec_module(e)
DATA = Path.home() / '.local/state/yabai-desktop-layout'
CONFIG = ROOT / 'desktop-layout.json'
ERROR = e.RestoreError


def digest(title):
    return hashlib.sha256((title or '').encode()).hexdigest()


def eligible(w):
    return (w.get('subrole') == 'AXStandardWindow'
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


def open_missing_apps(document, current, config, wait_seconds):
    if document.get('format') != 1:
        raise ERROR('Formato de layout incompatible.')
    saved = document['state']['windows']
    present = {w['app'] for w in current if eligible(w)}
    missing = sorted({w['app'] for w in saved} - present)
    launched = []
    warnings = []
    # No shell interpolation, no -n (duplicate process), no -F (discard app state).
    for app in missing:
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
    if launched:
        deadline = time.monotonic() + wait_seconds
        previous = None
        stable = 0
        while time.monotonic() < deadline:
            live = list(e.windows().values())
            matches, _ = match(saved, live)
            signature = tuple(sorted((w['id'], w['pid'], w['app'], digest(w.get('title')))
                                     for w in live if eligible(w) and w['app'] in launched))
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
    for w in state['windows']:
        w['bundle_id'] = bundles.get(w['pid'])
        w['title_digest'] = digest(observed[w['id']].get('title'))
        if w['kind'] == 'free' and not w['is-floating']:
            raise ERROR('Ventana no gestionada/no flotante: ' + w['app'])
    occupied = {w['space'] for w in state['windows']}
    state['spaces'] = [s for s in state['spaces'] if s['index'] in occupied]
    return dict(format=1, state=state, displays=e.query('displays'),
                settings=settings(state['spaces']))


def match(saved, current):
    """Only unique title pairs, or a single saved/current window for the entire app."""
    result = {}
    reasons = {}
    for app in sorted({w['app'] for w in saved}):
        old = [w for w in saved if w['app'] == app]
        new = [w for w in current if w['app'] == app and eligible(w)]
        if len(old) == len(new) == 1:
            result[old[0]['id']] = new[0]
            continue
        for w in old:
            peers = [x for x in old if x['title_digest'] == w['title_digest']]
            candidates = [x for x in new if digest(x.get('title')) == w['title_digest']]
            if len(peers) == len(candidates) == 1:
                result[w['id']] = candidates[0]
            else:
                reasons[w['id']] = app + (': no está abierta' if not new else ': título ausente o ambiguo')
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
        w.update(id=live['id'], pid=live['pid'], display=targets[w['space']]['display'])
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


def inventory():
    spaces = e.query('spaces')
    initial = focus_state(spaces, list(e.windows().values()))
    result = {}
    mouse = e.cmd('-m', 'config', 'mouse_follows_focus')
    e.cmd('-m', 'config', 'mouse_follows_focus', 'off')
    try:
        for s in spaces:
            if s.get('is-native-fullscreen') or not s['windows']:
                continue
            e.show_space(s['index'])
            result.update({i: w for i, w in e.windows().items() if w['space'] == s['index']})
    finally:
        e.restore_focus(initial)
        e.cmd('-m', 'config', 'mouse_follows_focus', mouse)
    # Preserve original focus, not the last Space visited.
    for w in result.values():
        w['has-focus'] = w['id'] == initial['focus']
    return list(result.values()), spaces, e.query('displays')


def execute_restore(state, document, report):
    if not state['windows']:
        raise ERROR('No hay escritorios completos y seguros que restaurar. Consulta preview.')
    # Recovery snapshot is separate from the named layout, which is never overwritten here.
    recovery = e.capture()
    recovery['phase'] = 'before-layout-restore'
    e.save(recovery, DATA / 'before-restore.json')
    current, current_spaces, current_displays = inventory()
    expected = {w['id']: w for w in state['windows']}
    for w in current:
        if w['id'] in expected:
            target = expected[w['id']]
            if w['pid'] != target['pid'] or w['app'] != target['app'] or not eligible(w):
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
        e.restore(state, verify_result=True)
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
            print(json.dumps(dict(saved=str(path), **e.summary(document['state'])), indent=2))
        else:
            if args.spaces:
                raise ERROR('--spaces se usa solo con save; restore usa el layout guardado.')
            if not path.exists():
                raise ERROR('No existe el layout '+name+'. Ejecuta save primero.')
            document = json.loads(path.read_text())
            current, spaces, displays = inventory()
            if args.action == 'restore-open':
                opened = open_missing_apps(document, current, config, wait_seconds)
                print(json.dumps(opened, indent=2, ensure_ascii=False), flush=True)
                if opened['opened']:
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
