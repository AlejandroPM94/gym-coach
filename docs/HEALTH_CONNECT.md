# Exportación automática de Health Connect mediante Google Drive

Samsung Health escribe actividad, sueño y señales del reloj en Health Connect; openScale sync puede
escribir peso y composición corporal estimada. Android exporta periódicamente sus datos a
`Health Connect.zip` dentro de una
carpeta privada de Google Drive. `gym-coach` consulta esa carpeta, descarga solo revisiones nuevas y
normaliza los últimos 30 días en PostgreSQL.

No se abre ningún puerto en el ordenador y no hay una app Android propia. Al desplegar el backend,
se trasladan las mismas variables y credenciales; la configuración del teléfono no cambia.

## Contrato del importador

- Google Drive se consulta en modo lectura. Se busca exactamente `Health Connect.zip` dentro del ID
  de carpeta configurado; no se selecciona por nombre de carpeta ni se recorre todo Drive.
- La autenticación usa una cuenta de servicio independiente. Aunque solicita el scope técnico
  `drive.readonly`, Google Drive limita los archivos visibles a los compartidos con esa identidad.
  La carpeta `gym-coach-health` debe compartirse con ella como lectora.
- Se comprueban tamaño declarado, MD5 de Drive cuando está disponible, CRC y disposición del ZIP,
  integridad SQLite, tablas/columnas necesarias y versión del esquema. La versión admitida es 26;
  cualquier versión nueva se detiene hasta revisar el contrato.
- El ZIP debe contener únicamente `health_connect_export.db`. Se limita a 256 MiB comprimidos,
  512 MiB descomprimidos y una razón de compresión máxima de 50 para evitar archivos abusivos.
- Para actividad y recuperación solo se leen registros cuyo paquete de origen sea Samsung Health
  (`com.sec.android.app.shealth`). Para peso y grasa BIA solo se admite openScale sync
  (`com.health.openscale.sync` y `com.health.openscale.sync.oss`). Google Fit y las demás
  aplicaciones quedan excluidas para evitar duplicados; cada tipo mantiene su procedencia.
- Los registros históricos de talla, peso y BMR escritos por Samsung no sustituyen el perfil
  confirmado ni los pesajes de openScale: suelen ser copias derivadas y crearían doble procedencia.
- Se normalizan por fecha local pasos; sesiones y fases de sueño; sesiones y tipos de ejercicio;
  distancia; energía total; frecuencia cardiaca; frecuencia cardiaca en reposo; HRV RMSSD; oxígeno
  y VO2 máx. Las series de pulso y oxígeno se resumen de forma determinista y no se conservan como
  miles de muestras en el contexto del agente. No se importan rutas GPS, nutrición ni historias
  clínicas. La energía del wearable es informativa y nunca ajusta por sí sola los macros.
- Los pesajes conservan su hora original. Las masas se convierten de gramos a kilogramos y el BMR
  de vatios a kcal/día. Se conservan grasa, masa magra, agua, hueso y BMR de openScale con procedencia;
  salvo el peso, son estimaciones descriptivas de BIA y no gobiernan objetivos ni cambios de rutina.
- La zona horaria se configura explícitamente; el valor predeterminado es `Europe/Madrid`.
- Solo se importan los últimos 30 días del ZIP. Una revisión de Drive se identifica mediante ID de
  archivo, versión del contrato importador y MD5, o fecha/tamaño cuando Drive no devuelve MD5.
  Repetirla no descarga ni duplica datos; ampliar el contrato permite releer una revisión una vez.
- PostgreSQL sigue siendo la fuente de verdad para Hermes. El agente nunca abre el ZIP ni consulta
  Google Drive directamente.

## Configuración de Google Drive

1. Conserva la exportación diaria de Health Connect en la carpeta `gym-coach-health`.
2. En Google Cloud crea o selecciona un proyecto personal y activa **Google Drive API**.
3. Crea una cuenta de servicio exclusiva, sin roles de proyecto adicionales. Genera una clave JSON.
4. Guarda el JSON fuera de Git, por ejemplo:
   `.local/google-drive/gym-coach-health-reader.json`, con permisos de lectura solo para tu usuario.
5. Copia el `client_email` del JSON. En Drive comparte `gym-coach-health` con ese correo como
   **Lector**. No compartas el enlace públicamente ni concedas acceso al resto de Drive.
6. Abre la carpeta en Drive y copia su ID: es el tramo que aparece después de `/folders/` en la URL.
7. Configura en `.env`, sin enviar los valores al chat ni registrarlos en Git:

   ```dotenv
   GYM_COACH_GOOGLE_DRIVE_SERVICE_ACCOUNT_FILE=.local/google-drive/gym-coach-health-reader.json
   GYM_COACH_GOOGLE_DRIVE_HEALTH_FOLDER_ID=ID_DE_LA_CARPETA
   GYM_COACH_GOOGLE_DRIVE_HEALTH_FILENAME=Health Connect.zip
   GYM_COACH_HEALTH_TIMEZONE=Europe/Madrid
   ```

8. Comprueba una importación manual:

   ```sh
   uv run gym-coach automation sync-health-drive
   ```

   Devuelve `imported`, `unchanged` o `not_found`, la fecha de la revisión y el número de días
   aceptados; no imprime el contenido del ZIP, credenciales, pasos ni sueño.

## Automatización

El repositorio incluye unidades de usuario en `integrations/systemd/`. Tras validar la importación
manual, instálalas mediante enlaces para conservar una única copia versionada:

```sh
mkdir -p ~/.config/systemd/user
ln -sf "$PWD/integrations/systemd/gym-coach-health-drive.service" ~/.config/systemd/user/
ln -sf "$PWD/integrations/systemd/gym-coach-health-drive.timer" ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now gym-coach-health-drive.timer
```

El timer consulta Drive aproximadamente cada hora; la exportación de Android sigue siendo diaria.
Si PostgreSQL, la red o Drive no están disponibles, el intento falla y el timer vuelve a ejecutarse
en su siguiente intervalo. Consulta estado y ejecuciones con:

```sh
systemctl --user status gym-coach-health-drive.timer
journalctl --user -u gym-coach-health-drive.service --since today
```

Los mensajes operativos no contienen datos de salud. La frescura real se comprueba mediante
`get_weekly_coaching_review.activity.last_observed_at`.

## Limitaciones

- El formato SQLite es interno y no está documentado como API estable. El bloqueo por versión evita
  una interpretación silenciosa si Google lo cambia, pero puede requerir adaptar el importador.
- La fecha de sueño corresponde al día local en el que comienza la sesión. Se separa la ventana de
  sesión del tiempo clasificado dormido y sus fases; ninguna fase demuestra por sí sola recuperación.
- Pulso, oxígeno, VO2 máx., gasto energético y composición son estimaciones de consumo: sirven para
  observar tendencias y no para diagnosticar ni para sustituir una medición clínica.
- La composición de una báscula doméstica depende de su algoritmo y condiciones de medida. El peso
  alimenta tendencias; la grasa BIA es secundaria y no representa un valor exacto.
- La exportación programada puede retrasarse. Ausente significa desconocido, nunca cero.
- La cuenta de servicio y su clave son credenciales sensibles. Revocar la clave o retirar el acceso
  a la carpeta detiene la sincronización sin borrar datos ya importados.

Fuentes oficiales consultadas:

- [Exportar y restaurar Health Connect](https://support.google.com/android/answer/15323271?hl=es-US).
- [Scopes y acceso limitado de Google Drive](https://developers.google.com/workspace/drive/api/guides/api-specific-auth).
- [Descarga de archivos de Drive](https://developers.google.com/workspace/drive/api/guides/manage-downloads).
