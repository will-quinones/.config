# Layouts de escritorio con yabai

`desktop-layout.py` guarda y restaura ventanas, Spaces, tamaños, stacks y zoom. El atajo `restore-open` también abre las aplicaciones faltantes.

## Chrome sin extensión

Chrome no necesita una extensión ni un puente nativo. Durante cada restauración:

1. Se lee `profile.last_used` desde `~/Library/Application Support/Google/Chrome/Local State`.
2. Cada ventana guardada se lanza como una tarea independiente con `--new-window` y ese perfil.
3. Una página local vacía recibe temporalmente un título único para asociar la ventana con su entrada del layout.
4. Al aparecer en yabai se guarda el par PID/ID en `~/.local/state/yabai-desktop-layout/chrome-window-map.json`.
5. La página se reemplaza automáticamente por `about:blank`; no se abren URLs, grupos ni pestañas guardadas.

Los layouts creados con la extensión anterior siguen funcionando: se reutiliza su token de ventana y se ignora el UUID antiguo del perfil. No hace falta guardar nuevamente.

Si Chrome ya tiene ventanas abiertas que no pertenecen al layout, `restore-open` no crea otras a ciegas. Esto evita duplicados o asignaciones incorrectas.

## Concurrencia

`launch_concurrency` indica el máximo de aperturas de ventanas activas y acepta valores de 1 a 3. Code y Chrome producen una tarea independiente por ventana; por eso hasta tres ventanas pueden abrirse a la vez. Docker conserva una tarea coordinada con las aplicaciones dependientes de su Space para no abrir DBeaver antes de que el motor esté listo.

```json
{
  "launch_concurrency": 3
}
```

El registro muestra cada ventana con su escritorio, por ejemplo `Code · escritorio 1` o `Google Chrome · escritorio 10`.

## Pruebas

Desde `~/.config/yabai/custom`:

```sh
python3 -m unittest discover -s layouts -p 'test*.py'
```

Las pruebas no abren ni mueven ventanas.
