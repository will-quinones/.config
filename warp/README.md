# Presets de Warp versionados

Los siete presets activos viven en este repositorio. Warp los lee mediante un enlace simbólico; no hay dos copias que sincronizar.

- Fuente: `/Users/williamquinones/.config/warp/tab_configs`
- Enlace usado por Warp: `/Users/williamquinones/.warp/tab_configs`

## Uso

Abrir el menú + de Warp y elegir el preset. Editar un preset desde Warp modifica el archivo versionado. Las rutas de proyectos son específicas de esta Mac; ajustarlas al instalar en otro equipo.

## Restaurar el enlace en otra instalación

Conservar primero cualquier carpeta existente de presets. Si la ruta del enlace está libre:

```sh
ln -s "$HOME/.config/warp/tab_configs" "$HOME/.warp/tab_configs"
```

No sobrescribir una carpeta existente. Para deshacer la integración, retirar únicamente el enlace simbólico y copiar los presets de vuelta a la ruta de Warp.

## Seguimiento

El .gitignore local general ignora archivos nuevos: añadir explícitamente nuevos presets con `git add -f -- warp/tab_configs/nombre.toml` desde el repositorio. Los siete existentes ya tienen seguimiento. No incluir tokens en comandos.

Verificado: contenido de los siete TOML idéntico antes/después y enlace resuelto correctamente. No se abrieron pestañas ni se ejecutaron servicios durante la migración; comprobar el menú + de Warp.
