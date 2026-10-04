# SDD: migración mínima de bootstrap y prueba PostgreSQL/RLS

Estado: F05a implementado y verificado por el writer con PostgreSQL real;
verificación independiente y spot check correctos; commit local autorizado pendiente.
Revisión nativa F05a pendiente, no aprobada. F05b será otro corte. Este documento
concreta PF-01, PF-02 y PF-10 sin implementar su esquema completo ni afirmar
multicliente antes de observar pruebas reales con dos organizaciones.

## Decisión y alcance

F05a añade una migración mínima y un arnés PostgreSQL desechable local. No añade
un lector runtime, integración HTTP con DB, Entra, UI, secretos de producto,
provisioning ni migración de producción. F05b conectará posteriormente el puerto
sincrónico existente a un pool y tendrá sus propias pruebas HTTP respaldadas por DB.

| Tabla | Invariante mínima |
|---|---|
| identities | UUID; provider, issuer y subject no vacíos; unicidad conjunta; correo no es identidad |
| organizations | UUID, slug único, nombre/estado y revisión de configuración seleccionada |
| memberships | Organización e identidad; ID propio; únicos (org, identity) y (org, id); estado restringido |
| configuration_revisions | Clave (org, revision), revisión positiva y configuración pública mínima |

La selección de configuración usa FK compuesta (org, revision) hacia
configuration_revisions, diferible para permitir inserción coherente en una
transacción. No puede apuntar a una revisión de otra empresa. Evitar una segunda
fuente de autorización, payloads arbitrarios y tablas del producto completo.

## Roles y políticas

Migraciones usan un propietario separado. Runtime solo tiene SELECT y privilegios
mínimos de conexión/uso del esquema; no posee tablas ni puede crear en el esquema.
Es NOSUPERUSER, NOBYPASSRLS, NOCREATEDB, NOCREATEROLE y NOREPLICATION, sin membresías
elevadas. Se verifican también atributos, propiedad y grants efectivos, no solo el
nombre del rol. Cada tabla de este corte lleva ENABLE y FORCE ROW LEVEL SECURITY.

| Recurso | Visibilidad interna runtime |
|---|---|
| identities | Solo el sujeto autenticado exacto provider/issuer/subject con contexto completo |
| memberships | Organización solicitada e identidad validada; propia active/suspended, no archived |
| organizations | Organización solicitada y existencia de membresía propia no archivada |
| configuration_revisions | Misma organización y membresía propia no archivada |

El GUC de organización por sí solo no concede acceso. Contexto ausente, parcial o
vacío deniega; contexto malformado no revela filas ni diagnósticos públicos.
Identidad no consulta membresías; membresía verifica identidad propia sin consultar
organización/configuración; las otras políticas consultan membresía. Esta dirección
evita dependencia circular y recursión de políticas. No usar funciones con poderes
de propietario como atajo para saltar RLS.

La membresía propia suspendida conserva visibilidad interna para que el transporte
posterior emita 403 solo después de comprobar contexto consistente. Membresía
archivada o ajena permanece oculta; no inferir autorización de lectura pública de
configuración a partir de ese acceso interno. La capa de aplicación sigue exigiendo
organización y membresía activas y proyectando campos allowlisted.

## Contexto transaccional y límite de confianza

El servidor confiable obtiene identidad del validador y valida organización/contexto.
Establece valores con `set_config` parametrizado y tercer argumento true dentro de
una transacción externa; nunca SET persistente, concatenación SQL ni contexto de
cabeceras confiadas al cliente. El arnés comprobará reutilización real del mismo
backend PID tras commit y rollback y ausencia de contexto/filas residuales.

RLS es defensa adicional. No evita una aplicación comprometida o SQL malicioso que
reemplace sus propios GUCs, ni sustituye validación de token/autorización. Errores de
FK/constraints pueden incluir identificadores y deben quedar privados; no convertir
un rechazo interno en información de existencia visible al cliente.

## Prueba real y criterios de aceptación

- Dos organizaciones, múltiples sujetos y combinaciones cruzadas; SELECT runtime
  sin filtro del llamador solo devuelve el ámbito correcto.
- Unicidad de identidad, estados/revisión inválidos y FK compuesta cruzada fallan.
- Contexto ausente, parcial, vacío y malformado no muestra datos; combinación de
  organización válida con sujeto ajeno no crea permiso.
- Runtime no es dueño/bypass/superusuario, no hereda poderes elevados y no modifica
  datos, políticas o esquema. FORCE/ENABLE y grants se inspeccionan en PostgreSQL.
- USING y WITH CHECK se prueban independientemente mediante un escritor exclusivo
  del arnés con grants restringidos; privilege denied del runtime no prueba WITH CHECK.
  Debe permitir la escritura válida y rechazar la cruzada por política, usando filas
  cuyos FKs sean válidos para no confundir RLS con un rechazo referencial.
- Commit y rollback reutilizan el mismo backend y eliminan contexto previo.
- RED ocurre contra scaffold real conectable sin RLS; GREEN con migración completa.
  Import fallido, Docker inaccesible o imagen ausente nunca son RED de comportamiento.
- Los 31 tests existentes siguen GREEN; suite DB obligatoria no permite skip
  silencioso. No se usa SQLite ni un mock para afirmar aislamiento.

## Arnés local y comandos previstos

El script PowerShell usará exclusivamente el Docker Desktop local mediante
`npipe:////./pipe/docker_engine`, binario absoluto y configuración Docker privada
vacía en `.local/postgres-test/`, ignorada antes de crear artefactos. No inspecciona
contextos, autenticación, contenedores, DB o volúmenes ajenos. Se resolverá una vez
la imagen oficial pública `postgres:17-bookworm` y se guardará su digest efectivo;
el modo normal usa `--pull=never` y falla claramente si la imagen no existe.

Cada ejecución crea nombre/credenciales aleatorios, puerto dinámico ligado solo a
127.0.0.1 y contenedor propio sin mounts de host ni volumen persistente. Un bloque
finally limpia exclusivamente el ID capturado y su almacenamiento anónimo, incluso
si falla una prueba. No prune ni borrado de recursos desconocidos. Contraseñas/DSN
no se imprimen ni persisten. Venv propio desde Python bundled y pin exacto de
`psycopg[binary]` resuelto por PyPI público; no se modifica Python global.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_foundation.py -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_api.py -v
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\test-postgres.ps1
.\.venv\Scripts\python.exe -m compileall -q src tests
.\.venv\Scripts\python.exe -m pip check
git diff --check
```

Los dos primeros comandos son el subconjunto existente sin DB (13 + 18 tests).
El script crea la DB propia, entrega conexión efímera al proceso hijo y ejecuta
unittest con `-s tests -p test_postgres_rls.py -v`. Ese módulo sin configuración
explícita del arnés debe fallar, no omitir tests. Discovery amplio incluirá DB;
no se anuncia como prueba sin PostgreSQL. Comprobar whitespace también en archivos
nuevos no trackeados. Ninguno de estos comandos se ejecutó en la preparación.

## Entrega y siguiente acción

F05a estima 900–1400 líneas authored incluyendo migración, arnés, pruebas y docs;
F05b estima 450–750 y se reestima antes de escribir. Son presupuestos orientativos:
no retirar pruebas, comprimir código ni dividir por extensión para ajustarlos.
El corte local feature-branch-chain mantiene pruebas junto al comportamiento.
Parent controla commit/revisión; no push, PR, merge ni revisión nativa del worker.

Siguiente acción: parent verifica estos dos documentos, actualiza el espejo completo
`odd/forge-foundation/tasks` y liberó F05a con los paths exactos registrados en el task.
La resolución y prueba observadas se registran abajo; no equivalen a integración
del lector runtime ni a aprobación de revisión nativa.
## Historial: prerrequisitos bloqueados antes de recuperación

Parent liberó F05a tras lectura y espejo completos. La resolución aislada PyPI
falló con JSONDecodeError al analizar una respuesta del índice; psycopg 3.3.6 solo
se observó como metadata, no como instalación/pin verificados. El pull de imagen
no se ejecutó; no hubo contenedor, versión PostgreSQL ni prueba RED/GREEN.

Existen scaffold SQL y archivos de pruebas provisionales, todavía sin políticas
RLS y no verificados. La escritura del arnés falló porque su directorio todavía no
existía. Se conservó el estado y se detuvo la ejecución, sin reintentos ciegos.
Estos fallos de preparación no prueban rechazo de aislamiento. Recuperación y
verificación quedan pendientes; F05b, integración HTTP y producción siguen fuera.
## Evidencia local recuperada

Una recuperación PyPI pública aislada, sin cache, con timeout 30/retries 1 y límite
180 segundos completó dependencias: psycopg y binary 3.3.6, pin exacto en extra de
pruebas; imports y pip check correctos. No se confirmó la causa del JSON truncado.
El directorio del arnés se creó por separado antes de regenerar los archivos.
El único pull oficial autorizado terminó correctamente; digest efectivo:
`postgres@sha256:639ab7ceb90e13123085b741fb31ef493fba25463002f6da665352e7b534b652`.
Servidor real observado: PostgreSQL 17.11 (Debian 17.11-1.pgdg12+2).

RED real: 21 métodos, 109 fallos de assertions y un error por política todavía
inexistente, exit 1; la DB era conectable y el scaffold mostraba datos cruzados.
GREEN inicial: 21/21. GREEN final: 22/22, incluido propietario sometido a FORCE,
helpers invoker y contexto limpio en el mismo PID después de commit/rollback.
Regresiones: 13 dominio + 18 HTTP; compileall, pip check y whitespace correctos.
La suite DB sin arnés falla claramente exit 1, no hace skip. No confundir esa
comprobación negativa con RED de aislamiento.

La verificación reforzada de mounts tuvo un fallo de arnés previo a tests porque
Docker informa tmpfs en HostConfig.Tmpfs, no en Mounts; se corrigió y el comando
final pasó. También se corrigió el stderr esperado de inspección tras rm en
PowerShell 5.1. Cada contenedor creado fue eliminado por su ID exacto; readback
confirmó ausencia. No quedaron recursos propios, mounts de host o volúmenes
persistentes. Secrets no aparecen en logs. El script normal nunca descarga imagen.

La migración es de una sola ejecución en DB/cluster Forge dedicado y vacío, con
roles reservados; no es un runner de upgrades ni debe alterar una DB compartida
ajena. Provisionar LOGIN/password y grants del escritor de tests es responsabilidad
exclusiva del fixture local. RLS conserva el límite de confianza descrito arriba.

Verificación independiente: 22 DB + 13 dominio + 18 HTTP, pip check y whitespace;
roles/RLS/WITH CHECK/constraints y cleanup inspeccionados y correctos. Parent repitió
el arnés: 22/22, exit 0, PostgreSQL 17.11 y ausencia del contenedor confirmada.
Commit local autorizado; parent mantiene espejo y evaluación/revisión nativa pendientes.
F05b lector/pool/HTTP, Entra, UI y producción siguen pendientes. Referencias de
semántica: [PostgreSQL RLS](https://www.postgresql.org/docs/17/ddl-rowsecurity.html)
y [transacciones psycopg](https://www.psycopg.org/psycopg3/docs/basic/transactions.html).