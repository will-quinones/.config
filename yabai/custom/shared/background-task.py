#!/opt/homebrew/bin/python3
"""Detach long custom yabai tasks from Karabiner's cancellable shell commands."""
import argparse
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
TASKS = {
    'restart': ('../restart/restart-preserving.sh', {'restart', 'restore', 'capture', 'inspect'}),
    'layout': ('../layouts/desktop-layout.sh', {'save', 'restore', 'restore-open', 'preview'}),
}


def spawn(script, arguments, log):
    log.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with log.open('ab') as output:
        return subprocess.Popen(['/bin/sh', str(script), *arguments],
                                stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT,
                                start_new_session=True, close_fds=True)


def main():
    os.umask(0o077)
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('task', choices=TASKS)
    p.add_argument('action')
    args = p.parse_args()
    script, actions = TASKS[args.task]
    if args.action not in actions:
        p.error('Acción inválida para esta tarea')
    log = Path.home() / '.local/state/yabai-custom/background.log'
    child = spawn(ROOT / script, [args.action], log)
    print('Tarea iniciada:', child.pid)


if __name__ == '__main__':
    try:
        main()
    except OSError as exc:
        print('No se pudo iniciar la tarea: '+str(exc), file=sys.stderr)
        sys.exit(1)
