# Configuración manual de Hermes

Hermes será inicialmente la interfaz conversacional y `gym-coach` seguirá siendo el backend y la
fuente de verdad. Esta guía no instala Hermes ni modifica `~/.hermes/` automáticamente.

## 1. Instalar en WSL

Desde la misma distribución WSL donde está este repositorio:

```bash
curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash
source ~/.bashrc
hermes doctor
```

Es el flujo vigente para Linux/WSL2 en la
[documentación oficial de instalación](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/getting-started/installation.md).
Conviene revisar el script antes de ejecutarlo.

## 2. Autenticar OpenAI Codex

Usa una de estas rutas interactivas:

```bash
hermes auth add openai-codex
# o
hermes model
```

En el selector, elige **OpenAI Codex** y completa el device-code login de ChatGPT. Hermes guarda sus
propias credenciales en `~/.hermes/auth.json`; no deben copiarse al repositorio. Este flujo usa acceso
Codex autenticado por la suscripción de ChatGPT y no una API key. No es ilimitado: está sujeto al plan
y a sus límites. La documentación de Hermes todavía no especifica exactamente qué contador de cuota
consume, por lo que debe comprobarse en la cuenta de OpenAI. Véase la
[tabla oficial de proveedores](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/integrations/providers.md#subscription-plans-what-your-plan-pays-for).

Mantén el bucle de agente normal de Hermes. No actives inicialmente **Codex App-Server Runtime**: es
una alternativa opt-in y limita algunas funciones propias de Hermes, incluida la memoria durante el
turno. Puede reevaluarse más adelante. Consulta la
[documentación del runtime opcional](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/codex-app-server-runtime.md).

## 3. Registrar el servidor MCP local

La opción más segura es dejar que Hermes escriba su propia configuración:

```bash
hermes mcp add gym-coach --command uv --args \
  --directory /home/alexpm/code/gym-coach run gym-coach mcp
```

El comando exacto que Hermes ejecutará es:

```bash
uv --directory /home/alexpm/code/gym-coach run gym-coach mcp
```

Como alternativa, revisa y fusiona manualmente
`config/hermes/mcp-server.example.yaml` en `~/.hermes/config.yaml`. El formato `mcp_servers`,
`command` y `args` corresponde a la
[configuración MCP oficial de Hermes](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/mcp.md).
No copies `HEVY_API_KEY` a la configuración de Hermes: el proceso arranca en el directorio del
proyecto y `gym-coach` carga su `.env` local.

## 4. Preparar la skill, opcionalmente

El ejemplo está en `integrations/hermes/skills/gym-coach/SKILL.md` y sigue el
[formato oficial de skills](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/skills.md).
Revísalo y, si estás conforme, cópialo manualmente:

```bash
mkdir -p ~/.hermes/skills/health/gym-coach
cp /home/alexpm/code/gym-coach/integrations/hermes/skills/gym-coach/SKILL.md \
  ~/.hermes/skills/health/gym-coach/SKILL.md
```

## 5. Verificar

Ejecuta desde WSL:

```bash
cd /home/alexpm/code/gym-coach
docker compose up -d postgres
uv run alembic upgrade head
uv run gym-coach hevy sync
hermes mcp list
hermes mcp test gym-coach
hermes chat
```

Consulta de prueba:

> Consulta mi último entrenamiento usando gym-coach y resúmelo sin proponer todavía modificaciones.

Hermes debe descubrir 18 herramientas. Para la consulta de prueba debe usar
`get_recent_workouts` y después `get_workout`; no debe afirmar que ha modificado Hevy.

Para validar el onboarding, inicia una conversación nueva y pide configurar tu perfil. Hermes debe:

1. llamar a `get_onboarding_status`;
2. preguntar únicamente por los campos pendientes;
3. mostrar un resumen estructurado antes de guardar;
4. preguntar explícitamente por dolor/lesiones, ejercicios problemáticos y preferencias, y registrar
   la revisión aunque la respuesta sea «ninguno»;
5. pedir confirmación explícita;
6. llamar a `save_confirmed_athlete_profile` y después a las herramientas confirmadas de objetivos;
7. consultar `get_training_metrics` antes de interpretar volumen, adherencia o estancamiento.

La creación de un plan requiere una petición explícita del atleta y solo genera un borrador local.
`decide_training_plan_proposal` registra una aprobación o rechazo confirmado, pero nunca escribe en
Hevy. Cada cambio necesita una justificación y evidencias vigentes. Las sesiones opcionales deben
marcarse como tales; planchas, cardio y otros ejercicios temporales usan duración o distancia, no
repeticiones ficticias.

## Diagnóstico

- **`uv: command not found`:** instala uv o añade su directorio al `PATH`; comprueba `uv --version`.
- **Directorio incorrecto:** usa exactamente `/home/alexpm/code/gym-coach` o adapta tanto
  `--directory` como el YAML de ejemplo.
- **`.env` no encontrado:** crea `/home/alexpm/code/gym-coach/.env` localmente; no lo copies a
  `~/.hermes/` ni lo confirmes en Git.
- **El servidor termina al arrancar:** ejecuta `uv run gym-coach mcp --help`, después
  `hermes mcp test gym-coach`; ningún texto de diagnóstico debe escribirse en stdout del servidor.
- **Autenticación Codex caducada:** ejecuta de nuevo `hermes auth add openai-codex`.
- **PostgreSQL no accesible:** comprueba `docker compose ps` y que `postgres` figure `healthy`.

## Imágenes

Hermes puede recibir imágenes si el modelo activo admite visión. `gym-coach` no recibe, almacena ni
analiza imágenes en esta fase. Las fotografías de progreso son datos sensibles y no deben
persistirse en el backend sin consentimiento explícito.
