# Verificación de esta integración

Unidades de cambio (sin commits automáticos):
1. Extensión/puente local + pruebas de protocolo y comportamiento.
2. Adaptador de layout + pruebas de emparejamiento, junto con esta guía de activación.

Pruebas realizadas antes de instalar:
- Layout: `python3 -m unittest discover -q` desde el directorio layouts de preparación: 57 pruebas.
- Transporte: `python3 -m unittest discover -s tests -v` desde chrome: 5 pruebas, incluida comunicación real entre proceso nativo y socket privado, con Chrome simulado.
- Modelo: `node tests/test_model.mjs`: validación de grupos, URLs y perfiles.
- Extensión: `node tests/test_worker.mjs`: Chrome simulado, apertura con `focused:false`, grupos, pestañas fijadas, reutilización, prevención de duplicados, recuperación tras cambio de IDs.

Verificación antes del commit (2026-09-09):
- `PYTHONDONTWRITEBYTECODE=1 /opt/homebrew/bin/python3 -m unittest discover -s tests -v` desde chrome: 9 pruebas correctas, incluido proceso nativo/socket y arranque por perfil.
- `node tests/test_model.mjs`: 11 comprobaciones correctas.
- `node tests/test_worker.mjs`: flujo simulado correcto.
- Extensión activada en Chrome; ensayo previo de restore-open desde Chrome cerrado restauró 9 ventanas sin escritorios omitidos. El usuario confirmó posteriormente que funciona.
- No se reinició macOS ni se cerraron ventanas para verificar este commit. La reanudación tras un reinicio real no queda probada por los tests simulados.

Reversión: copia fechada de `layouts/desktop-layout.py` y `layouts/adapters/__init__.py`; desactivar extensión y retirar registro nativo. No modificar el layout guardado ni las reglas de yabai.
