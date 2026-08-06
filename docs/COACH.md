# Contrato experimental del entrenador PydanticAI

Hermes mediante MCP es el orquestador conversacional principal. Esta integración se conserva como
opción experimental y para posibles evaluaciones; no es necesaria para ejecutar el backend.

## Capacidades actuales

- Mantener un perfil con experiencia, disponibilidad, equipamiento, limitaciones y preferencias.
- Mantener objetivos deportivos ordenados y versionados.
- Revisar las rutinas activas sincronizadas y las métricas de los últimos 28 días.
- Responder con hallazgos que citan evidencias deterministas.
- Proponer una rutina nueva, una mejora o una progresión como borrador estructurado.
- Aprobar o rechazar el borrador en PostgreSQL sin modificar Hevy.

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

Los estados permitidos son `draft`, `approved` y `rejected`. Solo un borrador puede decidirse y la
transición es irreversible en esta fase. No existe estado `applied` ni cliente de escritura Hevy.

## Pruebas

Los tests usan `TestModel` de PydanticAI y no necesitan red ni API keys. Cubren salida válida,
esquema inválido, campos extra, rangos inválidos, evidencia inventada y persistencia/aprobación
local sobre PostgreSQL.
