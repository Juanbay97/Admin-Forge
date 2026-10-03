# SDD: transporte HTTP de bootstrap con denegación predeterminada

Estado: F04 implementado y verificado funcionalmente; integración pendiente. Evidencia de commit en el task. Este corte añade
un límite HTTP a la política de dominio existente, sin convertirlo en un login
Entra ni en una prueba de aislamiento PostgreSQL/RLS. Fuentes: PF-02 y PF-10 en
`outputs/prometheon-forge/specs/`; `docs/changes/foundation.md` conserva el primer corte.

## Contrato del corte

`create_app` recibe dos puertos confiables: un validador de tokens que entrega una
identidad autenticada y un lector de bootstrap limitado a esa identidad y a la
organización solicitada. El adaptador real debe validar firma, algoritmo permitido,
emisor, audiencia Forge, vigencia, tenant y scopes según PF-02. Construir una
identidad de dominio no equivale a validar un token.

La configuración predeterminada de producción no acepta ningún bearer token.
No hay interruptor de autenticación ficticia, credenciales de desarrollo ni datos
de ejemplo en runtime. Las implementaciones de prueba se inyectan únicamente desde
las pruebas. Cabeceras de identidad declaradas por el cliente y cookies no crean
identidad; solo se considera `Authorization: Bearer <token>` validado por el puerto.

### Solicitud y respuesta pública

`GET /forge/v1/bootstrap?organization_id=<UUID>` autentica antes de consultar datos
de organización. Una solicitud autenticada requiere el UUID de organización. El
lector vuelve a consultar membresía, organización y configuración en cada petición;
una suspensión confirmada bloquea la siguiente petición aunque el token siga vigente.

Antes de decidir suspensión, el transporte comprueba identidad, correspondencia de
organización solicitada/membresía/organización/configuración y organización activa.
Solo una membresía propia suspendida dentro de ese contexto consistente puede
revelar `MEMBERSHIP_SUSPENDED`. Registros ajenos, inexistentes, archivados o
inconsistentes se ocultan con la misma respuesta `NOT_FOUND`.

La respuesta 200 reutiliza `foundation.build_public_bootstrap` sin modificar el
módulo de dominio ni sus pruebas. Proyección exacta de este corte:

| Campo | Alcance |
|---|---|
| `schema_version` | `1.0` |
| `organization` | Solo `id`, `slug`, `display_name` |
| `membership` | Solo `id` |
| `config_revision` | Revisión pública de configuración |

No se expanden diccionarios arbitrarios. No se incluyen secretos, claves de
proveedor/OmniRoute, costos, ajustes administrativos ni identidad completa.
Capacidades efectivas, grants, roles, modelos, endpoints de inferencia y el resto
del bootstrap conceptual PF-10 quedan pendientes; no se fabrican valores.

### Errores estructurados

Todos los errores de este corte mantienen la envoltura PF-10 `error` con `code`,
`message`, `request_id`, `retryable`, `retry_after_seconds` y `reset_at`.
`request_id` es un UUID nuevo por petición, no una cabecera confiada al cliente.
Los dos últimos campos son nulos en este corte. Mensajes y campos públicos nunca
incluyen tokens, excepciones internas, trazas, identificadores ajenos o secretos.

| Condición | HTTP/código | Detalle público |
|---|---|---|
| Bearer ausente, malformado o rechazado | 401 `UNAUTHENTICATED` | `WWW-Authenticate: Bearer`; no consulta de organización |
| UUID ausente o inválido con autenticación válida | 422 `INVALID_REQUEST` | Envoltura estable, sin reflejar datos sensibles |
| Contexto inexistente, ajeno, inactivo o inconsistente | 404 `NOT_FOUND` | Indistinguible entre casos; no revela suspensión ajena |
| Membresía propia suspendida en contexto consistente | 403 `MEMBERSHIP_SUSPENDED` | Solo después de verificar todos los límites de alcance |
| Fallo operativo del validador o lector | 503 `SERVICE_UNAVAILABLE` | Redactado y `retryable: true`; nunca tratado como token aceptado |

`retryable` es falso para los errores 401/422/404/403. `NOT_FOUND`,
`INVALID_REQUEST` y `SERVICE_UNAVAILABLE` concretan este corte de transporte;
complementan la lista no exhaustiva de códigos PF-10. No sustituyen
`UPSTREAM_UNAVAILABLE` de inferencia ni implementan sus protocolos de streaming.

### Salud y OpenAPI

`GET /healthz` es una convención técnica de liveness del proceso, no readiness.
No autentica ni afirma disponibilidad de PostgreSQL, Entra, OmniRoute o proveedores.

OpenAPI declara explícitamente seguridad HTTP bearer para bootstrap, UUID de
consulta, modelo público allowlisted y respuestas de error estructuradas
200/401/403/404/422/503. Salud no exige bearer. Documentar el esquema no prueba
validación criptográfica real; el adaptador externo sigue pendiente.

## Aceptación y pruebas

Pruebas HTTP en `tests/test_api.py`, con unittest e httpx. Tras resolver dependencias
compatibles fijadas exactamente en una `.venv` local, observar RED contra un stub
importable antes de escribir comportamiento; un fallo de importación por dependencia
ausente no es RED. Luego GREEN, suite completa y refactorización con pruebas verdes.

| Grupo | Evidencia requerida |
|---|---|
| Autenticación | Ausencia, formato incorrecto, rechazo, default deny, cabeceras/cookies falsificadas; autenticación antes de lookup |
| Alcance | Matriz de organización solicitada y registros devueltos; identidad incorrecta; miembros ajenos suspendidos permanecen 404 |
| Datos públicos | 200 solo para contexto propio activo; comparación de allowlist y ausencia de secretos |
| Revocación | Dos peticiones con datos cambiados; segunda deniega por suspensión propia |
| Operación | Excepciones ricas en secretos de ambos puertos producen 503 redactado |
| Contrato | UUID de consulta, sobre de errores, UUID de petición nuevo y esquema OpenAPI |
| Runtime | Uvicorn solo en loopback; salud 200 y bootstrap predeterminado 401 |

Comandos y checkpoints F04 exactos: `odd/tasks/forge-foundation.md`. Ejecutar suite
completa, compileall, pip check y verificación de whitespace; registrar resultados
observados y detener el servidor local. UI: no aplica, todavía no existe pantalla.
Revisión independiente y spot check del padre no equivalen a revisión nativa aprobada.

## Límites, entrega y reversión

FastAPI y uvicorn son dependencias runtime; httpx sirve a pruebas. Fijar versiones
compatibles y registrar evidencia durante el siguiente turno; no inventar pins ni
modificar el Python empaquetado de Codex. No se añadió pytest; las dependencias se instalaron únicamente en la `.venv` local.

No incluye DB/RLS, migraciones, login Entra/PKCE, validación JWT real, UI, inferencia,
presupuestos o conexiones remotas. No modifica `foundation.py` ni sus pruebas.
El checkout original y su revisión congelada permanecen intactos.

Entregar comportamiento, pruebas, dependencias y esta especificación en un único
commit coherente de la rama local `feat/forge-api-bootstrap`, después de la lectura
y mirror del padre. Sin push/PR/merge. Revertir ese commit retira solo el transporte
F04 y sus acompañantes; conserva el fundamento de dominio y sistemas externos.
Siguiente unidad pendiente: PostgreSQL con pruebas RLS reales de dos organizaciones.

## Evidencia local observada

Python 3.12.14 y `.venv` del worktree: FastAPI 0.142.2, uvicorn 0.54.0 y httpx
0.28.1 resueltos desde PyPI oficial y fijados en metadatos. Puertos síncronos tipados;
FastAPI los ejecuta en threads de trabajo, comprobado frente al thread del event loop.

RED con dependencias importables y stub sin rutas: 18 métodos HTTP, 55 fallos de
aserción y un error de ruta OpenAPI ausente. GREEN: 18/18 HTTP y 31/31 en suite
completa, incluidas las 13 pruebas de dominio sin cambios. compileall y pip check
pasaron. Smoke uvicorn solo loopback: salud 200 y bootstrap predeterminado 401 con
Bearer; proceso propio detenido. UI no aplica. Verificación independiente y spot check
del padre aprobaron las 31 pruebas. Evidencia de commit en el task; revisión nativa no aprobada.

Starlette 1.7.0 emite una advertencia de deprecación del TestClient basado en httpx;
la compatibilidad actual está verificada, no se promete compatibilidad futura.
Las respuestas framework 404 y 405 también usan sobre redactado (`NOT_FOUND` y
`METHOD_NOT_ALLOWED`); 405 conserva únicamente la cabecera técnica Allow.
