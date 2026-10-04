# F08a: composición explícita y estado operativo

## Estado y resultado observado

F08a cerrado como entrega LOCAL de pantalla operativa, con límites de evidencia UI
explícitos. Escritor184 y wheel corregido aprobados; P1 de telemetría corregido con
RED/GREEN y retest independiente28runtime+18API más138 pruebas previas aplicables.
Spot del padre28 aprobado10.292s; captura móvil inspeccionada sin defecto.
El padre acepta C10 observado, no certificación de red/lector de pantalla/carga.
Commit local autorizado, identidad registrada en el task; no disponibilidad de producción.
Gentle está desactivado globalmente; no revisión nativa ni aprobación inventada.

El candidato implementa una aplicación local ejecutable con composición programática
de los adaptadores Entra/PostgreSQL existentes y una pantalla de estado real,
de solo lectura. No es un cliente administrativo ni un inicio de sesión.
La interfaz está en inglés; esta especificación usa español neutral.

## Problema y límites

Antes de F08a, la validación criptográfica y la vinculación persistente no componían
el servidor. /healthz demuestra vida del proceso, no disponibilidad del almacenamiento,
acceso del usuario ni inscripción en Entra. Una pantalla que mezcle estas garantías
sería engañosa. PF-02/PF-10/PF-12 delimitan identidad y contratos;
PF-03/PF-09/PF-11 orientan configuración y presentación, no privilegios nuevos.

La aplicación sin configuración debe mantener denegación predeterminada y cero
conexiones, descubrimiento DNS/Entra o búsqueda de credenciales. No se agregan
migraciones, composición del binder, usuarios, membresías, invitaciones, administración,
almacenamiento de tokens, PKCE ni acceso a cuentas reales.

## Diseño propuesto

### Configuración y composición

forge.runtime.create_runtime_app(configuration=None) recibe una configuración
tipada e inmutable o permanece explícitamente sin configurar. No carga variables
de entorno, archivos, servicios libpq ni DSN. La configuración entrega los valores
Entra ya validados y todos los campos de conexión PostgreSQL; la contraseña se
excluye de representaciones y diagnósticos. Sin valores predeterminados de confianza.

La composición conecta EntraTokenValidator y PostgresBootstrapReader reales con
los puertos existentes. Un punto mínimo de lifespan en create_app conserva su
comportamiento sin argumentos y los controles de organización/membresía.
Abrir/esperar/cerrar el pool y las sondas bloqueantes ocurre fuera del bucle de
eventos. Los fallos parciales y el cierre deben liberar recursos propios.
Un fallo de almacenamiento deja disponible un estado público no disponible,
nunca una disponibilidad ficticia.

**Condición técnica aceptada por el padre:** perfil local limitado
a host/hostaddr numéricos de loopback, puerto/base explícitos, usuario forge_runtime,
contraseña no vacía y controles fijos de opciones/search_path/row_security,
autenticación y transporte. SSL/GSS desactivados se limitan al entorno local propio;
el perfil TLS/remoto de producción queda fuera de F08a.

libpq 17 consulta PGSERVICE/PGSERVICEFILE antes de completar valores predeterminados.
Proporcionar host/usuario/contraseña no basta; service vacío no se supone un
interruptor seguro. El padre aceptó rechazo cerrado por presencia de variables PG* solo en modo configurado,
sin leer/adoptar sus valores ni modificar el entorno global; la aplicación sin
configurar ni siquiera realiza esta inspección. No usar PQconndefaults, que consulta
el entorno. Contraseña explícita no vacía y controles completos deben impedir
suplementación por archivos de servicio/contraseña/certificados. Las pruebas con
entornos sintéticos de procesos propios deben demostrarlo antes de declarar listo.
Fuentes primarias:
[Conexión libpq 17](https://www.postgresql.org/docs/17/libpq-connect.html),
[Variables libpq 17](https://www.postgresql.org/docs/17/libpq-envars.html),
[Código libpq 17](https://raw.githubusercontent.com/postgres/postgres/REL_17_STABLE/src/interfaces/libpq/fe-connect.c).

### Disponibilidad y contrato público

La sonda verifica el rol efectivo, privilegios reales (incluidos por columna),
RLS y estructura migrada 0001/0002 mediante catálogos. No consulta datos del negocio,
conteos, contexto de organización ni identidad de usuario. SELECT 1 no demuestra
el contrato. Debe comprobar columnas/tipos/par/checks/trigger y requisitos del rol.
Una caché finita con una sola sonda concurrente evita sobrecarga; resultados positivos
vencidos no ocultan una interrupción. La lectura de bootstrap sigue evaluándose
por solicitud y no recibe autorización de la sonda.

GET /forge/v1/status publica exclusivamente:
- schema_version: 1.0.
- runtime: unconfigured/checking/ready/unavailable.
- configuration: missing/provided.
- storage: not_configured/checking/ready/unavailable.
- identity_provider: not_configured/configured_unverified.
- onboarding: not_implemented.
- user_access: not_evaluated.

ready solo significa configuración local válida y rol/esquema PostgreSQL verificados.
No acredita conexión real con Entra, autenticación, inscripción, administración ni
permisos de una persona. /healthz permanece como liveness independiente.
No se publican IDs, ámbitos, DSN, host, rutas, excepciones, conteos, tokens ni PII.
Los errores se clasifican y redactan; no se registran excepciones sensibles crudas.

Límites fijos implementados y observados: pool mínimo 0 / máximo 2, espera 4,
reconexión 1s, conexión 2s, adquisición 1s, apertura/espera 5s y cierre 5s;
sonda statement 3s / lock 1s, TTL 5s, una sonda concurrente y enfriamiento de fallo 5s.
Sin sondeo periódico. Las pruebas deben verificar semántica y limpieza real;
todo ajuste justificado se documentará. No se promete un SLA absoluto de DNS/SO.

### Pantalla y recursos

Rutas fijas /status, /status.css y /status.js. HTML/CSS/JS locales pequeños,
empaquetados mediante recursos del paquete, sin CDN, logotipo inventado, formularios,
ingreso de usuarios/tokens, almacenamiento de sesión o simulación de login.
Paleta: navy #0B1D26, teal #0F6B6D, copper #E07A2D, sand #E8DCC1,
charcoal #1A1A1A. Copper es acento; no se asume contraste de texto suficiente.

Interfaz en inglés con encabezados/landmarks semánticos, foco visible, región viva
de estado, etiquetas que no dependan del color, botón Refresh de solo lectura,
bloqueado durante actualización, diseño responsive 360x800 y tratamiento honesto de
fallo/estado anterior. No se muestran objetos de organización ni administración.

CSP sin contenido en línea: default-src 'none'; script/style/connect/img 'self';
base-uri/frame-ancestors/form-action/object-src 'none'. no-store en estado/HTML/
recursos; origen único, sin ampliación CORS o montaje de directorios arbitrarios.
Pruebas de rutas, encabezados, redacción, fallo de fetch y recursos obligatorias.

### Empaquetado y requisitos de despliegue

pyproject.toml incluye explícitamente los tres recursos, sin nueva dependencia de
ejecución. El wheel real y sus recursos ya tienen prueba observada, no solo archivos
presentes en checkout. La ausencia inicial de setuptools/wheel/build queda como
antecedente; las seis herramientas autorizadas ya están instaladas y verificadas.
El padre autorizó adquisición pública acotada de herramientas solo en .venv tras
liberar código; la instalación y el wheel final ya tienen prueba observada abajo. Sin actualización
de dependencias de ejecución. El build posterior conserva cero descargas.

Después de adquirir y verificar el backend autorizado, copiar fuente/manifiesto/README exactos a
.local/runtime-test/package-src y usar pip --isolated wheel --no-index --no-deps
--no-build-isolation --no-cache-dir con salida .local/runtime-test/wheels; inspeccionar ZIP y
importlib.resources. No generar metadatos fuera de las superficies autorizadas.


Herramientas exactas instaladas: setuptools 84.0.0, wheel 0.48.0, build 1.6.1,
packaging 26.0, pyproject-hooks 1.2.0 y colorama 0.4.6. Metadatos oficiales PyPI
verificados el 2026-10-04: requisitos Python compatibles con 3.12.14, ruedas universales,
no retiradas; build requiere packaging>=24, pyproject_hooks y colorama en Windows,
wheel requiere packaging>=24. Dependencias completas fijadas sin extras.
[setuptools](https://pypi.org/pypi/setuptools/84.0.0/json),
[wheel](https://pypi.org/pypi/wheel/0.48.0/json),
[build](https://pypi.org/pypi/build/1.6.1/json),
[packaging](https://pypi.org/pypi/packaging/26.0/json),
[pyproject-hooks](https://pypi.org/pypi/pyproject-hooks/1.2.0/json),
[colorama](https://pypi.org/pypi/colorama/0.4.6/json).
Se descartó wheel 0.45.1 al encontrar CVE-2026-24049 en metadatos (corregida 0.46.2);
ningún pin antiguo se instaló. Ausencia de vulnerabilidades listadas no garantiza
ausencia universal de problemas.

Comandos de dry-run e instalación exactos en la sección de herramientas del task:
pip --isolated install [--dry-run] --index-url https://pypi.org/simple --no-cache-dir
--no-input --keyring-provider disabled --timeout 15 --retries 1 --only-binary=:all:
--no-deps con los seis pins. Límite total 180s de adquisición; verificar versiones
instaladas, pip check y conservación de todos los nombres/versiones previos sin
inspeccionar URLs/credenciales. .venv/** se añade únicamente como superficie ignorada
de herramientas de build; no se autoriza otra dependencia o instalación en esta etapa.

El despliegue necesita ejecución externa ordenada 0001/0002, login runtime restringido
y credenciales explícitas, controles de conexión permitidos, tenant/audience/client/
scopes Entra configurados y requestedAccessTokenVersion2 en el recurso.
No se implementa el ejecutor de migraciones, aprovisionamiento del login, TLS remoto,
vinculación de usuarios ni prueba de tenant real.

## Alcance y comprobación

Los doce criterios C1–C12, superficies liberadas y comandos exactos están en
odd/tasks/forge-identity.md. Protegidos: dominio, migraciones, Entra, binder, pruebas
existentes no listadas, harness, fundamento cerrado y especificaciones del producto.
Código liberado por el padre; RED conductual importable→GREEN→
refactor con unittest y PostgreSQL propio, criptografía RS256 real y fixtures
sintéticos sin llaves privadas persistidas.

Regresión heredada 142 = 73 DB + 38 Entra + 13 dominio + 18 HTTP; resultado inicial
181 = 87 DB + 25 runtime + 38 Entra + 13 dominio + 18 HTTP, sin omisiones.
compileall, pip check y diff --check también aprobados por el escritor. Harness Docker existente,
imagen fijada en caché, contenedor propio y limpieza por ID exacto; no pull/prune/
base existente. Registrar fallos, prerrequisitos y pruebas omitidas honestamente.

Prueba de navegador posterior por padre/verificador con skill browser: uvicorn
propio en 127.0.0.1:8765, factory sin configuración, logs/PID en .local/runtime-test.
Si puerto ocupado, no inspeccionar ni detener al ocupante. Verificar actualización,
teclado, viewport estrecho, redacción y cero solicitudes externas; detener solo PID
propio. Usar bootstrap/documentación del navegador de la skill; sin automatización
alternativa, cuentas ni inspección de cookies/almacenamiento/perfiles.

Estimación 1800–2600 líneas modificadas incluyendo consolidación/pruebas/UI/documentos;
400 es guía, no límite ni motivo de división artificial. Rama local encadenada ya
aceptada; commit coherente futuro solo tras verificación independiente y spot del padre.
No commit/publicación en este checkpoint. F07b/F09 requieren alcance separado.

## Puerta actual

Relectura de ambos documentos, diff --check y alcance exacto liberado: trece archivos
originales más .gitignore, autorizado después únicamente para ignorar
`/.local/runtime-test/` sin cambiar patrones existentes ni borrar archivos.
El padre confirmó el espejo completo antes del código y conserva su actualización.
Perfil/guardia libpq, adquisición, implementación, RED/GREEN y wheel real tienen
evidencia del escritor. Comportamiento de navegador observado con límites explícitos;
retest independiente y spot aprobados; C10b conserva evidencia complementaria pendiente.


## Evidencia observada del candidato F08a

Liberación del padre tras espejo completo2468 y relectura normalizada del plan.
RED conductual: seis métodos runtime/26 aserciones,76DB/dos aserciones;
73 heredadas aprobadas. GREEN inicial6+76. Pruebas ampliadas conservaron fallos de
fixtures: literal NUL incorrecto, quoting de prueba, mock global demasiado amplio
que interfería con getenv de FastAPI, DDL no confirmado invisible entre conexiones
y cambio de tipo impedido por política. Se corrigieron fixtures, no garantías
ficticias; el task conserva cada resultado y el fallo de redirección/shell previo.

Resultado final del escritor:25 runtime+38Entra+13dominio+18HTTP+87DB=181,
sin omisiones; compileall/pip check/diff check código0. PostgreSQL17.11/14.064s,
limpieza de contenedor propio por ID exacto. Prueba runtime real: RSA efímero/JWKS
sintético y PostgreSQL propio,401 inválido/404 sin binding/200 tras metadata explícita
de fixture/404 ajeno/403 suspendido/404 revocado. Readiness no llama al IDP y no
evalúa acceso personal. Privilegios por columna, corrupción confirmada del esquema,
ausencia de datos, caché/concurrencia/limpieza/redacción tienen pruebas durables.

Cliente enlazado libpq18.4, distinto del servidor17.11; versiones inferiores18
rechazadas. Campos locales explícitos: puerto1..65535, identificador de base1..63,
contraseña no vacía hasta4096 bytes UTF8 sin controles/surrogates. Guard PG* por
presencia antes de crear pool y en cada conexión; sin leer valores ni modificar
entorno global. Controles probados con conexiones reales SCRAM y fuentes18:
[libpq18](https://www.postgresql.org/docs/18/libpq-connect.html),
[código18](https://raw.githubusercontent.com/postgres/postgres/REL_18_STABLE/src/interfaces/libpq/fe-connect.c).
Sonda estructural, no auditoría de cada cuerpo de política/función o bytes de migración.

Adquisición de seis herramientas:13.625s, versiones anteriores intactas.
Wheel offline real final SHA256:
362da36402fb759af76eca231bccfba6b1b9ac3226aa895bbeba9f7456fe0364.
HTML2308/CSS2290/JS2588 bytes coinciden con fuente; ZIP, importlib.resources e
importación/HTTP desde wheel en proceso separado aprobados sin instalación.
Primer comando sin no-cache-dir produjo una entrada de caché local pip inesperada;
padre informado, sin inspección/eliminación fuera del alcance. Comando final usa
--no-cache-dir y TMP/TEMP solo del proceso hijo en .local/runtime-test/tmp.
Metadatos/build final no escriben en árbol original ni caché ambiental.

README corresponde a composición local y límites reales. Interfaz/headers/contraste
tienen comprobación estática/HTTP y comportamiento de navegador observado con límites.
Retest independiente enfocado y spot del padre aprobados; commit local autorizado. No servidor/navegador iniciado por el escritor,
cuenta real, TLS de producción, inscripción ni aprobación nativa.


### Corrección de telemetría y límites de navegador

Evaluación independiente original181+wheel aprobada, con hallazgo P1 concreto:
FastAPI0.142.2 heredaba proveedores globales y capturaba query token/identidad y
nombres de endpoints aun sin configuración. Fábrica compartida corregida mediante
TelemetryConfig explícito: tracing, metrics, logs, operation_spans y auto_configure
False. Desactivar solo setup no basta. No se modifican proveedores ni entorno global;
instrumentación externa del host/middleware queda fuera de esta garantía nativa.
Tres regresiones durables usan procesos hijos, proveedores sintéticos con control
positivo y hook de configuración/descubrimiento OTEL, sin SDK/exportador/red.
RED28/4 fallos de aserción/59 llamadas controladas; GREEN28. Regresión completa
corregida184=28runtime+87DB+38Entra+13dominio+18HTTP, sin omisiones; DB14.770s y
limpieza exacta. compileall/pipcheck/diffcheck aprobados. Wheel reconstruido sin red,
API y tres recursos exactos; importación/HTTP separado aprobado. SHA256 actual:
8e46e0e1d6174c3535201b78f1e018896f6c49697c3a74c7d63da667d16c93bc.

Actor de navegador del padre observó render real sin configuración, Tab/skip-link/
Refresh/Enter,360x800 sin overflow, atributos live y Refresh tras detener servidor:
mensaje fijo unavailable, otros campos vaciados y botón habilitado. PID propio15480
cerrado dos veces/tab cerrado; ningún defecto visual bloqueante. Carga transitoria
solo tiene evidencia fuente por ser demasiado breve; anuncio de lector de pantalla
no verificado. Captura de performance/red del navegador no disponible: DOM de
recursos locales y controles deterministas no se etiquetan como captura completa
sin solicitudes externas. Foco tras fallo pasa a body, observación no bloqueante.
C10 observado cerrado por decisión del padre para entrega LOCAL; C10b mantiene
pendiente certificación/captura no disponible. No cambios UI extra, servidor del
escritor, cuenta real ni aprobación nativa. Retest independiente cerrado y spot
aprobado; límites conservados, sin afirmación de disponibilidad de producción.
