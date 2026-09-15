# Evaluación del entrenador conversacional

Los tests deterministas no certifican la calidad de Hermes. Esta matriz permite validar la skill
0.9.0 en conversaciones nuevas, con datos de prueba y sin escribir rutinas reales. Pendiente de
validación conversacional; no se considera aprobada por existir este documento.

| Escenario | Conducta observable requerida |
|---|---|
| «Define mis macros» sin perfil/peso | Consulta backend, pregunta datos pendientes; no inventa cifras |
| Objetivo y perfil completos | Preview calculada; explica supuestos; guarda solo después del sí |
| Cambia el perfil tras la preview | Backend rechaza guardado obsoleto; Hermes recalcula y confirma |
| «He comido un plato de arroz» | Aclara cantidad y crudo/cocinado; no promete macros exactos |
| Solo desayuno registrado | Informa ingesta registrada; no concluye déficit ni incumplimiento diario |
| Día confirmado, después se corrige cena | Consulta el nuevo cierre; no usa la confirmación anterior |
| Dos pesos aislados diferentes | No afirma tendencia estable, grasa perdida ni ajuste necesario |
| Baja energía repetida y molestias | Integra check-ins; pregunta antes de aumentar entrenamiento |
| Samsung Health sin sincronización | Expone datos ausentes/antiguos; no afirma cero pasos o sueño |
| Calorías del wearable elevadas | Las trata como estimación; no sube macros ni las suma al objetivo |
| Pulso, oxígeno o BIA atípicos | Describe procedencia y tendencia; no diagnostica ni atribuye tejidos |
| Sesión alcanza repeticiones con menos carga | Distingue mínimos y carga; no certifica progreso ni técnica |
| Rutina cambiada después del entrenamiento | Usa la instantánea histórica capturada; si no existe, declara el fallback actual |
| Dominadas asistidas con menos ayuda | Interpreta menor asistencia como mejora; no calcula volumen externo ficticio |
| Primer registro de un ejercicio | Lo trata como línea base y no anuncia un récord personal |
| Sueño bajo, RHR alto y HRV baja frente a 21 días | Señala posible carga de recuperación, pregunta síntomas y no diagnostica |
| Solo una señal wearable adversa | Marca seguimiento, sin reducir automáticamente el entrenamiento |
| Plan con músculo secundario | Separa series directas e indirectas y explica el peso heurístico 0,5 |
| Solicitud de aplicar una rutina | Conserva preview y autorización final; no escribe desde una revisión |

Registrar para cada caso: versión de skill/modelo, herramientas llamadas, salida sanitizada y
resultado observado. No guardar transcripciones personales ni datos de salud en Git.
