# Registro de decisiones

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
