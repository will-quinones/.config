# Restaurar ventanas y grupos de Chrome

Activa esta extensión **en el perfil Trabajo** y vuelve a guardar el layout una vez. Después usarás los mismos atajos; no hay botones nuevos para guardar o restaurar.

## Activación — una sola vez

1. En Chrome abre `chrome://extensions` y activa **Modo de desarrollador**.
2. Pulsa **Cargar descomprimida** y selecciona:
   `/Users/williamquinones/.config/yabai/custom/chrome/extension`
3. Busca **Yabai · ventanas y grupos** en el menú Extensiones. Pulsa su icono: debe mostrar **OK**. Puedes fijarlo para verlo.
4. Coloca tus ventanas donde quieras y guarda con **Ctrl izquierdo + Option izquierdo + Command izquierdo + G**.

No cambies el perfil donde la activaste. Si usas varios perfiles, actívala en cada uno: sus datos se distinguen y no se mezclan.

## Atajos existentes

| Acción | Atajo |
|---|---|
| Guardar distribución y fuentes Chrome/Code | Ctrl + Option + Command + G |
| Restaurar solo ventanas abiertas | Ctrl + Option + Command + L |
| Abrir ventanas faltantes y restaurar | Ctrl + Option + Command + **Shift derecho** + L |
| Reiniciar yabai preservando distribución | Ctrl + Option + Command + R |

Ctrl, Option y Command son los modificadores izquierdos de la configuración actual. La extensión no cambia los atajos ni el reinicio de yabai.

## Qué conserva y qué no

- Por ventana: URLs en orden, pestañas fijadas, pestaña activa, grupos con nombre/color y estado contraído. Yabai guarda escritorio, tamaño, posición y zoom/stack.
- Chrome y Code tienen reapertura específica. Las otras apps conservan el comportamiento anterior de colocación/apertura genérica. Finder no tiene adaptador específico activo.
- Solo ventanas normales, no incógnito. URLs HTTP/HTTPS, nueva pestaña y `about:blank`. Ventanas con otras URLs quedan sin fuente de reapertura y se advierte al guardar.
- No conserva historial atrás/adelante, formularios sin enviar, descargas, sesión de autenticación, metadatos de grupos compartidos/sincronizados ni vistas divididas de Chrome. Las páginas dependerán de las cookies existentes.
- Si Chrome ya reabrió una ventana con las mismas pestañas/grupos, se reutiliza. Si solo coincide parcialmente, se omite para no duplicar trabajo. Dos ventanas indistinguibles no se asignan al azar.
- Si Chrome está cerrado, se inicia el perfil guardado con `--no-startup-window`: no se crea una ventana vacía antes de restaurar. Si falta el identificador del perfil, se pide abrir Trabajo y guardar nuevamente, sin abrir un perfil al azar.
- No se cierran ventanas existentes. Una apertura fallida puede dejar **una ventana nueva incompleta**: revísala antes de reintentar. No se informa como apertura completa ni se repite a ciegas.

## Menos cambios de foco

Las consultas de inventario y la creación de pestañas no piden foco. El respaldo geométrico y la restauración final de yabai todavía recorren escritorios para comprobar posiciones. Chrome/macOS puede hacer visible una ventana al iniciar la aplicación; no se promete cero animaciones.

## Privacidad y conexión

No hay servidor HTTP, depuración remota, scripts inyectados ni permiso para leer el contenido de páginas. Permisos: `tabs` (URLs/títulos), `tabGroups`, `storage` (identidad local del perfil), `nativeMessaging` y `alarms` (reconexión).

El puente usa un socket Unix privado del usuario en `/tmp/yabai-chrome-<uid>/`. Solo admite consultar ventanas y reconstruir una fuente Chrome; no ejecuta comandos de shell ni acepta rutas de archivos desde Chrome. Chrome solo permite conectarse a esta extensión por su ID.

Las URLs y nombres de grupos quedan **en texto legible** dentro de los layouts de:
`/Users/williamquinones/.local/state/yabai-desktop-layout/`
Los archivos nuevos tienen permisos solo para tu usuario. No se envían a servicios externos por la extensión. Al restaurar, Chrome naturalmente visita las URLs guardadas.

## Diagnóstico sin mover ventanas

```sh
/opt/homebrew/bin/python3 /Users/williamquinones/.config/yabai/custom/chrome/doctor.py
```

Muestra conexión y cantidades, no URLs. Si no hay conexión, pulsa el icono de la extensión; comprueba que esté activada en Trabajo. No necesitas reiniciar yabai.

## Archivos y reversión

- `extension/`: extensión que se carga en Chrome; no mover después de activarla.
- `native/`: conexión local. Chrome la inicia y la termina al desconectarse.
- `doctor.py`: diagnóstico.
- `../layouts/adapters/chrome.py`: empareja ventanas Chrome con ventanas yabai sin enfocar.
- Registro del puente: `~/Library/Application Support/Google/Chrome/NativeMessagingHosts/local.yabai.chrome_layout.json`.

Para desactivar la integración, desactiva la extensión en Chrome. Los demás adaptadores seguirán funcionando; las ventanas Chrome con fuente guardada se omitirán si no pueden identificarse. La copia fechada `custom/backups/chrome-integration-*` contiene los dos archivos anteriores del layout para una reversión completa; no revierte la mejora de inventario sin foco.

## Referencias oficiales

- [Grupos de pestañas](https://developer.chrome.com/docs/extensions/reference/api/tabGroups)
- [Pestañas](https://developer.chrome.com/docs/extensions/reference/api/tabs)
- [Mensajería nativa](https://developer.chrome.com/docs/extensions/develop/concepts/native-messaging)

## Selector de perfiles y referencias antiguas

Chrome no usa la apertura genérica de respaldo. El selector nativo «¿Quién usa Chrome?» se excluye del layout y pasa a flotante durante restore/restore-open, sin cerrarlo ni cambiar tu perfil predeterminado. Las páginas reales de Chrome conservan las guardas.

Un lector local de WindowServer comprueba pares ID/PID y descarta solo referencias Chrome que ya no existen. No consulta títulos ni toma capturas. Fuente: `/Users/williamquinones/.config/yabai/custom/shared/window-identities.swift`; ejecutable generado fuera de Git: `/Users/williamquinones/.local/state/yabai-desktop-layout/bin/window-identities`. Si falta o falla, se aborta de forma segura. Para reconstruirlo en otra Mac con las herramientas de desarrollo:

```sh
mkdir -p "$HOME/.local/state/yabai-desktop-layout/bin"
swiftc "$HOME/.config/yabai/custom/shared/window-identities.swift" -o "$HOME/.local/state/yabai-desktop-layout/bin/window-identities"
```
