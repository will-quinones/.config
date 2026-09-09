# Herdr: atajos en Warp

Karabiner traduce Fn a combinaciones directas Ctrl+Alt que recibe Herdr.

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
