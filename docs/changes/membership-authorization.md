# F07b1: autorización de membresías por organización

## Estado y resultado observado

Fuente liberada tras espejo completo2534/relectura exacta del plan por el padre.
F07b1 cerrado como modelo interno local:211 pruebas del escritor, retest independiente
211/wheel y spot del padre108DB/18.864s aprobados; servidor17.11 y limpieza exacta.
Commit coherente local autorizado; identidad real se registra en el task tras ejecutarlo.
Sin dependencias nuevas, mutaciones/HTTP/administrador sembrado ni cuentas.

Task: odd/tasks/forge-administration.md; tema del espejo
odd/forge-administration/tasks, propiedad del padre.
Línea base48785aeb1d41958c227b8e80cc66dc0ac95d177c, rama local
feat/forge-tenant-storage. Las184 pruebas heredadas son evidencia histórica.
Gentle desactivado globalmente; no llamadas ni aprobación nativa.

El resultado implementado es un modelo interno de autorización, no una interfaz
administrativa. Separar identidad validada, vinculación persistente, membresía
activa y permiso por organización evita convertir un login o rol declarado por
el cliente en autoridad. F07b/F09 siguen incompletos.

## Alcance aceptado

PF-02 define cuatro roles de organización: organization_admin, department_manager,
skill_reviewer y member. platform_operator tiene ámbito de operación de plataforma,
no constituye un rol organizacional ni concede administración implícita.
PF-10 asigna invitación, actualización y suspensión de miembros al administrador
de la organización y contempla revision en membresías. PF-09 exige trazabilidad
de operaciones administrativas; PF-11 menciona crear un administrador sin definir
la autoridad inicial ni la política del último administrador.

En este corte, solo organization_admin autoriza las acciones exactas members.invite,
members.update y members.suspend. Los demás roles no autorizan estas acciones.
Acción desconocida, roles vacíos, valores malformados o cualquier rol desconocido
incluso mezclado con organization_admin deniegan. No equivalencias, normalización
permisiva, grants genéricos, precedencia allow/deny ni permisos MCP implícitos.

La designación/recuperación del primer administrador y la política del último
administrador requieren decisiones futuras antes de mutaciones. No se inventan
semillas, cuentas ni acceso predeterminado; esas decisiones no bloquean este
modelo de lectura.

## Datos y migración aditiva

0003_membership_authorization.sql incorpora:
- memberships.revision bigint NOT NULL DEFAULT1, CHECK revision>0.
- membership_roles(organization_id,membership_id,role), PK compuesta de los tres
  campos y FK(organization_id,membership_id) a memberships(organization_id,id).
- CHECK de los cuatro roles exactos, ENABLE/FORCE RLS y SELECT únicamente para
  forge_runtime; PUBLIC sin acceso, forge_migrator propietario.

La PK compuesta de memberships ya existe. No cambiar0001/0002 ni la vinculación
Entra; conservar active/suspended/archived. Filas existentes obtienen revision1
por el default del esquema, sin filas de rol/backfill de permisos/administradores.
No se introduce borrado en cascada/historia ni disparador de incremento de revision.
El uso futuro de If-Match y actualización atómica de revision sigue pendiente.

RLS de roles es SELECT por organización y membresía propia activa, con organización
activa y visibilidad de identidad canónica existente. Para Entra exige además par
persistido completo, issuer tenant-v2 exacto y subject object-id canónico; proveedores
genéricos y policies0001/0002 sin cambios. No mostrar roles de pares,
otras empresas ni identidad sin contexto. Funciones de contexto siguen invoker;
sin SECURITY DEFINER ni elevación. forge_identity_binder mantiene cero acceso
al nuevo almacenamiento/revision y sus permisos de columnas Entra sin cambios.
PK/FK impiden duplicados y enlaces de membresía a otra organización.

Migración transaccional con lock_timeout2s y statement_timeout10s; ejecutor de
migraciones/despliegue no implementado. Nunca ejecutar contra una base existente
o productiva en esta unidad.

## Snapshot y política pura

AuthorizationSnapshot congelado conserva identidad confiable exacta, UUID canónicos
de organización/membresía, revision positiva tipada y acotada por bigint, estado
de membresía/organización y roles copiados en estructura inmutable.
La política verifica forma completa, actividad, roles y acción exacta; bool no es
revision válida. Snapshot ausente/inválido o rol mixto desconocido deniega.

Construir un dataclass no autentica a nadie. Solo el puerto interno posterior a
validación alimenta el lector; nunca roles del JWT, header, body o parámetros
del cliente. Entra requiere tid/oid persistidos y coincidencia exacta de issuer/
subject canónicos; sin fallback por sub/idp/correo. Fixtures de otros proveedores
confiables conservan su comportamiento, sin nueva autenticación de desarrollo.

El snapshot no reserva un permiso ni sirve como capacidad reutilizable de escritura.
Mutaciones futuras deben revalidar identidad, organización, membresía, roles y
revision dentro de la transacción de escritura con auditoría/outbox. Sin caché de
autorización, API, sesión/login, invitación, aprovisionamiento ni grants engine.

## Lectura PostgreSQL y disponibilidad

PostgresAuthorizationReader usa pool síncrono externo restringido, sin descubrir
DSN/credenciales/entorno ni crear pool. Entrada inválida se rechaza antes de adquirir.
Errores operativos internos tipados y redactados; no exponer excepciones DB, tokens,
PII, DSN ni secretos. Datos de autorización no se agregan al estado HTTP público.

Una conexión idle/autocommit, guardia real de rol/propiedad/session/ACL/RLS y contexto
canónico/binder vacío antes de establecer GUC locales de identidad/organización.
Una sola SELECT de negocio parametrizada une identidad, organización activa,
membresía propia activa, revision y roles; evita lecturas parciales entre consultas.
No caché. Adquisición1s, override finito(0,30]; validar rango antes de convertir
a float. SET LOCAL statement_timeout3s/lock_timeout1s y restauración transaccional
de contexto/límites incluso con error; sin reapertura silenciosa ni estado global.
Cliente libpq18.4 y servidor17.11 son versiones heredadas verificadas, no promesa
para despliegues diferentes.

Extender guardia existente de cuatro a cinco tablas RLS, conservando SELECT en
todas las tablas Forge y prohibiciones de mutación de tabla/columna
INSERT/UPDATE/REFERENCES, elevación, propiedad o membresía de rol.
Readiness catalog-only exige columnas/tipos/default/CHECK de revision, roles,
PK/FK/CHECK/RLS/policy/grant nuevos sin debilitar checks Entra previos.
No leer datos/contar usuarios ni otorgar permisos para aparentar disponibilidad.
Esquema ausente/debilitado o privilegios expandidos deben dar unavailable.

## Superficies, pruebas y puerta

Checkpoint histórico modificó solo nuevo task, esta SDD y un enlace hijo;
la fuente fue liberada después del espejo/relectura y conserva límites exactos.
Las trece superficies de código/documentación y dos rutas ignoradas propuestas,
criterios D1–D10 y comandos exactos están en odd/tasks/forge-administration.md.
Protegidos0001/0002, dominio/API/Entra/binder/composición/UI/manifest, harness,
pruebas no listadas y especificaciones de producto. Sin dependencias nuevas,
instalación, .venv, servidor, navegador, commit o operación remota en el checkpoint.

Tras liberación: RED conductual de política y PostgreSQL propio, GREEN/refactor,
184 heredadas más pruebas nuevas, compileall/pipcheck/diffcheck. Imagen Docker
fijada existente, sin pull/prune y limpieza de recursos propios por ID exacto.
Probar matriz de roles/acciones/tipos, aislamiento empresa/pares, identidad Entra
sin vincular, actividad/revocación/revision recientes, snapshot concurrente,
constraints, privilegios, binder y limpieza/contexto/timeout.

Mantener probes originales0002 intactos y agregar casos distintos para:
1.0001→0002→0003 fresco.
2.Upgrade poblado, revision1 y cero roles sembrados, datos/lifecycle preservados.
3.Fallo determinista SELECT1/0 insertado en memoria antes del COMMIT exacto0003:
INERROR real, ROLLBACK y relectura sin tabla de roles/revision/policies/ACL nuevas,
con filas/funciones/RLS anteriores idénticos. COMMIT→ROLLBACK solo no prueba fallo.
Nuevos probes antes del fixture compartido; orden explícito de tres migraciones
después. El TABLES de probes originales conserva sus cuatro tablas.

Build offline con herramientas ya instaladas: staging bajo .local/runtime-test,
pip --isolated wheel --no-index --no-deps --no-build-isolation --no-cache-dir y
TMP/TEMP explícitos del hijo. Verificar módulos nuevos en ZIP/importación fresca
desde wheel y los tres recursos estáticos exactos, sin instalación ni descargas.
UI sin cambios: no repetir navegador; integración de readiness real obligatoria.
C10b previo de captura de red/lector de pantalla/carga sigue pendiente, no cerrado.

Estimación1100–1800 líneas autorales, pruebas completas incluidas;400 es guía,
no límite ni motivo de dividir por tipos de archivo/reducir claridad.
Estrategia local feature-branch-chain existente; un commit coherente futuro solo
tras verificación independiente, spot del padre y autorización separada.
No push/PR/merge/Gentle/cuentas/producción/secretos ni permisos automáticos.

## Siguiente paso

D1–D10 y F07b1 están cerrados con evidencia del escritor, retest independiente y
spot del padre aprobados; commit local autorizado. No implica API administrativa.
El padre actualiza espejo completo actual; no se confunde guardar con entrega.
No se solicita decisión de bootstrap administrativo para este corte de lectura.
Rollback de código es el commit local de F07b1; recuperación/downgrade de datos exige
procedimiento separado, no se entrega una migración destructiva.


## Evidencia del candidato y límites

RED puro6 métodos/26 aserciones y DB88/una aserción con87 heredadas aprobadas,
fixtures importables y limpieza exacta. GREEN6/89DB inicial tras corregir expectativa
legítima de cinco tablas y deparse de pg_get_expr dependiente de search_path:
SET LOCAL search_path=pg_catalog estabiliza checks exactos, con restauración probada.
Intermedio102DB aprobado no incluía cuatro métodos nuevos debajo de guards __main__;
corrección de descubrimiento→106DB aprobado. Error de sintaxis JavaScript de
orquestación antes de herramientas/comandos, sin mutación; llamada corregida.
Prueba adicional de lock real y filas pobladas con los tres estados→107DB final,
18.593s, servidor17.11 y contenedor propio eliminado por ID exacto.
Total210=6política+107DB+28runtime+38Entra+13dominio+18HTTP,184heredadas+26nuevas;
compileall/pipcheck/diffcheck aprobados, sin omisiones. Warnings heredados no silenciados.

Probes0003 separados: fresco cincoRLS/cero roles; poblado conserva active/suspended/
archived/revision1 sin permisos sembrados;22012/INERROR real antes de COMMIT,
ROLLBACK/IDLE sin tabla/revision nueva y filas/ACL/policies/funciones/RLS idénticos.
Función/probes0002 y TABLES cuatro tablas preservados exactamente.

Snapshot/roles/revision frescos y consistentes en concurrencia, vinculación Entra
obligatoria, aislamiento empresa/pares, RLS actividad y binder sin acceso probados.
Adquisición agotada0.1s y lock de relación1s reales, fallo redactado y pool/contexto/
límites/search_path restaurados; sin caché ni capacidad reutilizable de escritura.
Readiness rechaza nueva estructura/policy debilitada, RLS desactivado y grants de
mutación de columnas; guardia SELECT de todas las tablas y checks previos conservados.
La UI/composición no cambia; integración runtime real sigue aprobada, sin navegador nuevo.

Wheel real offline con herramientas existentes y TMP/TEMP del hijo: nuevos módulos,
postgres.py y tres recursos estáticos exactos, importación fresca/resources/HTTP0.
SHA256 previo al refuerzo 9adeb3ebedebc1cc4821bbd411c2d02a1ad48e00222468d92e3a1c0fa4b8b8ff;
sin instalación/descarga/dependencias.
Espejo actualizado y verificación independiente pertenecen al padre. Bootstrap/último
administrador, API/mutaciones/If-Match, auditoría/outbox y aprovisionamiento siguen futuros.

## Refuerzo acotado de RLS nuevo

La verificación independiente original210/wheel aprobó el lector. SELECT directo
mostró el rol propio de Entra sin vinculación, mientras el lector devolvióNone:
distinción entre capas, no bypass de autorización. El padre autorizó coherencia
adicional solo en policy0003 y su forma exacta de readiness, sin autocompletar
identidad ni roles. Providers genéricos y policies anteriores conservan sus bytes.
RED108DB/18.647s tuvo una aserción real de fila sin vinculación y107 anteriores
aprobadas; lectorNone aprobado antes del fallo. GREEN final108/19.918s demuestra
fila propia vinculada, controles positivos genéricos, denegación pares/empresa/
tenant/sub y readiness que rechaza la policy anterior sin binding. Servidor17.11,
limpieza por ID exacto. Total211=6política+108DB+28runtime+38Entra+13dominio+18HTTP,
compileall/pipcheck/diffcheck0, sin omisiones. Retest independiente211/wheel y spot108/18.864s aprobados.
Wheel reconstruido SHA256 06014d56d1137e20664b76aaac611bd805aea214d342739f760a3ac3c3754b43;
módulos actuales/recursos exactos e importación fresca/resources/HTTP0.0003 fuente
SHA256 f1b72d96dde40e1740c4d4d59036bff61c600a5d36f508d79a16542fbaceaf94;
SQL auditado por relectura, no se afirma inclusión en wheel. Sin descargas; cierre local autorizado.

Auditoría estructural inicial: ValueError por delimitador next-def ausente en helper
base, solo lectura; delimitador def/class corregido confirmó probe original intacto.
