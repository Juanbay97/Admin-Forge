# F07b2a: designación central inicial de administrador

## Estado y decisión

Implementación interna verificada:266 pruebas del escritor y266 independientes
pasan sin defecto concreto; spot del padre147DB30.482s/17.11 y limpieza por ID
exacto pasan. Entrega local autorizada; commits/estado se registran en el task.
El padre liberó fuente después de releer espejo2534 completo coincidente. Línea
base96e29200460df7b6f3f220c24f7f3064bac5ab71; decisión central confirmada por el
usuario2549, alcance2553/exploración2550. Sin configuración real del operador,
HTTP/UI ni despliegue productivo. Gentle desactivado globalmente;
sin llamadas, aprobación nativa ni operaciones remotas.

El servicio interno designa el primer organization_admin únicamente sobre una
membresía existente activa y una identidad Entra vinculada coherentemente. No crea
identidad/membresía, no vincula cuentas, no activa empresa ni cambia lifecycle.
No entrega endpoint, interfaz administrativa, configuración real de operadores,
credenciales/pool de despliegue ni publicación de auditoría/provisión externa.

## Contrato de autoridad y entradas

| Elemento | Decisión |
|---|---|
| Autenticación | Servicio llama al EntraTokenValidator real con token crudo en CADA intento, también replay. RS256/claims/límites ya implementados; construir VerifiedPrincipal no constituye autoridad |
| Operador | Allowlist inmutable de despliegue con issuer/tid/oid exactos y actor UUID interno confiable asociado. Configuración ausente/vacía o principal no autorizado deniega antes de DB |
| Organización/tenant | Mapa explícito inmutable organización→tenants Entra admitidos para el destino. No sustituirlo por allowlist global del validador. Organización sin mapa deniega antes de DB |
| Solicitud | UUID de organización, membresía y operación; expected_revision positivo tipado. Sin actor/roles/tenant/email/identidad declarados por el request |
| Destino | Membresía activa exacta de esa organización, provider entra, par tid/oid persistido completo, issuer tenant-v2 exacto y subject oid canónico; tenant presente en mapa de esa organización |
| Empresa inactiva | Puede recibir intención válida de designación inicial, pero permanece inactiva y el runtime continúa denegando acceso |
| Replay | Reautenticar/reautorizar token y configuración actual; actor+operación+payload original exactos recuperan resultado original sin otra revisión/rol/evento. Revalidar mapa actual contra tenant destino almacenado |
| Conflictos | Actor/payload distintos, operación reutilizada, revisión obsoleta, marcador previo o cualquier organization_admin ya existente impiden nueva designación |

El servicio copia/congela configuración: máximo64 operadores,256 mapas de empresa y
64 tenants por mapa; validar GUID/issuer canónicos y entradas duplicadas/ambiguas.
Sin configuración ambiental/defaults, trust por primer login/tenant-admin/roles JWT,
email matching o IDs corporativos reales. Cada tuple validada tiene actor UUID
interno explícito; request nunca selecciona ese actor. Parámetros UUID tipados y
revision entera exacta, sin bool/coerción/NaN/inf/entero gigante, máximo2**63-2 para
incremento válido bigint. Errores fijos tipados y redactados, sin token/PII/causa SQL.
Resultado inmutable con organización/membresía/operación/evento/revision committed;
audit_publication=pending, no falsa publicación. Port de almacenamiento interno
confía únicamente en composición del servicio, no en dataclass de un llamador externo.

## Transacción inicial, permanente e idempotente

1. Validar token real, allowlist y existencia del mapa antes de tomar conexión.
2. Abrir transacción limpia; cargar metadata de destino acotada si hace falta.
   La primera escritura reclama org/operación mediante INSERT del marcador único.
   Competidores esperan esa unicidad; después del conflicto, replay exacto devuelve
   resultado guardado o conflicto. No crear marcador de error fuera de transacción.
3. Bloquear/releer membresía FOR UPDATE con privilegio UPDATE solo de revision;
   volver a validar estado, identidad vinculada, tenant, organización y revisión.
   Verificar que NO exista ningún rol organization_admin en la organización.
4. Insertar ese rol al destino, incrementar revisión, insertar evento/outbox real y
   confirmar junto con el marcador. Error de cualquier escritura revierte TODO.

Marcador initial_admin_designations append-only: una organización, operación global
única, actor/request/target/targettenant/revisiones esperada y resultante y evento.
Tenant procede de identidad persistida validada, nunca del request; cualquier lectura
preliminar se revalida bajo lock. Marcador permanente impide reabrir bootstrap si
más adelante se elimina el rol. Replay tras pérdida de respuesta o cambios posteriores
de lifecycle conserva resultado original, sujeto a autoridad/configuración vigente.
Cambiar payload/revision del replay no es otra mutación: conflicto.

Outbox y marcador tienen claves/relaciones que impiden commit de marcador sin evento;
comprobación diferida al commit permite su escritura atómica. No UPDATE/DELETE de
marcador/evento, reparación silenciosa ni camino de recuperación. Concurrencia de
dos destinos misma empresa, mismo replay, suspensión del destino y empresas distintas
se verifica con DB real; resultados deben corresponder a órdenes seriales válidos.
No imponer política de último administrador o remoción no definida en este corte.

## Evento PF09 y publicación pendiente

PF09 requiere event_id, schema_version, organization_id, actor_id, actor_type, source,
event_type, occurred_at, received_at, request_id, resource_type, resource_id, outcome,
metadata allowlisted; servidor fija actor/organización de eventos autenticados.
Aquí actor_id es UUID interno del allowlist que coincidió con principal validado,
actor_type=deployment_operator, source=server, event_type=membership.initial_admin_designated,
schema_version=1, resource_type=membership y outcome=succeeded. UUID de evento y
marcas de tiempo se generan en servidor; request_id es operación validada y
resource_id membresía validada. Metadata exacta/bounded de rol y revisión, sin
sub/token/email/claims libres/PII o valores arbitrarios del request.

Outbox se inserta en la misma transacción del cambio como exige PF09. Consumidor,
publicación/deduplicación downstream y entrega son trabajo futuro; no llamar esta
inserción aprovisionamiento o entrega. No tabla universal de auditoría ni worker nuevo.
Fuente: outputs/prometheon-forge/specs/09-auditoria.md, evento base y atomicidad;
PF02 exige proveedores/tenants por empresa; PF10 revisión/membresías; PF11 administración
sin definir recuperación/último administrador. Estos últimos siguen fuera de alcance.

## Privilegios, RLS y readiness

Nueva0004 aditiva preserva bytes0001–0003. forge_designator NOLOGIN sin propietario,
membresías de rol, BYPASSRLS, superuser, DDL o SECURITY DEFINER; LOGIN/pool externo
corresponden al despliegue, no a una credencial inferida. Matriz explícita:

| Rol | Acceso |
|---|---|
| Runtime | SELECT cinco tablas de negocio existentes, cero privilegios de tabla/columna en marcador/outbox o cualquier tabla Forge desconocida |
| Binder | SELECT identities/UPDATE par Entra existentes; cero acceso a nuevas tablas/revision/roles |
| Designator | SELECT metadata de empresa/destino vinculado/rol admin en empresa; UPDATE(revision) exclusivamente; INSERT rol admin al destino; INSERT marcador/outbox y SELECT replay propio actor/request |

Sin SELECT configuration_revisions, creación de identidades/membresías, status/org
UPDATE, UPDATE de tabla completa, auditoría DELETE/UPDATE ni grants al runtime sobre
nuevas tablas. Policies nuevas específicas del designator y policies RESTRICTIVE para
acotar posible OR de policies antiguas PUBLIC, preservando sus cuerpos/semántica para
runtime y probes legacy. EXECUTE mínimo de helpers invoker existentes solo si la
evaluación de esas policies lo exige; no elevar privilegios. Contexto targetidentity
se deriva de membresía validada; policy de identidad no consulta membresías ni crea
ciclo RLS. Rol SELECT limitado a empresa/admin; INSERT limitado destino/admin.
Operacionales limitadas empresa/actor/request/destino; sin contexto no filas.

Guardias reales por préstamo comprueban rol/session/ACL y columnACL/propiedad/
membresía/contexto/idle/autocommit. Contextos nuevos locales y timeout/search_path
se restauran en éxito/error/rollback. Acquire1s opcional finito(0,30], statement3s,
lock1s; migración lock2s/statement10s. Validar rango antes de conversión float. Sin
savepoint sobre transacción sucia, reopen, credencial/DSN ambiental ni cambio global.
Cliente18.4/servidor17.11 son evidencia previa de pruebas, no claim productivo/TLS.

_ROLE_CHECK se adapta a SELECT positivo solo en cinco tablas y matriz cero para
resto, no grant-all. Readiness solo catálogo: formas/PK/FK/CHECK/owner/roles/ACL/RLS,
policies exactas por rol y vínculos marcador-evento, binder cero. Conteo previo de
policy de roles se extiende deliberadamente sin debilitar policies runtime. Ausencia,
policy ampliada, columna/table grant indebido o esquema alterado deniega readiness.
No consulta filas/cuentas de negocio ni conecta la designación a runtime/HTTP.

## Superficies y pruebas tras liberación

Superficies liberadas exactas:
migrations/0004_initial_admin_designation.sql; src/forge/administration.py;
src/forge/administration_store.py; src/forge/postgres.py; tests/test_administration.py;
tests/test_postgres_administration.py; tests/postgres_support.py;
tests/test_postgres_runtime.py; tests/test_postgres_rls.py; README.md;
docs/changes/initial-admin-designation.md; odd/tasks/forge-administration.md.
Salidas ignoradas .local/postgres-test/** y .local/runtime-test/** exclusivamente.
Sin auxiliares, dependencias, .venv ni cambios en API/UI/binder/Entra/readmodel/
manifest/harness/probes previos. No modificación de base existente o externa.

E1–E12 del task cubren autoridad/target/replay/atomicidad/concurrencia/privilegios/
readiness/evento/probes/regresión/wheel/gate. Pruebas significativas RED realRSA y
RED atomicidadDB antes de implementar, luego GREEN/refactor y211 anteriores+nuevas.
RSA efímera solo en memoria y JWKS públicos/transporte falso; no stub de autoridad.
Probes0004 separados fresco/poblado/falloSQL real antes deCOMMIT, INERROR→ROLLBACK/
IDLE y filas/policies/ACL/RLS anteriores exactos. Funciones/probes0002/0003 byte-intactos.
Fixture cuatro migraciones ordenadas y login designator descartable, no credenciales
persistidas. Fallo outbox tras rol/revision demuestra rollback de todas las escrituras.
Reprobar lectores/runtime/zero operational grants/cualquier tabla desconocida/
contaminación de columna, limpieza de conexión y conflictos/races/replay auténtico.

Comandos exactos en task: test_administration, harness original test-postgres.ps1,
test_authorization/test_runtime/test_entra/test_foundation/test_api, compileall,
pipcheck y diffcheck. Harness propio imagen cacheada --pull=never, sin pull/prune,
limpieza ID exacto. Build offline existente --isolated wheel --no-index --no-deps
--no-build-isolation --no-cache-dir con staging y TMP/TEMP del hijo bajo.runtime-test;
ZIP/importación fresca/resources comprueban módulos/assets exactos y0004 se audita
como fuente separada, no claim de SQL en wheel. No UI nueva/navegador requerido;
C10b previo conserva límites de certificación. Pruebas/build observados se resumen abajo; no certificación UI nueva.

Estimación1800–2600 líneas autorales/30–60 pruebas nuevas, guía no aceptación;400
es heurística, nunca motivo de code-golf o división por tipos. Estrategia local
feature-branch-chain: unidad coherente tras verificación independiente/spot/autoridad
de commit separada, seguimiento pequeño de hash real. Checks locales~2–4minutos,
sin descargas/gasto externo. Recuperación DB requiere procedimiento separado; no
downgrade destructivo. READINESS NO significa administrador/interfaz productiva lista.

## Siguiente paso

Padre relee cierre local y actualiza espejo completo; luego decide siguiente
alcance acotado. No se infiere política de recuperación/remoción/último administrador. No IDs reales/credenciales solicitados en esta prueba interna.
Configuración/pool real, HTTP/UI, publicación del outbox, recovery/último administrador,
provisión y lifecycle de miembros siguen futuros. F07b/F09 no se completan aquí.


## Evidencia observada y límites de entrega

266 pruebas:147 PostgreSQL29.983s,16 servicio RSA0.175s,6 autorización0.003s,
28 runtime11.725s,38 Entra0.995s,13 dominio0.001s,18 HTTP0.492s;211 anteriores
más55 nuevas, sin skips en ejecuciones finales. compileall/pipcheck exit0;
diffcheck exit0 tras lectura final. Servidor17.11 propio/cacheado, eliminación
confirmada por ID exacto en cada ejecución. Probes0004 separados fresco/poblado/
falloSQL22012 antes de COMMIT demuestran rollback real y metadata/datos previos
idénticos.37 blobs protegidos y texto de probes0002/0003 coinciden con línea base
considerando filtros Git de finales de línea.

RED RSA y RED DB con servicio autenticado precedieron implementación GREEN. Pruebas
finales demuestran replay con autenticación nueva, marcador permanente, races de
replay/destinos/empresas/suspensión, fallo outbox después de rol/revisión/claim y
rollback total, timeout real y restricciones RLS/privilegios. Dos RED adicionales
mostraron proconfig NULL que eludía comparación y GUC nuevo aceptado por reader
runtime; se corrigieron con IS DISTINCT FROM y guardia compartida. Readiness
conserva espacios literales, fuentes/firmas exactas de helpers y formas de policies/
constraints; controles adversariales cambian literales y comprueban recuperación.

Fallos intermedios de generación/importación/expectativas de fixture, sombra de
helper, conexión retenida, LIKE sin escape al parametrizar y revocación de UPDATE
que quitó también grant de columna están conservados en el task. Token exp NOW-1
seguía válido por skew30s; se corrigió prueba expirada, no validador. Ningún fallo
intermedio se presenta como PASS. Probe wheel inicial consultó ruta inexistente404;
/forge/v1/status real pasó después. Advertencia previa de TestClient/httpx no motivó
instalaciones ni cambios de dependencias.

Wheel offline con herramientas existentes: todos11 módulos fuente y3 assets exactos,
importación fresca/resources y HTTP local sin configuración pasan; SHA256
c7568016ff9a83fdb99cd5eccc257f760accb83c16e0afe4fb37b9c4dc1f3992.
0004 se audita aparte como fuente SHA256
4c458728d8b1cff92f2a449e5b128d7ac49c4f3a322d252bd47f7e04bcbf87d0,
no SQL empaquetado. Sin servidor UI nuevo ni repetición de navegador por assets
intactos; C10b conserva límites previos. E1–E11 tienen evidencia del escritor;
E12 registra cierre local/commits reales y comprobación de estado limpio en el task.
Verificación independiente266 y wheel exacto pasan sin defecto; spot147DB del padre
pasa con limpieza exacta. No aprobación nativa: Gentle sigue desactivado.
Outbox sigue publicación pendiente; configuración/pool/operador real, HTTP/UI,
recovery/removal/último administrador e invitaciones/provisión siguen fuera de alcance.
