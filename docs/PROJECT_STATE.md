# Estado del proyecto

Actualizado: 2026-08-06

## Funcionalidades terminadas

- Esqueleto Python 3.12 gestionado con uv.
- API FastAPI mínima con `GET /health`.
- Configuración tipada mediante entorno y `.env`.
- Cliente Hevy async exclusivamente de lectura con paginación, timeouts, errores sanitizados,
  validación Pydantic y conservación raw fuera de Git.
- CLI para comprobar Hevy y descargar usuario, rutinas, entrenamientos y plantillas.
- Modelo SQLAlchemy/PostgreSQL normalizado para usuario, plantillas, rutinas, entrenamientos,
  ejercicios y series, con dos migraciones reversibles.
- Sincronización Hevy por instantánea completa, idempotente por hash, con borrados lógicos,
  restauración, reintentos transitorios y trazabilidad en `sync_runs`.
- Motor deportivo determinista para volumen, repeticiones, e1RM Epley, evolución, adherencia y
  estancamiento, expuesto mediante CLI y FastAPI.
- Entrenador PydanticAI con perfil, objetivos, revisión contextual, propuestas estructuradas y
  aprobación/rechazo local sin escritura en Hevy.
- Selección tipada de proveedor del entrenador: Ollama local por defecto y OpenAI opcional.
- Servidor MCP local `stdio` con ocho herramientas read-only, instrucciones breves para clientes y
  contratos Pydantic públicos desacoplados de Hevy y SQLAlchemy.
- Artefactos manuales para Hermes: configuración MCP sin secretos y skill de entrenador; Hermes no
  se ha instalado ni se ha modificado `~/.hermes/`.
- PydanticAI movido a un extra experimental; la gestión de perfil, objetivos y decisiones no
  requiere el runtime de agente.

## Integraciones verificadas

- Hevy real: autenticación, usuario, 4 rutinas, 50 entrenamientos recientes y 451 plantillas de
  ejercicios verificados el 2026-08-05.
- Contrato real de `/v1/user/info`: sobre `data` con `id`, `name` y `url`.
- Docker Desktop y Compose se verificaron sin `sudo`; PostgreSQL 17 llegó a estado `healthy` y sus
  pruebas de integración pasaron. Al final de la sesión, Docker Desktop dejó de estar integrado con
  esta distribución WSL y debe reactivarse antes de la prueba manual con Hermes.
- Ollama 0.32.3 se verificó `healthy`, detectó la RTX 3070 y conservó `gpt-oss:20b` (13 GB) en un
  volumen Docker. PydanticAI obtuvo una salida estructurada real; una consulta en caliente tardó
  14,83 s antes de desaparecer la integración WSL de Docker Desktop.
- MCP v2 verificado por transporte `stdio` real fuera del sandbox: inicio, listado de ocho
  herramientas, llamada sin credenciales y cierre correcto.
- Sincronización real: 1 usuario, 451 plantillas, 4 rutinas y 95 entrenamientos; una segunda
  ejecución produjo 551 elementos sin cambios y ninguna inserción, actualización o eliminación.

## Pruebas existentes

- Salud FastAPI autocontenida sin base de datos ni API key.
- Cliente Hevy: usuario realista, opcionales/nulos, extras, paginación, HTTP, JSON inválido,
  esquema inválido, diagnósticos sanitizados, timeout y no exposición de credenciales.
- CLI: regresiones de `hevy check` y `hevy user` con HTTP simulado.
- Almacenamiento de respuestas raw.
- Migraciones upgrade/downgrade y sincronización PostgreSQL: inserción, repetición idempotente,
  borrado trazado, restauración y actualización de hijos.
- Métricas: dominios válidos y nulos, redondeo, separación de plantillas, ventanas, adherencia,
  progreso/estancamiento y lectura PostgreSQL/API.
- Agente: contratos estrictos, salida simulada sin red, esquema inválido, evidencia desconocida,
  rangos de repeticiones y ciclo PostgreSQL de perfil, objetivo, borrador y aprobación.
- MCP: registro de herramientas, validación, límites, búsqueda, recursos inexistentes, errores
  sanitizados, ausencia de secretos, contratos públicos y ciclo `stdio` opt-in.

## Problemas conocidos

- El sandbox del agente bloquea el socket Docker; las comprobaciones requieren permiso escalado.
- La integración WSL de Docker Desktop desapareció durante la última verificación; `docker version`
  pide reactivarla. No se modificaron permisos ni configuración global automáticamente.
- El sandbox también bloquea el transporte MCP entre subprocesos; la prueba `stdio` debe ejecutarse
  fuera de él con `GYM_COACH_RUN_MCP_STDIO_TESTS=1`.
- La API pública de Hevy se declara inestable y requiere mantener fixtures y esquemas observados.
- Los JSON raw contienen datos personales y no son fuente de verdad ni backup.
- El objetivo semanal de adherencia es configuración de consulta, no un plan persistido todavía.
- e1RM y volumen excluyen por diseño peso corporal, asistencia, distancia y duración hasta disponer
  de masa corporal o reglas específicas fiables.
- El agente no mantiene aún historial conversacional ni aplica propuestas aprobadas en Hevy.
- La clave OpenAI configurada es válida, pero la cuenta no tiene saldo de API; la suscripción a
  ChatGPT no aporta créditos a la API. La alternativa local evita esa dependencia.
- `gpt-oss:20b` se reparte aproximadamente 42% GPU y 58% CPU en este equipo. La primera carga tardó
  unos 82 s; Ollama lo mantiene residente 10 minutos y la inferencia en caliente es mucho más rápida.

## Último hito completado

Sexto hito completado: Hermes definido como orquestador inicial y servidor MCP read-only validado
por `stdio`, manteniendo PostgreSQL como fuente de verdad y PydanticAI como extra experimental.
