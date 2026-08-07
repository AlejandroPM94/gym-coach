# Contrato experimental del entrenador PydanticAI

Hermes mediante MCP es el orquestador conversacional principal. Esta integración se conserva como
opción experimental y para posibles evaluaciones; no es necesaria para ejecutar el backend.

## Capacidades actuales

- Mantener un perfil con experiencia, disponibilidad, equipamiento, limitaciones y preferencias.
- Mantener datos confirmados de antropometría, estilo de vida, salud y nutrición, más mediciones y
  check-ins fechados.
- Mantener objetivos deportivos ordenados y versionados.
- Revisar las rutinas activas sincronizadas y las métricas de los últimos 28 días.
- Responder con hallazgos que citan evidencias deterministas.
- Proponer una rutina nueva, una mejora o una progresión como borrador estructurado.
- Aprobar o rechazar el borrador y, mediante MCP, previsualizar y aplicar la versión exacta en Hevy
  tras una única confirmación final sobre la preview exacta.

## Frontera de datos

El proveedor predeterminado es Ollama local con `gpt-oss:20b`: el texto de la petición y el contexto
se procesan en el equipo. Si el usuario selecciona voluntariamente OpenAI, solo se envían al
proveedor el texto actual y un JSON mínimo con perfil, objetivos, rutinas sin notas y evidencias
calculadas. Nunca se incluyen payloads raw, nombre/URL del usuario Hevy, descripciones de
entrenamientos, credenciales ni cabeceras. Las limitaciones físicas forman parte del perfil porque
son necesarias para una propuesta segura.

PostgreSQL conserva perfil, objetivos y la parte estructurada de las propuestas. No conserva la
petición completa, el prompt compuesto, mensajes de razonamiento ni la respuesta bruta del modelo.
Cuando se usa la API de OpenAI se configura con `openai_store=false`. Cada ejecución limita las
peticiones a tres (incluidos reintentos), la entrada a 100.000 tokens y la salida a 6.000 tokens.
El timeout es de 300 segundos para Ollama local y 60 segundos para OpenAI.

## Evidencia y seguridad

El código calcula las métricas y asigna identificadores a cada hecho. La salida exige referencias
a esos identificadores y se rechaza si aparece uno desconocido. El agente interpreta, pero no
calcula volumen, e1RM, adherencia o estancamiento. Una propuesta es orientación deportiva, no un
diagnóstico médico.

Los estados de propuesta son `draft`, `approved` y `rejected`. La aplicación externa tiene estado
separado (`prepared`, `applying`, `applied`, `failed`, `uncertain` o `partial`), hash del plan y de la
rutina origen y token almacenado solo como hash. Antes de actualizar se compara otra vez la rutina
remota; un timeout nunca se reintenta.

El resultado público incluye un diagnóstico seguro (`hevy_http_<status>`,
`hevy_invalid_response`, `hevy_timeout` o `hevy_transport`) sin cuerpo remoto. Un `403` puede indicar
permisos, plan o límite de cuenta —la modalidad gratuita de Hevy admite cuatro rutinas— y no debe
presentarse automáticamente como una API key incorrecta. Una respuesta inválida después de un 2xx
queda `uncertain`, porque la escritura puede haberse producido, y nunca se reintenta automáticamente.

## Pruebas

Los tests usan `TestModel` de PydanticAI y no necesitan red ni API keys. Cubren salida válida,
esquema inválido, campos extra, rangos inválidos, evidencia inventada y persistencia/aprobación
local sobre PostgreSQL.
