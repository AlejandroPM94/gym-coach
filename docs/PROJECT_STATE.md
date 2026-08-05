# Estado del proyecto

Actualizado: 2026-08-05

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

## Integraciones verificadas

- Hevy real: autenticación, usuario, 4 rutinas, 50 entrenamientos recientes y 451 plantillas de
  ejercicios verificados el 2026-08-05.
- Contrato real de `/v1/user/info`: sobre `data` con `id`, `name` y `url`.
- Docker Desktop y Compose verificados sin `sudo`; PostgreSQL 17 está en ejecución y `healthy`.
  El acceso al socket requiere ejecutar fuera del sandbox del agente.
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

## Problemas conocidos

- El sandbox del agente bloquea el socket Docker; las comprobaciones requieren permiso escalado.
- La API pública de Hevy se declara inestable y requiere mantener fixtures y esquemas observados.
- Los JSON raw contienen datos personales y no son fuente de verdad ni backup.
- El objetivo semanal de adherencia es configuración de consulta, no un plan persistido todavía.
- e1RM y volumen excluyen por diseño peso corporal, asistencia, distancia y duración hasta disponer
  de masa corporal o reglas específicas fiables.
- El agente no mantiene aún historial conversacional ni aplica propuestas aprobadas en Hevy.
- La primera ejecución real con OpenAI queda pendiente de que el usuario configure su clave local.

## Último hito completado

Cuarto hito completado: entrenador PydanticAI con contexto mínimo, evidencias obligatorias y
propuestas aprobables localmente, validado sin llamadas reales ni cálculos deportivos del LLM.
