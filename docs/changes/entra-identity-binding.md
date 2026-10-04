# Vinculación persistente de identidades Entra: F07a

## Estado y resultado esperado

**Cierre funcional completo; entrega local autorizada.** El padre liberó código
después del espejo 2468 y su relectura completa. Writer142 y verificación
independiente142 aplicable pasaron; la comprobación final del padre pasó73 DB
en13.492s sobre PostgreSQL17.11 y confirmó limpieza por ID exacto. El hash real
del commit local se registra en el task después de su creación.

F07a vincula explícitamente una identidad existente con su par verificado
(tenant de recurso, objeto Entra). No crea identidades, usuarios, invitaciones
ni membresías. F06 ya valida tokens; validar un token no equivale a autorizar
vinculación o acceso a una organización.

## Lectura rápida

1. Revisar la migración aditiva y sus restricciones.
2. Revisar el adaptador interno, su rol restringido y el cierre del lector.
3. Comprobar RED → GREEN real en PostgreSQL, actualización y rollback transaccional.
4. Obtener verificación independiente y comprobación del padre antes del commit.

## Persistencia y compatibilidad

La nueva migrations/0002_entra_identity_binding.sql preserva 0001_bootstrap.sql.
Añade UUID anulables entra_tenant_id y entra_object_id a forge.identities.

| Invariante | Regla |
|------------|-------|
| Par completo | Ambos NULL o ambos no NULL, mediante ramas explícitas IS NULL / IS NOT NULL. |
| Par presente | provider = entra; issuer exactamente https://login.microsoftonline.com/<tid>/v2.0; subject = representación canónica de oid. |
| Unicidad | Un par tid/oid solo corresponde a una identidad; los pares ausentes conservan las filas genéricas existentes. |
| Escritura única | Un trigger SECURITY INVOKER permite la primera vinculación coherente y su repetición idéntica; impide borrar o cambiar metadatos vinculados, incluso mediante otras columnas de identidad. |
| Identidad estable | No cambia UUID, provider, issuer, subject ni claves de membresía; no migra por correo, sub, idp ni heurísticas. |

Las filas Entra existentes sin par quedan sin vincular y no obtienen bootstrap.
La migración no deduce ni rellena metadatos a partir de cadenas existentes.
Los invitados conservan el objeto del tenant de recurso. Un oid igual en otro
tenant sigue siendo una identidad diferente.

## Puerto interno y autorización

src/forge/identity_store.py expone bind_existing(existing_identity_uuid,
VerifiedPrincipal), separado del lector. La identidad solicitada debe existir y
coincidir exactamente con el provider/issuer/subject canónico del principal.
Solo se rellena el par, sin INSERT, relink ni escritura de membresías.

VerifiedPrincipal es un contrato interno de entrada confiable después de F06;
construir su dataclass no prueba una firma ni autoriza una operación. La selección
y autorización de la identidad existente corresponden a un llamador interno
explícitamente confiable. No hay endpoint HTTP, conexión automática al login
ni configuración del pool en esta unidad.

El resultado es inmutable y los errores operativos están tipados y redactados.
No se exponen tokens, claims, PII, credenciales ni excepciones de red/SQL sin
sanitizar. La repetición concurrente del mismo vínculo debe ser idempotente;
ningún conflicto permite cambiar un vínculo previo.

## Privilegios, RLS y ciclo del pool

La migración crea forge_identity_binder NOLOGIN como rol separado, sin poderes
administrativos, membresías de roles ni propiedad de objetos. Recibe únicamente
USAGE necesario, SELECT sobre identities y UPDATE de las dos columnas nuevas.
La política original de identidades se limita a runtime/migrator;
el fixture incorpora explícitamente su writer de prueba, no un rol de producción.
No hereda forge_runtime ni tiene INSERT/DELETE o acceso de escritura a otras
tablas. Los helpers son SECURITY INVOKER con search_path
restringido y EXECUTE explícito, sin concesión pública.

El adaptador comprueba current_user/session_user, atributos, membresías,
propiedad, privilegios efectivos, RLS ENABLE/FORCE y conexión inactiva en autocommit.
La vinculación usa una transacción explícita y contexto local de identidad y
principal verificado, con RLS exclusivamente sobre la identidad coincidente.
No exige ni inventa una membresía organizacional para poder rellenar el par.
El contexto no persiste al devolver la conexión; fallos y concurrencia deben
demostrar rollback y limpieza. El pool externo sigue siendo propiedad del
llamador, con esperas y timeouts finitos; no se descubren DSN ni credenciales.

forge_runtime sigue siendo SELECT-only. Su guardia detecta también
privilegios efectivos por columna: has_table_privilege por sí solo no detecta
UPDATE concedido a una columna. La regresión correspondiente es aplicable al
código actual. El lector exige el par coherente solo para provider Entra y
mantiene las comprobaciones de organización/membresía/configuración existentes.

## Prueba observada y cierre pendiente

- RED conductual contra PostgreSQL real antes de GREEN; no contar importaciones
  fallidas como RED.
- Ejecutar explícitamente 0001 → 0002 en instalación limpia; probar actualización
  con filas genéricas y Entra preexistentes, y rollback transaccional.
- Probar pares parciales, coherencia, unicidad, escritura única, privilegios/RLS,
  rechazo de roles o conexiones inseguros y repetición concurrente.
- Probar cero creación/relink/membresía, contexto limpio tras éxito/fallo,
  lector y API bloqueados antes de vincular, y membresía aún requerida después.
- Conservar los 113 tests previos; ejecutar todos los nuevos, compileall,
  pip check y git diff --check sin omitir fallos o skips.

tests/postgres_support.py aplica las migraciones en orden explícito y usa
columnas explícitas en INSERT de fixtures genéricos. El login del binder tiene
contraseña aleatoria solo en el proceso/harness desechable. Se reutilizó el
Docker propio con imagen fijada ya disponible; no se alteró el script ni se instalaron
dependencias, usaron bases existentes o realizaron accesos Entra reales.

Prueba PostgreSQL17.11: RED46 métodos/4 fallos de aserción sin errores, GREEN46,
ampliación67,72 originales y73/73 después de ampliar evidencia, sin skips. RED mostró bootstrap Entra sin vínculo y
grants por columna no detectados. Total actual142 =73 DB+38 Entra+13 dominio+18 HTTP.
compileall, pip check y diff check: exit0. Cada contenedor propio fue eliminado
y su ausencia confirmada por ID exacto. Warning TestClient/httpx sin ocultar.

Las cuatro pruebas de migración usan bases temporales distintas dentro del cluster
propio: instalación limpia, actualización con identidades genéricas/Entra y
membresía existentes, rollback explícito y fallo SQL antes de COMMIT. Ejecutan
las instrucciones originales; el rollback cambia COMMIT final a ROLLBACK en
memoria, mientras la cuarta prueba inserta SELECT1/0 antes del COMMIT original.
Observa SQLSTATE22012/INERROR y después ROLLBACK/IDLE; verifica también políticas
y funciones sin cambios. El rollback explícito no se presenta como prueba de fallo.
Ambas pruebas verifican filas/UUIDs intactos,
metadatos ausentes, cuatro tablas RLS ENABLE/FORCE y rollback del rol/columnas.
Cada caso elimina solo su base capturada y roles creados; no una base existente.
Los guards de runtime/binder también rechazan REFERENCES concedido solo a las
dos columnas del par. Las pruebas RLS existentes cubren contexto propio, parcial,
malformado y ajeno sin ampliar alcance por contexto organizacional.
La API usa un puerto de identidad sintético de prueba con lector DB real; la
criptografía JWT real sigue probada por F06, no se atribuye a este puerto.

El probe opcional combinado del verificador quedó bloqueado antes de SQL por
su espera de readiness15s; no produjo veredicto y no se repitió ese wrapper.
La ampliación durable usó el harness existente:73 DB en14.420s y todos los
controles, exit0. El recheck independiente73 DB y los69 offline previos completan
142 checks aplicables; la comprobación final73 del padre también pasó.

## Límites y brecha de despliegue

0002 establece lock_timeout2s y statement_timeout10s dentro de su transacción.
El binder limita adquisición a1s configurable (0,30], lock local1s y statement5s.
Pruebas demuestran espera acotada, rollback posterior a UPDATE y restauración de
contexto/timeouts en el mismo backend. No son una garantía total de latencia.
No se implementó runner de migración, tracking de versiones, provisioning LOGIN,
composición de pools ni downgrade seguro de datos vinculados.

## Entrega y exclusiones

Las rutas y comandos exactos están en el documento del feature. Estimación F07a:
1000–1600 líneas autoradas, incluidas pruebas y documentación; 400 es una
heurística, no un límite ni motivo para omitir claridad. Un commit coherente
agrupará migración, adaptadores, pruebas y documentación tras verificación independiente,
comprobación y autorización del
padre; el commit local ya está autorizado. El rollback de una migración
fallida se probó dentro de su transacción; ningún downgrade destructivo queda
autorizado.

F07b queda separado: creación, invitaciones, confirmación de objetos y provisioning.
F08 composición/readiness y F09 PKCE/almacenamiento/enrollment siguen pendientes.
Gentle AI está GLOBALOFF: sin llamadas ni aprobación nativa.

## Evidencia y fuentes

Diseño del explorador: observación 2483; aceptación del padre: 2485. Baseline local:
4ab2d40c8c3a1e80cbb0106c917804fed949e881. La aceptación no constituye prueba funcional.

La semántica de privilegios por columna se verificó en
[PostgreSQL17: funciones de información](https://www.postgresql.org/docs/17/functions-info.html).
Las ramas explícitas evitan que NULL eluda un CHECK, conforme a
[PostgreSQL17: restricciones](https://www.postgresql.org/docs/17/ddl-constraints.html).
