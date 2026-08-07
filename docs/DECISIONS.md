# Registro de decisiones

## 2026-08-06 — Superseries explícitas y agrupación de confirmaciones

- **Decisión:** representar una superserie con un `superset_group` textual en la propuesta y
  convertirlo a un ID entero estable dentro de cada rutina. Agrupar la entrevista y persistencia por
  bloques, manteniendo una confirmación explícita para cada bloque y las protecciones de escritura.
- **Motivo:** el modelo Hevy ya expone `superset_id`, pero las propuestas no podían solicitarlo; las
  confirmaciones por campo hacían pesada la conversación sin aportar información adicional.
- **Alternativas:** inferir superseries por títulos; eliminar toda confirmación; guardar grupos solo
  en la memoria conversacional.
- **Consecuencias:** el plan conserva la intención de superserie y las validaciones son testeables;
  las escrituras externas siguen auditadas y el flujo de Topics queda separado del dominio.

## 2026-08-06 — Supergrupo privado y entrega de revisiones por Topic

- **Decisión:** usar el supergrupo privado existente con `Entrenamiento` y `Revisiones`, y dirigir
  el cron post-entrenamiento a `Revisiones` mediante el destino Telegram con `chat_id` y `thread_id`.
- **Motivo:** Hermes ya conserva sesiones separadas por Topic y soporta destinos de cron en ese
  formato; una comunidad añadiría grupos y permisos innecesarios para un único atleta.
- **Alternativas:** canal con grupo de discusión; comunidad con varios chats; mantener todas las
  revisiones en el chat privado original.
- **Consecuencias:** la conversación y las revisiones quedan ordenadas sin mover secretos al repo;
  falta validar una entrega real después de un entrenamiento nuevo.

## 2026-08-06 — Una confirmación visible para aplicar una rutina

- **Decisión:** interpretar la petición explícita de crear o mejorar una rutina como aprobación
  inicial del borrador; mostrar comparación y preview juntas y pedir una única confirmación final
  antes de `apply_training_plan_to_hevy`.
- **Motivo:** eliminar la confirmación conversacional redundante sin retirar la preview, el token ni
  la auditoría interna de aprobación y aplicación.
- **Alternativas:** mantener dos respuestas separadas; eliminar también la confirmación final.
- **Consecuencias:** Hermes requiere una sola respuesta afirmativa visible para la escritura exacta;
  PostgreSQL conserva las dos fases y los fallos inciertos siguen sin reintento automático.

## 2026-08-06 — Recuperar y reconciliar creaciones Hevy por coincidencia estructural

- **Decisión:** tomar una instantánea de IDs antes de crear y, si el `2xx` no valida, confirmar solo
  una rutina nueva que coincida de forma estructural y única. Exponer reconciliación MCP local para
  aplicaciones `uncertain`/`partial` mediante lectura directa de Hevy.
- **Motivo:** Hevy devolvió `201` y creó una rutina, pero el cuerpo no coincidió con el contrato;
  consultar solo PostgreSQL ocultó el cambio hasta la siguiente sincronización.
- **Alternativas:** reintentar el POST; confiar en el código 201 sin identificar el recurso; tratar
  el listado PostgreSQL como reconciliación remota.
- **Consecuencias:** se evitan duplicados y se identifican las sesiones confirmadas; hay lecturas
  adicionales en la creación y cualquier coincidencia ambigua permanece bloqueada.

## 2026-08-06 — Skill Hermes enlazada al repositorio

- **Decisión:** instalar `SKILL.md` como enlace simbólico de archivo mediante un script idempotente,
  conservando como backup cualquier copia previa y ofreciendo `--check`.
- **Motivo:** las copias manuales dejan fácilmente a Hermes ejecutando contratos antiguos. Hermes
  descubre archivos enlazados dentro de directorios reales, pero `Path.rglob` no recorre un
  directorio de skill que sea un enlace.
- **Alternativas:** copiar después de cada cambio; enlazar el directorio completo; modificar el
  cargador de Hermes; duplicar la skill en configuración.
- **Consecuencias:** las ediciones del repositorio se reflejan sin sincronización manual. Sigue
  haciendo falta reiniciar el gateway para recargar la skill y el subproceso MCP persistente.

## 2026-08-06 — Contrato real y diagnóstico seguro de escritura Hevy

- **Decisión:** enviar `folder_id: null` explícito al crear, validar respuestas bajo `routine` o en
  forma directa y devolver códigos sanitizados como `hevy_http_403`. Un 2xx cuyo cuerpo no valida
  queda `uncertain`.
- **Motivo:** dos intentos reales fueron rechazados sin crear rutinas; el cliente omitía un campo
  nullable requerido, esperaba una respuesta sin sobre y descartaba el código HTTP útil.
- **Alternativas:** conservar un error `failed` genérico; registrar el cuerpo completo de Hevy;
  reintentar automáticamente respuestas inválidas.
- **Consecuencias:** Hermes puede distinguir rechazo limpio de resultado ambiguo sin ver datos
  remotos. Antes de otro intento hay que comprobar el límite de cuatro rutinas y emitir una preview
  y un token nuevos.

## 2026-08-06 — Entrevista longitudinal y nivel derivado del historial

- **Decisión:** ampliar el perfil con antropometría voluntaria, actividad, recuperación, nutrición y
  salud; guardar mediciones/check-ins e inferir profundidad del historial con confianza y límites.
- **Motivo:** evitar preguntas redundantes sobre nivel cuando Hevy aporta meses de evidencia, sin
  confundir historial con técnica.
- **Alternativas:** conservar un perfil mínimo; dejar la entrevista en memoria de Hermes.
- **Consecuencias:** PostgreSQL conserva el estado y cada dato sensible se resume y confirma.

## 2026-08-06 — Conocimiento deportivo y nutricional trazable

- **Decisión:** codificar cálculos básicos y un catálogo de reglas con fuente/año/alcance; Hermes
  puede investigar fuentes primarias cuando el catálogo no baste.
- **Motivo:** perder grasa exige alimentación y actividad, y el LLM no debe calcular ni presentar
  recomendaciones generales como hechos personales.
- **Alternativas:** RAG completo; confiar solo en el conocimiento paramétrico del modelo.
- **Consecuencias:** no se añade vector store; la nutrición clínica se deriva a profesionales.

## 2026-08-06 — Escritura Hevy con doble confirmación y sin reintento ambiguo

- **Decisión:** permitir POST/PUT de rutinas solo tras propuesta aprobada, preview con hashes, token
  de un solo uso y segunda confirmación. Antes de un PUT se relee la rutina remota y se rechaza si
  cambió. Un timeout queda `uncertain` y no se reintenta.
- **Motivo:** cumplir el control humano y evitar duplicar o sobrescribir rutinas ante fallos de red.
- **Alternativas:** una sola aprobación; reintentos HTTP; creación manual permanente.
- **Consecuencias:** un fallo tras crear parte de un plan queda `partial` y exige reconciliación.

## 2026-08-06 — Mantener temporalmente el sondeo como disparador

- **Decisión:** conservar el cron incremental cada cinco minutos para la primera validación real y
  aplazar la recepción del webhook disponible en la cuenta de Hevy.
- **Motivo:** el flujo de sondeo ya está implementado y probado; el webhook exige además desplegar un
  endpoint HTTPS público y gestionar un secreto Bearer y su disponibilidad continua.
- **Alternativas:** habilitar inmediatamente un túnel temporal; desplegar un endpoint estable con
  dominio; conectar Hevy al receptor genérico de Hermes pese a la incompatibilidad de autenticación.
- **Consecuencias:** la primera revisión puede tardar hasta unos seis minutos. El webhook queda como
  mejora posterior y la cola PostgreSQL permite cambiar el disparador sin rehacer el análisis.

## 2026-08-06 — Eventos incrementales y cron de Hermes para revisiones automáticas

- **Decisión:** sondear cada cinco minutos el feed público `/v1/workouts/events`, persistir cursor y
  revisiones en PostgreSQL y usar un pre-script de Hermes que solo despierta al agente ante cambios.
- **Motivo:** la API pública de Hevy no documenta webhooks; Hermes proporciona gate sin modelo,
  sesiones cron aisladas y entrega directa al canal Telegram configurado.
- **Alternativas:** usar endpoints privados de webhook; sincronizar siempre la instantánea completa;
  ejecutar el modelo cada cinco minutos; enviar Telegram directamente desde `gym-coach`.
- **Consecuencias:** la latencia esperada es inferior a unos seis minutos, no hay coste de inferencia
  sin cambios y PostgreSQL conserva idempotencia y reintentos. El gateway y el chat de Telegram
  deben estar operativos; Hevy permanece exclusivamente de lectura.

## 2026-08-06 — Línea base silenciosa y reconocimiento posterior a la revisión

- **Decisión:** el primer sondeo fija el cursor sin revisar históricos; cada evento nuevo se reclama
  con caducidad de 30 minutos y Hermes lo reconoce solo tras preparar el informe.
- **Motivo:** evita enviar decenas de revisiones antiguas y permite recuperar ejecuciones que se
  interrumpan antes de generar contenido.
- **Alternativas:** marcar todos los entrenamientos previos como entregados; eliminar la cola al
  reclamar; deduplicar mediante archivos dentro de Hermes.
- **Consecuencias:** una reclamación abandonada vuelve a estar disponible. Un fallo posterior al
  reconocimiento pero anterior a la entrega sigue requiriendo inspección del ledger de Hermes.

## 2026-08-06 — Seguridad explícita y planes tipados

- **Decisión:** exigir que Hermes confirme haber preguntado por limitaciones y preferencias; modelar
  sesiones opcionales, ubicación, duración y series por una sola dimensión entre repeticiones,
  tiempo o distancia.
- **Motivo:** una lista vacía no demostraba que se hubiera realizado el cribado y los isométricos se
  estaban representando como repeticiones, perdiendo significado.
- **Alternativas:** confiar en la conversación; almacenar texto libre; tratar todas las sesiones como
  obligatorias; codificar segundos dentro de `load_guidance`.
- **Consecuencias:** el perfil existente vuelve a estado de onboarding pendiente hasta confirmar los
  dos apartados. Los borradores antiguos siguen legibles, pero no adquieren metadatos que nunca
  tuvieron y deben sustituirse antes de aprobar.

## 2026-08-06 — Evidencias revalidadas y diff determinista

- **Decisión:** volver a resolver en el backend cada ID de evidencia al crear una propuesta, exigir
  evidencia por cambio y comparar ejercicios, frecuencias, series y músculos primarios en Python.
- **Motivo:** un ID declarado por el agente no prueba por sí solo que la métrica exista o siga
  vigente, y los recuentos estructurales no deben depender del modelo conversacional.
- **Alternativas:** confiar en IDs suministrados por Hermes; guardar todas las lecturas en un ledger;
  dejar la comparación en texto libre; recalcular dentro de la skill.
- **Consecuencias:** evidencias antiguas o inventadas se rechazan y deben consultarse otra vez. El
  diff es reproducible; la distribución muscular usa por ahora solo el músculo primario.

## 2026-08-06 — Onboarding confirmado y planes locales mediante MCP

- **Decisión:** permitir cinco mutaciones MCP limitadas a perfil, objetivos, creación de borradores y
  decisiones locales. Perfil, objetivos y decisiones exigen confirmación explícita; crear un
  borrador exige que el atleta lo haya solicitado. Ninguna herramienta escribe en Hevy.
- **Motivo:** el onboarding debe ocurrir naturalmente en Hermes/Telegram, pero PostgreSQL debe
  conservar el estado estructurado y auditable en vez de depender de memoria conversacional.
- **Alternativas:** introducir los datos mediante CLI; confiar solo en memoria de Hermes; permitir
  escrituras directas sin confirmación; posponer cualquier persistencia hasta Telegram.
- **Consecuencias:** el perfil conserva instantáneas versionadas, una revisión de objetivo archiva la
  versión anterior y las decisiones sobre planes quedan registradas. La confirmación se expresa en
  el contrato MCP y la skill prohíbe marcarla sin una respuesta afirmativa del atleta.

## 2026-08-06 — Métricas y evidencias calculadas exclusivamente por gym-coach

- **Decisión:** exponer resumen deportivo y progreso por ejercicio mediante MCP con límites de
  periodo e IDs de evidencia; Hermes solo los interpreta.
- **Motivo:** preservar resultados reproducibles y evitar cálculos deportivos variables dentro del
  modelo conversacional.
- **Alternativas:** enviar entrenamientos brutos y pedir cálculos a Hermes; ejecutar PydanticAI como
  intermediario; duplicar fórmulas en la skill.
- **Consecuencias:** volumen, repeticiones, adherencia, e1RM y estancamiento proceden del motor Python.
  Los planes pueden citar esas evidencias, pero la comparación semántica detallada queda pendiente.

## 2026-08-06 — Hermes como orquestador mediante MCP

- **Decisión:** usar inicialmente el bucle normal de Hermes con el proveedor `openai-codex` y
  conectar `gym-coach` como servidor MCP local `stdio` exclusivamente de lectura. PostgreSQL sigue
  siendo la fuente de verdad y PydanticAI queda como extra experimental.
- **Motivo:** Hermes aporta conversación, memoria, skills y futuros canales sin duplicar la lógica
  deportiva ni el estado estructurado del backend. MCP mantiene una frontera estándar y auditable.
- **Alternativas:** ampliar PydanticAI como orquestador principal; sustituir PostgreSQL por memoria
  de Hermes; activar Codex App-Server Runtime; integrar Hermes mediante HTTP propio.
- **Consecuencias:** el backend expone contratos públicos estables y ninguna escritura. Hermes y su
  autenticación se configuran manualmente fuera del repositorio. El runtime App-Server queda
  aplazado para conservar memoria y skills en el bucle normal.

## 2026-08-06 — SDK MCP v2 y prueba stdio fuera del sandbox

- **Decisión:** usar `mcp>=2,<3`, su API de alto nivel `MCPServer` y transporte `stdio`; marcar la
  prueba de subproceso como opt-in.
- **Motivo:** v2 es la línea estable actual. El sandbox bloquea de forma reproducible el intercambio
  stdio incluso para un servidor mínimo, mientras la misma prueba fuera del sandbox inicia, lista,
  llama y cierra correctamente.
- **Alternativas:** fijar la rama v1 mantenida; usar HTTP; omitir la prueba real de transporte.
- **Consecuencias:** la suite ordinaria usa pruebas MCP en memoria y no se cuelga; la verificación
  real se ejecuta con `GYM_COACH_RUN_MCP_STDIO_TESTS=1` fuera del sandbox.

## 2026-08-06 — Modelo local gratuito como proveedor predeterminado

- **Decisión:** usar Ollama con el modelo abierto de OpenAI `gpt-oss:20b` por defecto y conservar
  OpenAI Responses como proveedor opcional seleccionado mediante entorno.
- **Motivo:** la API key verificada no dispone de saldo y la suscripción de ChatGPT no incluye uso
  de API. El equipo tiene una RTX 3070 de 8 GB, 16 GB de RAM y capacidad para ejecutar el modelo
  repartido entre GPU y memoria sin enviar el perfil deportivo a terceros.
- **Alternativas:** pagar créditos de OpenAI; Gemini gratuito, que puede usar datos del free tier
  para mejorar productos; OpenRouter o Groq gratuitos con límites y proveedor remoto; un modelo
  local más pequeño con menor capacidad.
- **Consecuencias:** no hay coste por petición ni API key para el entrenador predeterminado, a
  cambio de una descarga de unos 14 GB, más uso de RAM/GPU y mayor latencia. El nombre del proveedor
  se conserva con cada propuesta para trazabilidad. En el equipo actual se observó un reparto
  42% GPU/58% CPU, unos 82 s de primera carga y 14,83 s para una prueba estructurada en caliente.

## 2026-08-05 — Entrenador estructurado sobre OpenAI Responses

- **Decisión:** usar PydanticAI con OpenAI Responses, `gpt-5.6-terra` configurable y razonamiento
  medio por defecto.
- **Motivo:** el caso es conversacional y repetido; Terra equilibra capacidad, latencia y coste,
  mientras la Responses API y PydanticAI aportan salida estructurada.
- **Alternativas:** modelo Sol por defecto; llamadas OpenAI directas; proveedor fijo en código.
- **Consecuencias:** el modelo puede cambiarse por entorno y los tests lo sustituyen sin red; una
  ejecución real requiere `OPENAI_API_KEY` local.

## 2026-08-05 — Contexto mínimo y sin transcripciones persistidas

- **Decisión:** enviar petición actual, perfil, objetivos, rutinas sin notas y métricas; no guardar
  prompts, respuestas brutas ni historial completo.
- **Motivo:** es suficiente para revisar/generar planes y reduce exposición de datos personales.
- **Alternativas:** enviar payloads Hevy completos; usar conversaciones durables del proveedor;
  conservar todos los mensajes localmente.
- **Consecuencias:** privacidad y auditoría más simples; la continuidad conversacional rica queda
  pendiente de un diseño de resúmenes consentidos.

## 2026-08-05 — Aprobación local sin efecto externo

- **Decisión:** las propuestas solo transitan de `draft` a `approved` o `rejected` en PostgreSQL.
- **Motivo:** aprobar una idea y modificar una rutina externa son autoridades diferentes.
- **Alternativas:** aplicar al aprobar; añadir ya un estado `applied`; no persistir decisiones.
- **Consecuencias:** no existe ruta técnica de escritura Hevy en este hito; una aplicación futura
  necesitará previsualización y una aprobación explícita adicional.

## 2026-08-05 — Adaptar el usuario al sobre `data`

- **Decisión:** modelar `/v1/user/info` como `{"data": UserInfo}` y mantener campos extra.
- **Motivo:** dos respuestas reales observadas usan `data`; el sobre `user` anterior nunca valida.
- **Alternativas:** aceptar ambos sobres; omitir el modelo y devolver diccionarios.
- **Consecuencias:** contrato tipado acorde a producción; un cambio futuro vuelve a fallar de forma
  explícita y sanitizada en lugar de propagarse silenciosamente.

## 2026-08-05 — Diagnósticos Pydantic sin valores recibidos

- **Decisión:** informar ruta, tipo esperado, tipo recibido y ausencia, omitiendo siempre valores.
- **Motivo:** permite corregir contratos externos sin filtrar datos personales o secretos.
- **Alternativas:** mostrar `ValidationError` completo; mantener un error genérico.
- **Consecuencias:** diagnóstico útil y seguro, aunque algunos constraints poco comunes se describen
  de forma genérica como `valid value`.

## 2026-08-05 — Mantener la salida de usuario anónima

- **Decisión:** `hevy user` confirma la descarga sin imprimir nombre, ID ni URL.
- **Motivo:** el objetivo operativo es verificar/guardar la respuesta, no publicar datos personales.
- **Alternativas:** mostrar el nombre completo; mostrar un identificador parcialmente redactado.
- **Consecuencias:** menor riesgo en terminales y logs; el payload completo sigue disponible solo en
  `data/raw/hevy/`, que permanece excluido de Git.

## 2026-08-05 — Alinear esquemas con muestras raw verificadas

- **Decisión:** mapear `type` a `set_type`, corregir `superset_id` y tipar `routine_id`,
  `rest_seconds` y `rep_range`.
- **Motivo:** esos nombres y estructuras aparecen consistentemente en las muestras reales; los
  nombres anteriores `set_type` y `supersets_id` dejaban atributos tipados vacíos.
- **Alternativas:** conservarlos únicamente como campos extra; modelar todos los payloads como JSON.
- **Consecuencias:** el acceso tipado refleja el contrato observado sin perder tolerancia a futuras
  adiciones de Hevy.

## 2026-08-05 — Distinguir restricciones del sandbox del estado de Docker

- **Decisión:** validar Docker fuera del sandbox, sin `sudo` ni cambios globales, antes de atribuir
  un `permission denied` al usuario o al daemon.
- **Motivo:** el sandbox bloquea el socket; con acceso aprobado Docker responde y PostgreSQL está
  `healthy`.
- **Alternativas:** aceptar el diagnóstico del sandbox; cambiar grupos o permisos del socket.
- **Consecuencias:** Docker queda verificado sin mutaciones globales; futuras comprobaciones del
  daemon necesitarán permiso escalado del ejecutor.

## 2026-08-05 — Sincronización mediante instantánea completa

- **Decisión:** descargar completamente usuario, plantillas, rutinas y entrenamientos antes de
  aplicar una única transacción PostgreSQL.
- **Motivo:** solo una instantánea completa permite interpretar ausencias como borrados sin falsos
  positivos por páginas o descargas fallidas.
- **Alternativas:** usar únicamente eventos de Hevy; persistir página a página; limitar históricos.
- **Consecuencias:** semántica simple y recuperable a cambio de más llamadas. Los hashes hacen
  incremental la escritura y una futura fase podrá adoptar eventos conservando el repositorio.

## 2026-08-05 — Hijos normalizados y reemplazo atómico al cambiar

- **Decisión:** normalizar ejercicios y series en tablas propias; si cambia el hash del padre, sus
  hijos se eliminan y reconstruyen dentro de la misma transacción.
- **Motivo:** Hevy identifica establemente el padre, pero posiciones de ejercicios/series son la
  identidad observable de los hijos.
- **Alternativas:** JSONB embebido; upsert individual de hijos; IDs sintéticos derivados.
- **Consecuencias:** consultas deportivas futuras son relacionales y consistentes; modificar un
  padre reemplaza sus hijos, mientras una repetición idéntica no los toca.

## 2026-08-05 — Borrado lógico vinculado a la ejecución

- **Decisión:** conservar entidades ausentes con `deleted_at` y `deleted_sync_id`, y restaurarlas si
  reaparecen.
- **Motivo:** se requiere trazabilidad y no conviene destruir históricos por cambios del proveedor.
- **Alternativas:** borrado físico; una tabla separada de eventos; ignorar ausencias.
- **Consecuencias:** las consultas activas deberán filtrar `deleted_at IS NULL`; cada borrado queda
  asociado a un `sync_run` auditable.

## 2026-08-05 — Dominio conservador para volumen y e1RM

- **Decisión:** calcular volumen externo solo para `weight_reps` y series `normal`; estimar 1RM con
  Epley únicamente con carga positiva y 1-12 repeticiones.
- **Motivo:** no se dispone de masa corporal para ejercicios asistidos/lastrados y Epley pierde
  utilidad con repeticiones altas o modalidades temporizadas/de distancia.
- **Alternativas:** aplicar Epley a todo; estimar masa corporal; sumar cargas parciales heterogéneas.
- **Consecuencias:** resultados comparables y explicables, a costa de omitir modalidades que
  necesitarán reglas específicas en el futuro.

## 2026-08-05 — Redondeo decimal y cálculo bajo demanda

- **Decisión:** usar `Decimal`, redondeo `ROUND_HALF_UP` a 0,01 y calcular métricas al consultar.
- **Motivo:** garantiza reproducibilidad y el histórico actual no justifica materializaciones.
- **Alternativas:** floats sin redondeo; tablas de métricas; vistas materializadas.
- **Consecuencias:** no hay migración adicional ni riesgo de métricas obsoletas; si el volumen crece
  se medirá antes de materializar.

## 2026-08-05 — Adherencia y estancamiento configurables

- **Decisión:** adherencia compara sesiones con un objetivo semanal en una ventana y se limita al
  100%; estancamiento exige al menos cuatro sesiones, 14 días y menos de 2% de mejora en e1RM.
- **Motivo:** Hevy no aporta una frecuencia planificada ni una definición universal de meseta.
- **Alternativas:** inferir frecuencia histórica; reglas fijas ocultas; decisión del LLM.
- **Consecuencias:** cada resultado incluye ventana, objetivo, sesiones, motivo y umbral; cambiar la
  ventana puede cambiar legítimamente la clasificación.

## 2026-08-06 — Avisos del gateway en el Topic Alertas

- **Decisión:** usar el supergrupo privado y su Topic `Alertas` como `TELEGRAM_HOME_CHANNEL` más
  `TELEGRAM_HOME_CHANNEL_THREAD_ID`; mantener las revisiones automáticas en `Revisiones`.
- **Motivo:** separar avisos operativos de las conversaciones de entrenamiento y de las revisiones.
- **Alternativas:** conservar el chat privado como home channel; enviar todos los avisos a
  `Revisiones`.
- **Consecuencias:** el ajuste vive en `~/.hermes/.env` y no en Git; el primer arranque después de
  un reinicio efectivo debe confirmar la entrega en `Alertas`.

## 2026-08-07 — Aviso de restarting también en Alertas

- **Decisión:** mantener los avisos `Gateway restarting` y `Gateway online` en el chat que inició
  el reinicio y emitirlos además en el home channel configurado, que apunta a `Alertas`.
- **Motivo:** el aviso es útil como respuesta contextual, pero los eventos operativos deben quedar
  reunidos en el topic de alertas.
- **Alternativas:** moverlo exclusivamente a `Alertas`; dejar el comportamiento original de Hermes,
  que suprimía el home channel para reinicios iniciados dentro de un chat.
- **Consecuencias:** se aplicó un parche local mínimo en `~/.hermes/hermes-agent/gateway/run.py`;
  una actualización de Hermes podría sobrescribirlo y requerir reaplicación.

## 2026-08-07 — Recuperación de turnos y arranque de dependencias

- **Decisión:** al recuperarse de una caída, Hermes inspecciona el final persistido de cada
  conversación y reanuda únicamente los turnos cuyo último elemento sea una entrada de usuario,
  resultado de herramienta o llamada de herramienta sin finalizar. PostgreSQL usa `unless-stopped`;
  Ollama queda en el perfil Compose opcional `llm`.
- **Motivo:** el límite temporal fijo no cubría apagados largos y relanzar conversaciones ya
  finalizadas produciría duplicados; PostgreSQL debe estar disponible antes del cron y Ollama no es
  el proveedor activo.
- **Alternativas:** reanudar todas las sesiones recientes; dejar que el cron informe cada fallo de
  conexión; arrancar siempre Ollama.
- **Consecuencias:** se preservan turnos pendientes sin duplicar respuestas terminadas, el primer
  sondeo tras el arranque puede quedar silencioso hasta que PostgreSQL esté listo y Ollama solo
  consume recursos cuando se activa explícitamente el perfil.

## 2026-08-07 — Normalización de respuestas de escritura Hevy

- **Decisión:** aceptar `routine` como objeto o como lista de exactamente un elemento en las
  respuestas de rutinas; rechazar listas de tamaño distinto de uno.
- **Motivo:** la respuesta real observada en `PUT /v1/routines/{id}` usa el envoltorio de lista,
  aunque el lector y algunas respuestas de escritura usan un objeto. Una lista ambigua no puede
  asociarse de forma segura a la rutina solicitada.
- **Alternativas:** aceptar cualquier lista y elegir el primero; tratar toda respuesta como incierta.
- **Consecuencias:** las actualizaciones válidas dejan de clasificarse erróneamente como inciertas,
  conservando el bloqueo seguro ante payloads ambiguos.

## 2026-08-07 — Reconciliación de actualizaciones por lectura exacta

- **Decisión:** para una aplicación `update`, leer `source_routine_id` y comparar en Python todos
  los campos controlados con el plan aprobado; usar el feed completo solo para `create`.
- **Motivo:** una actualización no crea una rutina reciente y no puede reconciliarse buscando por
  `created_at`; la lectura directa evita falsos positivos y no escribe nada.
- **Alternativas:** mantener reconciliación solo para creaciones; volver a enviar el `PUT`.
- **Consecuencias:** un resultado incierto puede marcarse aplicado solo ante coincidencia exacta;
  cualquier discrepancia sigue requiriendo una propuesta y token nuevos.

## 2026-08-07 — Política de modelos Hermes

- **Decisión:** mantener `gpt-5.6-luna` con `high` como predeterminado y cambiar explícitamente a
  `gpt-5.6-terra` en turnos complejos mientras no exista un router probado.
- **Motivo:** Hermes ofrece fallback por errores, no selección por complejidad; cambiar de modelo
  durante una conversación rompe la caché y una heurística no validada puede aumentar coste o
  degradar seguridad.
- **Alternativas:** usar fallback como selector; añadir un clasificador LLM en el gateway.
- **Consecuencias:** comportamiento predecible y barato ahora; el enrutamiento automático queda
  aplazado a un hito con métricas de coste, latencia y calidad.

## 2026-08-07 — Sincronización posterior a escrituras Hevy

- **Decisión:** después de una creación o actualización confirmada, ejecutar una instantánea
  completa de Hevy y devolver `sync_status` junto con el resultado de la aplicación. Las
  reconciliaciones que confirman recursos remotos también sincronizan.
- **Motivo:** PostgreSQL debe reflejar automáticamente el estado remoto y no depender de que el
  atleta ejecute `gym-coach hevy sync` manualmente.
- **Alternativas:** actualizar solo la fila afectada; esperar al cron; ejecutar sincronización antes
  de cada lectura.
- **Consecuencias:** una escritura puede tardar más y descarga también entrenamientos/plantillas,
  pero conserva el snapshot como fuente de verdad local. Si la sincronización falla, la escritura
  remota no se reintenta y queda visible como `sync_status=failed`.

## 2026-08-07 — Confirmación interactiva de aplicaciones

- **Decisión:** Hermes debe usar `clarify` con dos elecciones visibles, aprobar o denegar, para la
  confirmación final antes de llamar al MCP de escritura; el texto queda como fallback.
- **Motivo:** reducir errores y fricción al autorizar cambios sin eliminar la preview exacta ni la
  auditoría del backend.
- **Alternativas:** exigir siempre una palabra escrita; eliminar la confirmación final; delegarla en
  el modelo sin una interacción del atleta.
- **Consecuencias:** Telegram puede mostrar botones inline mediante la skill enlazada; otras
  interfaces pueden presentar las mismas elecciones como lista o texto.

## 2026-08-07 — Reparación manual de sincronización desde MCP

- **Decisión:** exponer `sync_hevy` como herramienta MCP local, idempotente y protegida por
  confirmación, para ejecutar una instantánea completa de Hevy en PostgreSQL sin modificar Hevy.
- **Motivo:** una sincronización posterior puede fallar cuando no hay nuevos eventos que despierten
  el cron; el atleta necesita una recuperación desde Telegram sin acceder a la CLI.
- **Alternativas:** depender solo del cron; ejecutar comandos shell desde Hermes; actualizar solo la
  rutina afectada.
- **Consecuencias:** existe un fallback observable con contadores y `run_id`; sigue siendo una
  operación local confirmada y no sustituye los reintentos automáticos futuros.
