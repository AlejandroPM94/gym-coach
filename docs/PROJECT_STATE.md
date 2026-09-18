# Estado del proyecto

Actualizado: 2026-09-18

## Seguimiento conjunto y Samsung Health mediante Drive

- Skill Hermes 0.9.0 y MCP con 41 herramientas: objetivos nutricionales calculados y versionados,
  cierre de días, revisión semanal e informe post-entrenamiento estructurado.
- Rutinas Hevy versionadas de forma inmutable. Cada sesión se enlaza solo a una prescripción cuya
  vigencia pueda probarse por fecha; el resto declara fallback a la rutina actual.
- Progreso determinista por modalidad: e1RM, carga externa, menor asistencia, repeticiones,
  distancia o duración; RPE agregado y récords que requieren historial previo.
- Recuperación frente a línea base personal de 21 días, excluyendo días parciales; señales de sueño,
  pulso en reposo y HRV aportan contexto sin diagnosticar ni cambiar el plan automáticamente.
- Comparación de planes con series directas y estímulo secundario heurístico de 0,5 por serie.
- Catálogo nutricional buscable por barcode, raciones de etiqueta y objetivo de fibra parametrizado.
- Último peso disponible independiente de mediciones de cintura; edad no forzada a 18 años.
- Revisión con dieta, objetivos por fecha, entrenamiento, medidas manuales, pesajes openScale,
  check-ins y actividad Samsung.
- Migraciones `d83a1b50a201`, `e94b2c61b302`, `f47c3d92a105`, `ab914ec42f10` y
  `c31e6c1124ab`: seguimiento auditado, salud normalizada y prescripciones versionadas.
- Exportación diaria nativa de Health Connect hacia una carpeta privada de Google Drive; el backend
  solo realiza conexiones salientes y PostgreSQL conserva los datos normalizados.
- Importador de ZIP/SQLite con límites de tamaño, CRC, integridad y esquema v26. Filtra Samsung para
  pasos, fases de sueño, ejercicio, distancia, energía, pulso, HRV, oxígeno y VO2 máx.; openScale
  aporta peso y composición BIA. Procesa 30 días y separa ausente de cero.
- Cliente Drive de solo lectura mediante cuenta de servicio y carpeta exacta; valida tamaño y MD5,
  evita revisiones repetidas y no expone credenciales ni métricas en la salida operativa.
- Cuenta de servicio sin roles de proyecto y carpeta dedicada compartida como lectora. La primera
  descarga importó 29 días; la ampliación releyó la revisión actual una vez e importó 30 días.
- CLI `gym-coach automation sync-health-drive` y timer systemd horario activos. La ejecución real
  mediante systemd terminó con `Result=success` y dejó programada la siguiente comprobación.
- El receptor LAN, certificados y APK propios se retiraron; no se abre ningún puerto en el equipo.
- El ZIP real ampliado produjo 30 días: 27 con pasos, 24 con fases de sueño, 19 con ejercicio,
  30 con pulso y 24 con oxígeno. La revisión se reimportó tras aplicar la migración.
- Alembic está en `c31e6c1124ab`. La sincronización real posterior dejó 565 registros sin cambios,
  capturó 8 versiones actuales y enlazará sesiones futuras; no atribuyó esas versiones a los 94
  entrenamientos previos porque sus fechas no lo permiten.
- Verificación final: 114 tests, incluidos PostgreSQL y MCP stdio; Ruff, Mypy, lock y diff limpios.
  Hermes se reinició, descubre 41 herramientas y el informe conjunto respondió correctamente con
  el entrenamiento real más reciente sin exponer sus datos.
- Los crons activos usan ya los contratos nuevos: post-entrenamiento cada cinco minutos y revisión
  semanal el lunes a las 09:00 sobre la semana cerrada. PostgreSQL quedó saludable y publicado solo
  en `127.0.0.1:5432`; Ollama, si se activa, también queda limitado a loopback.
- Activación y límites en `docs/HEALTH_CONNECT.md`; matriz conversacional pendiente en
  `docs/COACHING_ACCEPTANCE.md`.
- El ZIP de Drive del 18 de septiembre contenía dos pesajes openScale con paquete
  `com.health.openscale.sync.oss`; el filtro anterior solo admitía el paquete sin `.oss`.
  Se aceptan ambas variantes y la revisión se reimportó: PostgreSQL contiene los pesajes
  del 16 y 17 de septiembre, junto con los 30 días de actividad.

## Hito nutricional

- Catálogo personal de productos por 100 g/ml, recetas reutilizables, preview, diario fechado y
  anulaciones auditadas; en aquel hito se alcanzaron 34 herramientas MCP.
- Composiciones con procedencia confirmada, estimaciones explícitas y fibra desconocida nullable.
- Totales Decimal calculados en Python; UUID idempotentes y composición histórica inmutable.
- Migración `b62d8a04e391`, skill Hermes 0.7.0 y guía `docs/NUTRITION.md`.
- Verificación: 91 tests pasan, incluidos PostgreSQL y MCP stdio; Ruff y Mypy limpios.
  Migración aplicada a la base local, Alembic sin deriva y lock verificado.
- En aquel hito, gateway y conexión Hermes→MCP se verificaron con 34 herramientas; la versión actual
  aparece en la sección superior.
- Pendiente validar etiqueta/comida real por Telegram. El backend no tiene OCR ni catálogo externo.

## Funcionalidades terminadas

- Esqueleto Python 3.12 gestionado con uv.
- API FastAPI mínima con `GET /health`.
- Configuración tipada mediante entorno y `.env`.
- Cliente Hevy async con lecturas paginadas y creación/actualización de rutinas aislada, timeouts,
  errores sanitizados, validación Pydantic y conservación raw fuera de Git.
- CLI para comprobar Hevy y descargar usuario, rutinas, entrenamientos y plantillas.
- Modelo SQLAlchemy/PostgreSQL normalizado para usuario, plantillas, rutinas, entrenamientos,
  ejercicios y series, con migraciones Alembic reversibles.
- Sincronización Hevy por instantánea completa, idempotente por hash, con borrados lógicos,
  restauración, reintentos transitorios y trazabilidad en `sync_runs`.
- Motor deportivo determinista para volumen, repeticiones, e1RM Epley, evolución, adherencia y
  estancamiento, expuesto mediante CLI y FastAPI.
- Entrenador PydanticAI con perfil, objetivos, revisión contextual, propuestas estructuradas y
  aprobación/rechazo local sin escritura en Hevy.
- Selección tipada de proveedor del entrenador: Ollama local por defecto y OpenAI opcional.
- Servidor MCP local `stdio` con 27 herramientas y contratos públicos desacoplados de Hevy/ORM.
- Onboarding conversacional respaldado por PostgreSQL: estado de campos pendientes, perfil con
  instantáneas versionadas y objetivos que pueden añadirse o revisarse con confirmación explícita.
- Métricas deterministas de resumen y progreso por ejercicio disponibles para Hermes, con IDs de
  evidencia estables para justificar propuestas.
- Borradores locales de planes solicitados por el atleta, consulta, comparación determinista y
  decisión confirmada; ninguna operación aplica cambios en Hevy.
- Revisión explícita de limitaciones y preferencias: una lista vacía ya no se confunde con un campo
  que nunca se preguntó.
- Planes con sesiones opcionales, ubicación, duración estimada y series prescritas por una única
  dimensión: repeticiones, segundos o distancia; las series pueden incluir `weight_kg` cuando la
  carga está respaldada por evidencia verificada.
- Evidencias verificadas nuevamente al guardar cada propuesta y justificaciones por cambio.
- Diff determinista de ejercicios retenidos/añadidos/eliminados, frecuencias, series y estímulo
  muscular directo e indirecto.
- Hermes 0.20.0 instalado y configurado manualmente por el usuario; la conexión MCP, la skill y una
  consulta real de entrenamiento se verificaron de extremo a extremo.
- PydanticAI movido a un extra experimental; la gestión de perfil, objetivos y decisiones no
  requiere el runtime de agente.
- Detector incremental de entrenamientos nuevos con cursor, solapamiento, cola idempotente y
  reclamaciones recuperables almacenados en PostgreSQL.
- Gate de cron para Hermes: sondeo cada cinco minutos sin modelo cuando no hay cambios y revisión
  contextual mediante MCP cuando aparece un entrenamiento nuevo.
- Entrevista intensiva versionada para antropometría voluntaria, actividad, sueño, estrés,
  alimentación, salud y preferencias; mediciones y check-ins quedan fechados y confirmados.
- Evaluación determinista del historial con profundidad, confianza y límites. No confunde registros
  con técnica ni obliga a autodeclarar nivel cuando existe evidencia suficiente.
- Cálculos Python de IMC, Mifflin-St Jeor y proteína, con reglas trazables de ACSM, OMS, ISSN y AESAN.
- Aplicación de rutinas Hevy con aprobación inicial derivada de la petición explícita, preview ligado
  a hashes, token de un solo uso y una confirmación final visible. Los timeouts no se reintentan y
  quedan pendientes de reconciliación.
- Contrato de escritura corregido: `folder_id: null` explícito en POST, respuesta bajo `routine` o
  directa, códigos HTTP sanitizados y respuestas 2xx inválidas clasificadas como inciertas.
- Recuperación segura de creaciones tras respuestas 2xx no interpretables mediante instantáneas
  anterior/posterior y coincidencia estructural única; reconciliación MCP explícita de aplicaciones
  parciales contra Hevy, sin confundir PostgreSQL sincronizado con el estado remoto.
- Superseries tipadas de extremo a extremo: propuestas con `superset_group`, validación de grupos
  consecutivos y conversión determinista a `superset_id` compartido en Hevy.
- Skill Hermes 0.6.4: entrevista y persistencia agrupadas por bloques, con una confirmación por
  bloque en lugar de una confirmación por cada campo o llamada MCP.
- Diseño documentado de Telegram Topics sobre un supergrupo privado, manteniendo PostgreSQL como
  fuente de verdad y dejando el enrutamiento `chat_id`/`message_thread_id` para el siguiente paso.
- Instalador idempotente de la skill Hermes mediante enlace de archivo, con backup, comprobación y
  prueba aislada; elimina las copias manuales en cada cambio.
- Enrutamiento local de las notificaciones de arranque y parada de Hermes al Topic `Alertas` del
  supergrupo; las revisiones post-entrenamiento continúan en `Revisiones`.

## Integraciones verificadas

- Hevy real: autenticación, usuario, 8 rutinas, 50 entrenamientos recientes y 451 plantillas de
  ejercicios verificados el 2026-08-05.
- Contrato real de `/v1/user/info`: sobre `data` con `id`, `name` y `url`.
- Docker Desktop y Compose funcionan sin `sudo`; PostgreSQL 17 está `healthy`, las pruebas de
  integración pasan y la migración `e15f7c9b4a20` está aplicada en la base local.
- Ollama 0.32.3 se verificó `healthy`, detectó la RTX 3070 y conservó `gpt-oss:20b` (13 GB) en un
  volumen Docker. PydanticAI obtuvo una salida estructurada real; una consulta en caliente tardó
  14,83 s antes de desaparecer la integración WSL de Docker Desktop.
- MCP v2 verificado por transporte `stdio` real fuera del sandbox: inicio, listado de 25
  herramientas, llamada sin credenciales y cierre correcto.
- La configuración real de Hermes volvió a probarse tras la migración: conexión correcta y 19
  herramientas descubiertas.
- Endpoint real de eventos Hevy verificado: pagina bajo `workouts`, incluida respuesta vacía. La
  línea base quedó creada y un segundo sondeo real terminó silenciosamente.
- Gateway Hermes activo como servicio de usuario con linger. Cron `gym-coach-post-workout` activo y
  gate silencioso verificado; el bot nuevo entregó correctamente un mensaje de prueba a Telegram.
- Sincronización real: 1 usuario, 451 plantillas, 4 rutinas y 95 entrenamientos; una segunda
  ejecución produjo 551 elementos sin cambios y ninguna inserción, actualización o eliminación.
- Incidente real de escritura revisado: un POST posterior obtuvo `201` y creó exactamente la primera
  de cuatro sesiones, aunque su cuerpo no validó. La lectura directa mostró cinco rutinas; no se
  expusieron payloads personales ni credenciales.
- Skill 0.6.4 enlazada desde la instalación real al repositorio; gateway reiniciado y MCP verificado
  con 27 herramientas.
- Supergrupo privado de Telegram creado, bot añadido y Topics `Entrenamiento` y `Revisiones`
  detectados por Hermes. El cron post-entrenamiento entrega ahora en `Revisiones`; los IDs privados
  permanecen únicamente en la configuración local de Hermes.
- Topic `Alertas` configurado como home channel de Hermes mediante `TELEGRAM_HOME_CHANNEL` y
  `TELEGRAM_HOME_CHANNEL_THREAD_ID`; no se guardan identificadores en el repositorio.
- Los avisos `Gateway restarting` y `Gateway online` conservan la entrega contextual al chat que
  inició el reinicio y se emiten además en el home channel `Alertas`; se eliminó la supresión
  específica de reinicios iniciados desde un chat en la instalación local de Hermes.
- La recuperación de sesiones tras una caída ahora inspecciona también el último mensaje persistido:
  las conversaciones cuyo último turno es de usuario, herramienta o una llamada de herramienta
  pendiente quedan marcadas para continuar aunque el apagado haya durado más de dos minutos.
- Sincronización posterior a la creación de las cuatro rutinas nuevas: PostgreSQL incorporó tres
  rutinas pendientes (`inserted=3`), sin borrados ni actualizaciones inesperadas.
- Docker Desktop 4.85.0 verificado; PostgreSQL queda `healthy` con `restart: unless-stopped` y
  Ollama se detuvo y pasó al perfil Compose opcional `llm` porque no es el proveedor activo.

## Pruebas existentes

- Salud FastAPI autocontenida sin base de datos ni API key.
- Cliente Hevy: usuario realista, opcionales/nulos, extras, paginación, HTTP, JSON inválido,
  esquema inválido, eventos incrementales realistas, diagnósticos sanitizados, timeout y no
  exposición de credenciales.
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
- Onboarding/planes MCP: rechazo sin confirmación, versiones de perfil, revisión de objetivos,
  métricas backend, borrador solicitado, comparación y aprobación local sin escritura en Hevy.
- Contratos robustos: revisión explícita, rechazo de prescripciones ambiguas, duración/distancia,
  evidencia caducada o inexistente y diff PostgreSQL por ejercicio/músculo.
- Verificación del octavo hito: 51 pruebas ordinarias pasan, seis integraciones opt-in pasan,
  Ruff y Mypy limpios, lock vigente, migración en `head` y Alembic sin deriva.
- Verificación del noveno hito: 55 pruebas ordinarias pasan, siete integraciones opt-in pasan,
  Ruff y Mypy limpios, lock vigente, migración en `head` y Alembic sin deriva.
- Verificación del décimo hito: 69 pruebas pasan, incluidas migraciones reversibles, PostgreSQL y
  transporte MCP opt-in; Ruff y Mypy están limpios. No se ejecutó una escritura Hevy real.
- Verificación de la corrección y el enlace Hermes: 73 pruebas pasan, incluidas las siete
  integraciones opt-in de PostgreSQL y MCP; Ruff, Mypy, lock y comprobación del diff están limpios.
- Verificación de recuperación/reconciliación: 76 pruebas pasan con PostgreSQL y transporte MCP
  opt-in; el cliente recupera una coincidencia única y conserva cualquier resultado ambiguo.
- Verificación del hito: 78 pruebas pasan con PostgreSQL y transporte MCP opt-in; validación de
  grupos y asignación de IDs Hevy cubiertas por pruebas unitarias. Falta probar una aplicación real
  con una superserie.
- Verificación de la corrección Hevy: 85 pruebas pasan con PostgreSQL y transporte MCP opt-in;
  Ruff, Mypy, lock y `git diff --check` están limpios. `hevy check` y `hevy user` reales terminaron
  con código 0 usando el `.env` local sin mostrar sus respuestas.
- Verificación de cargas prescritas: 85 pruebas pasan con PostgreSQL y transporte MCP opt-in; una
  carga `weight_kg` se conserva desde la propuesta pública hasta el payload de escritura de Hevy.

## Problemas conocidos

- El sandbox del agente bloquea el socket Docker; las comprobaciones requieren permiso escalado.
- La integración WSL de Docker Desktop desapareció transitoriamente en una sesión anterior; se
  recuperó sin modificar permisos globales y volvió a verificarse antes de este hito.
- El sandbox también bloquea el transporte MCP entre subprocesos; la prueba `stdio` debe ejecutarse
  fuera de él con `GYM_COACH_RUN_MCP_STDIO_TESTS=1`.
- La API pública de Hevy se declara inestable y requiere mantener fixtures y esquemas observados.
- La API pública de Hevy no ofrece webhooks documentados; la latencia depende del sondeo de cinco
  minutos y de la disponibilidad del equipo local.
- Los JSON raw contienen datos personales y no son fuente de verdad ni backup.
- MCP calcula adherencia contra los días semanales del perfil confirmado; la API y CLI todavía
  permiten un objetivo de consulta independiente.
- El volumen `kg·repeticiones` sigue limitado a ejercicios de peso y repeticiones. Peso corporal,
  asistencia, distancia y duración usan métricas propias para no fabricar un volumen incomparable.
- Las series indirectas se ponderan a 0,5 como heurística transparente; no estiman activación o
  hipertrofia fisiológica real.
- El borrador creado antes de este endurecimiento sigue legible y en estado `draft`, pero no contiene
  opcionalidad ni justificaciones estructuradas por cambio. Debe revisarse o sustituirse, no
  aprobarse como si usara el contrato nuevo.
- Hermes mantiene la conversación, pero `gym-coach` no conserva transcripciones.
- La aplicación real quedó reconciliada como `partial`: Hevy contiene la sesión de índice 0 de las
  cuatro aprobadas. Las tres restantes deben constituir una propuesta nueva y recorrer de nuevo
  ambas confirmaciones; repetir las cuatro duplicaría la primera.
- Las ediciones del repositorio se reflejan mediante el enlace, pero Hermes conserva skill y MCP en
  procesos persistentes: todavía requiere `hermes gateway restart` para recargarlos.
- El último reinicio solicitado quedó diferido por una unidad de trabajo activa; el siguiente
  arranque del servicio leerá el nuevo home channel desde `~/.hermes/.env`.
- El cambio de Hermes está fuera del repositorio y puede requerir reaplicarse si una actualización
  reemplaza `gateway/run.py`; el código modificado pasa una comprobación de sintaxis.
- El servicio de usuario de Hermes puede arrancar antes que Docker Desktop; el gate del cron sale en
  silencio si el puerto de PostgreSQL aún no acepta conexiones y reintenta en la siguiente ejecución.
- La clave OpenAI configurada es válida, pero la cuenta no tiene saldo de API; la suscripción a
  ChatGPT no aporta créditos a la API. La alternativa local evita esa dependencia.
- `gpt-oss:20b` se reparte aproximadamente 42% GPU y 58% CPU en este equipo. La primera carga tardó
  unos 82 s; Ollama lo mantiene residente 10 minutos y la inferencia en caliente es mucho más rápida.
- La entrega automática completa aún debe validarse con un entrenamiento real nuevo. Hasta entonces
  están verificados por separado el evento incremental, el gate, MCP y la entrega Telegram.
- Las aplicaciones confirmadas de rutinas lanzan ahora una sincronización completa de Hevy antes de
  devolver el resultado; la respuesta incluye `sync_status` y conserva el estado de la escritura si
  la sincronización posterior falla.
- Reparación verificada de las aplicaciones B/C anteriores: una sincronización completa posterior
  terminó `succeeded`, actualizó 3 rutinas y dejó 8 rutinas normalizadas en PostgreSQL.
- La skill Hermes solicita la confirmación final mediante `clarify` con opciones de aprobar/denegar,
  que Telegram representa con botones cuando la interfaz interactiva está disponible.
- MCP expone `sync_hevy` como reparación local confirmada: ejecuta una instantánea completa,
  idempotente y sin modificar rutinas en Hevy.
- Las propuestas de planes admiten `weight_kg` por serie y lo convierten al campo de carga de
  Hevy; las cargas solo deben incluirse con evidencia suficiente.

## Último hito completado

Diario nutricional conversacional (2026-09-14): catálogo, recetas, comidas, resumen diario y
correcciones auditadas. Pendiente prueba de aceptación con una etiqueta real desde Telegram.

Hito de sincronización posterior a escrituras, confirmación interactiva y cargas prescritas por
serie, sobre la base de ergonomía conversacional, superseries y enrutamiento de Telegram Topics,
incluido `Alertas`; queda pendiente una aplicación real de superserie y la prueba de entrega
automática en `Revisiones`.

## Corrección verificada del contrato Hevy

La respuesta real de escritura puede usar `{"routine": [routine]}`. El cliente acepta una lista de
un único elemento y rechaza listas ambiguas. La reconciliación de actualizaciones lee ahora la
rutina fuente exacta y compara en Python los campos controlados con el plan aprobado. El intento
anterior no debe reutilizarse: tras recargar MCP hay que crear una propuesta nueva.

Hermes no ofrece actualmente selección automática de modelo por complejidad: sus fallbacks cubren
errores y cambiar de modelo rompe la caché de prompt. Se mantiene Luna `high` como predeterminado y
Terra se reserva para turnos complejos mediante cambio explícito.
