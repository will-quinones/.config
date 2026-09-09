"""Per-window reopen descriptors; no arbitrary shell commands."""
from pathlib import Path
from . import vscode, chrome
MODULES = (vscode, chrome)
HINTS = []

def key(source):
    if chrome.key(source): return chrome.key(source)
    if not isinstance(source, dict) or source.get('kind') not in ('code-folder','code-workspace'):
        return None
    path = source.get('path')
    if not isinstance(path, str) or not Path(path).is_absolute(): return None
    return source['kind'], str(Path(path).resolve())


def set_hints(saved):
    HINTS[:] = [w['reopen'] for w in saved if key(w.get('reopen'))]


def annotate(windows, include_chrome=True):
    result = [dict(w) for w in windows]
    warnings = []
    descriptors = {}
    for module in MODULES:
        if module is chrome and not include_chrome: continue
        try: descriptors.update(module.identify(result, HINTS))
        except (OSError, ValueError, RuntimeError, __import__('subprocess').TimeoutExpired) as exc:
            warnings.append(str(exc))
    for w in result:
        if w['id'] in descriptors: w['reopen'] = descriptors[w['id']]
    return result, warnings


def launch(source, chrome_ready=None):
    k = key(source)
    if not k: raise ValueError('Origen de ventana inválido')
    if k[0] == 'chrome-window': return chrome.launch(source, readiness=chrome_ready)
    normalized = dict(kind=k[0], path=k[1])
    if k[0].startswith('code-'): return vscode.launch(normalized)
    raise ValueError('Origen no admitido')
