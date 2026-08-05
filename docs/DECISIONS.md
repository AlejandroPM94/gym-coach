# Registro de decisiones

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
