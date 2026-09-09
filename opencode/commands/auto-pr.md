---
description: "Ejecuta mediante el subagente coordinador el flujo de status:approved y fusion a develop con CI verde sobre repositorios suministrados por el agente principal."
agent: build
model: openai/gpt-5.6-luna-fast
variant: low
---

Actúa como agente principal delegador. Usa el contexto de esta conversación y tu historial de herramientas para identificar las rutas o identificadores exactos de todos los repositorios que acabas de trabajar; no detectes repositorios mediante escaneo, no preguntes cuáles se trabajaron y no uses el cwd como sustituto. No ejecutes mutaciones Git, GitHub o Jira directamente. Invoca una sola vez al subagente global `auto-pr-coordinator` mediante `task`, pasando explícitamente esas rutas/identificadores y ordenándole cargar y ejecutar la skill `auto-pr-develop`. El coordinador puede trabajar con repositorios fuera del directorio desde donde se abrió OpenCode, debe auditar cada repositorio suministrado y omitir cualquiera sin trabajo real. Si no puedes establecer el alcance exacto desde el contexto, detente sin mutaciones y reporta que falta el alcance. Instrucciones adicionales: $ARGUMENTS
