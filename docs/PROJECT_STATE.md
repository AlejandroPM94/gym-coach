# Estado del proyecto

Actualizado: 2026-08-05

## Funcionalidades terminadas

- Esqueleto Python 3.12 gestionado con uv.
- API FastAPI mínima con `GET /health`.
- Configuración tipada mediante entorno y `.env`.
- Cliente Hevy async exclusivamente de lectura con paginación, timeouts, errores sanitizados,
  validación Pydantic y conservación raw fuera de Git.
- CLI para comprobar Hevy y descargar usuario, rutinas, entrenamientos y plantillas.
- Base SQLAlchemy y Alembic preparadas, todavía sin tablas de dominio.

## Integraciones verificadas

- Hevy real: autenticación, usuario, 4 rutinas, 50 entrenamientos recientes y 451 plantillas de
  ejercicios verificados el 2026-08-05.
- Contrato real de `/v1/user/info`: sobre `data` con `id`, `name` y `url`.
- Docker Desktop y Compose verificados sin `sudo`; PostgreSQL 17 está en ejecución y `healthy`.
  El acceso al socket requiere ejecutar fuera del sandbox del agente.

## Pruebas existentes

- Salud FastAPI autocontenida sin base de datos ni API key.
- Cliente Hevy: usuario realista, opcionales/nulos, extras, paginación, HTTP, JSON inválido,
  esquema inválido, diagnósticos sanitizados, timeout y no exposición de credenciales.
- CLI: regresiones de `hevy check` y `hevy user` con HTTP simulado.
- Almacenamiento de respuestas raw.

## Problemas conocidos

- El sandbox del agente bloquea el socket Docker; las comprobaciones requieren permiso escalado.
- La API pública de Hevy se declara inestable y requiere mantener fixtures y esquemas observados.
- Los JSON raw contienen datos personales y no son fuente de verdad ni backup.

## Último hito completado

Corrección y validación real del primer hito: contrato de usuario, diagnóstico seguro, esquemas raw
y cobertura de regresión. El segundo hito no se ha iniciado.
