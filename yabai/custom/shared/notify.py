#!/opt/homebrew/bin/python3
"""Native, best-effort notifications for custom yabai wrappers. No window actions."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys


def records(output):
    decoder = json.JSONDecoder()
    found = []
    for marker in re.finditer(r'^\{', output, re.M):
        try:
            value, _ = decoder.raw_decode(output[marker.start():])
            if isinstance(value, dict):
                found.append(value)
        except ValueError:
            pass
    return found


def message(action, event, output=''):
    starts = {
        'save': 'Guardando posiciones, tamaños y zoom de las ventanas…',
        'restore': 'Restaurando el layout de las ventanas abiertas…',
        'restore-open': 'Abriendo apps faltantes y preparando la restauración…',
        'restart': 'Guardando la distribución antes de reiniciar yabai…',
        'recover': 'Restaurando la distribución guardada de yabai…',
        'capture': 'Guardando un punto de recuperación…',
        'preview': 'Comprobando qué ventanas se pueden restaurar…',
    }
    if event == 'test':
        return 'yabai · Prueba de avisos', 'Los avisos están configurados. Esta prueba no modifica ventanas ni reinicia yabai.'
    if event == 'start':
        return 'yabai · En curso', starts.get(action, 'Procesando…')
    if event == 'error':
        errors = [line.removeprefix('ERROR:').strip() for line in output.splitlines() if line.startswith('ERROR:')]
        reason = errors[-1] if errors else 'La operación no se completó.'
        return 'yabai · Error', reason[:190] + ' Revisa run.log antes de reintentar.'
    objects = records(output)
    warnings = [w for obj in objects for w in obj.get('warnings', [])]
    report = next((obj for obj in reversed(objects) if 'restore' in obj and 'skipped' in obj), None)
    if report is not None:
        n, skipped = len(report['restore']), len(report['skipped'])
        if action == 'preview':
            return 'yabai · Previsualización', f'{n} ventanas listas; {skipped} escritorios se omitirían. No se movieron ventanas.'
        title = 'yabai · Restaurado con avisos' if skipped or warnings else 'yabai · Layout restaurado'
        body = f'{n} ventanas restauradas; {skipped} escritorios omitidos.'
        if warnings:
            body += f' {len(warnings)} aviso(s) al abrir apps.'
        if skipped or warnings:
            body += ' Detalles en run.log.'
        return title, body
    if action == 'save':
        summary = next((obj for obj in objects if 'saved' in obj), {})
        body = f"{summary.get('windows', '?')} ventanas en {summary.get('spaces', '?')} escritorios."
        if 'reopenable' in summary:
            body += f" {summary['reopenable']} con proyecto/carpeta para reabrir."
        if warnings: body += ' Algunas rutas no se identificaron; revisa run.log.'
        return ('yabai · Guardado con avisos' if warnings else 'yabai · Layout guardado'), body
    if action == 'restart':
        return 'yabai · Reinicio completado', 'Servicio reiniciado y distribución de ventanas restaurada y verificada.'
    if action == 'recover':
        return 'yabai · Distribución restaurada', 'Restauración y verificación completadas.'
    return 'yabai · Completado', 'La operación terminó correctamente.'


def deliver(title, body):
    # Pass text as argv, never interpolate it into AppleScript source.
    script = 'on run argv\n display notification (item 2 of argv) with title (item 1 of argv)\nend run'
    return subprocess.run(['/usr/bin/osascript', '-e', script, title, body],
                          capture_output=True, text=True, timeout=8)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action')
    p.add_argument('event', choices=['start', 'success', 'error', 'test'])
    p.add_argument('output', nargs='?', type=Path)
    args = p.parse_args()
    output = args.output.read_text(errors='replace') if args.output else ''
    title, body = message(args.action, args.event, output)
    result = deliver(title, body)
    if result.returncode:
        print('AVISO: no se pudo enviar la notificación: '+result.stderr.strip(), file=sys.stderr)
        return 1
    print('NOTIFY enviado: '+args.action+' / '+args.event, flush=True)
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, subprocess.TimeoutExpired) as exc:
        print('AVISO: notificación no enviada: '+str(exc), file=sys.stderr)
        sys.exit(1)
