# Herdr: atajos en Warp

Karabiner traduce Fn a combinaciones directas Option+Shift (sin prefijo) que recibe Herdr.

| Atajo | Acción |
|---|---|
| Fn + I / O | Pestaña anterior / siguiente de Herdr |
| Fn + U / P | Workspace anterior / siguiente de Herdr |
| Fn + N | Último panel enfocado, incluso en otro workspace |
| Fn + Cmd izquierdo + I / O | Pestaña anterior / siguiente de Warp |

## Aplicar cambios

- Herdr: Ctrl+B, soltar, luego Shift+R para recargar la configuración.
- Karabiner: regenerar con `goku` después de editar el EDN.
- Las reglas se limitan a Warp, no detectan si la pestaña contiene Herdr.
- Los atajos originales de pestañas Ctrl+B → P/N se conservan.

## Archivos

- `/Users/williamquinones/.config/herdr/config.toml`: configuración nativa.
- `/Users/williamquinones/.config/karabiner.edn`: fuente de los remapeos.
- `/Users/williamquinones/.config/karabiner/karabiner.json`: salida generada ya versionada en este repositorio.

Se validaron TOML y las siete reglas JSON generadas; la prueba interactiva queda pendiente de confirmación del usuario. No versionar sesiones, logs, sockets ni credenciales.

## Transporte de teclas

Fn+I/O/U/N envía Option izquierdo+Shift izquierdo+I/O/U/N. Fn+P envía Option izquierdo+Shift izquierdo+Y para siguiente workspace. Herdr usa alt+shift en los cinco atajos. Sin Ctrl, prefijo ni teclas F. Fn+Cmd izquierdo+I/O mantiene las pestañas de Warp.

Warp debe tener Option izquierdo como Meta activado (terminal.input.extra_meta_keys.left_alt = true). El usuario confirmó que I/O/U/N funcionan. La combinación directa Option+Shift+P no produce acción; se prueba Y como alternativa interna sin cambiar Fn+P. Causa exacta y prueba de Y pendientes de confirmar.
