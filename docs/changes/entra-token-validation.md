# F06 · Validador backend de access tokens Entra v2

**Estado: F06 verificado localmente; validación independiente y comprobación del coordinador completas. Evidencia de commit en la tarea.**
Se agregó un adaptador criptográfico sin iniciar sesión, registrar aplicaciones ni
habilitar el despliegue. La API sigue denegando todos los tokens cuando no se inyecta
el adaptador. Autenticar no crea membresías.

## Alcance y antecedente

Tarea: odd/tasks/forge-identity.md, F06, diez criterios. PF-02 exige identidad/aislamiento,
PF-10 define API/datos y PF-12 exige evidencia. La fundación cerrada permanece en
odd/tasks/forge-foundation.md: 44 pruebas PostgreSQL +31 dominio/HTTP verificadas
independientemente y por el coordinador. Baseline:
f44032ea175c9197eb8cdca1f28348ce4fc6bd44.
Ese antecedente no prueba Entra ni un alta real.

## Diseño autorizado

| Límite | Decisión |
|---|---|
| Configuración | Tenant GUID permitidos, audiencia GUID de API, scopes delegados requeridos y clientes públicos GUID autorizados; conjuntos no vacíos y acotados |
| Firma | PyJWT/cryptography con versiones compatibles fijadas; únicamente RS256, algoritmo nunca elegido por el JWT |
| Entrada | Token y kid acotados; formas/tipos estrictos; jku/x5u no son autoridades de red |
| Claims | iss/aud exactos, tid permitido, ver 2.0, azp permitido y scp mediante tokens exactos separados por espacios |
| Tiempo | exp/nbf/iat finitos y numéricos, no booleanos/cadenas; emisión y habilitación anteriores a expiración; reloj inyectable y tolerancia acotada |
| Rechazo | None para token inválido; rechazar Graph, ID token, scopes incompletos e idtyp=app; typ=JWT no demuestra token de acceso |
| Operación | Fallo discovery/JWKS: excepción tipada/redactada; API existente responde 503 |
| Autorización | El lector vuelve a comprobar organización/membresía; grupos/roles del JWT no conceden permisos Forge |

El perfil Forge es más estricto que un parser genérico. Scopes delegados,
audiencia/cliente autorizados y firma deben comprobarse juntos. El manifiesto futuro
del recurso deberá usar requestedAccessTokenVersion=2; el endpoint v2 solo no lo fija.
Ver [claims Entra](https://learn.microsoft.com/en-us/entra/identity-platform/access-token-claims-reference),
[validación de claims](https://learn.microsoft.com/en-us/entra/identity-platform/claims-validation)
y [versionado/validación](https://learn.microsoft.com/en-us/entra/identity-platform/access-tokens).

## Identidad canónica explícita

Resultado inmutable: sub real, tid y oid verificados por separado.
Devuelve AuthenticatedIdentity("entra", issuer_v2_exacto, oid_GUID_canónico).
subject del dominio significa principal canónico Forge, **no** copia del sub OIDC.
Mismo tenant/oid con sub distinto: mismo principal; oid igual con otro tenant:
principal distinto. Esto prioriza identidad empresarial estable frente a privacidad
pairwise por aplicación.

Invitados permanecen objetos del tenant emisor del recurso; correo/idp/nombre no
sustituyen oid ni unen identidades. F07 persistirá/vinculará tid/oid explícitamente
antes del alta. Actualmente no existen usuarios Entra reales que migrar.
Sin fallback a sub, membresías/administradores automáticos ni signup de tenants.
La distinción sub/oid está en la
[referencia oficial](https://learn.microsoft.com/en-us/entra/identity-platform/access-token-claims-reference).

## Discovery y JWKS acotados

Metadata únicamente por tenant GUID configurado:
https://login.microsoftonline.com/{tenant}/v2.0/.well-known/openid-configuration.
issuer exacto; jwks_uri solo HTTPS del host oficial con ruta
/{tenant}/discovery/v2.0/keys o /common/discovery/v2.0/keys.
Sin credenciales, fragmentos, queries, puertos alternativos, redirects u otros hosts.
Clave RSA pública de firma con uso/algoritmo seguros e issuer compatible; validar
template {tenantid} antes de usarla. Forma oficial de endpoints/template:
[validación de issuer/claves](https://learn.microsoft.com/en-us/entra/identity-platform/access-tokens).

Fetcher/reloj inyectables; límites finitos de timeout/bytes/claves/tenants/kid/
concurrencia. Los valores exactos y rangos implementados se documentan abajo.
Caché por tenant con TTL finito y sincronización; kid desconocido permite como máximo
una actualización cuando el cooldown lo permite. Cooldown/backoff también al fallar
la descarga. Sin caché eterna por clave ni aceptación de material vencido durante
una caída. Este perfil conservador puede producir 503 temporal durante rotación o
caída, en vez de aceptar claves vencidas.

La librería verifica firmas; Forge acota red/caché y no implementa RSA.
No usar JWTClient sin comprobar límites de defaults. Ver
[API PyJWT](https://pyjwt.readthedocs.io/en/stable/api.html) y
[rotación Entra](https://learn.microsoft.com/en-us/entra/identity-platform/signing-key-rollover).
Algoritmos explícitos impiden que el atacante dirija la verificación.

## Pruebas y cierre

1. RED conductual con adaptador mínimo importable; RSA efímero generado en pruebas,
   JWKS pública sintética y transporte inyectado; ninguna clave privada escrita.
2. GREEN de firma/tipos/tiempos/issuer/audiencia/tenant/cliente/scopes e identidad
   estable, tenants distintos e invitados sin unión por correo.
3. Rotación/TTL/kid desconocido/concurrencia/fallo con cooldown, redirects,
   JSON malformado, límites de cuerpo/claves y timeout.
4. Adaptador real por create_app sin editar API ni tests existentes: 401 inválido,
   503 operacional y cero llamadas al lector cuando se rechaza.
5. Regresión previa completa, compileall, pip check, whitespace, verificación
   independiente y comprobación del coordinador, con resultados observados.

Comandos/superficies exactos en la tarea; evidencia observada y límites abajo.

## Continuidad y exclusiones

F07: vínculo persistente/aprovisionamiento; F08: composición/readiness; F09: PKCE,
caché protegida por SO y spike de alta autorizado. No reutilizar .env ni
mcp-tokens.json upstream para tokens corporativos. Sin credenciales, cuenta real,
producción, gasto, remoto, push/PR/merge. Gentle AI review GLOBALOFF:
disabled/unmanaged, sin evaluación o aprobación nativa.
Las pruebas sintéticas no prueban consentimiento, MFA, refresh o alta Microsoft real.

## Límites implementados y versiones

PyJWT[crypto] 2.15.1 y cryptography 50.0.2, resueltos/instalados con wheels compatibles
en Python 3.12.14 desde PyPI público aislado, sin caché ni credenciales.
La instalación directa de pins sustituye .[test] con aprobación del coordinador,
para evitar generar metadatos de build fuera de las superficies autorizadas.

| Límite | Valor inicial | Rango admitido |
|---|---:|---:|
| JWT ASCII | 16384 bytes | 1024–65536 |
| kid ASCII no vacío | 128 caracteres | 1–256 |
| Cada respuesta metadata/JWKS | 262144 bytes | 1024–1048576 |
| Claves por JWKS | 64 | 1–128 |
| Tenants / clientes / scopes configurados | 16 / 32 / 16 máximos | No ampliables por el JWT |
| TTL por tenant | 3600 segundos | 1–86400 |
| Cooldown tras éxito o fallo | 60 segundos | 1–3600 |
| Timeout socket/admisión lock/slot | 3 segundos | 0.1–10 |
| Fetches simultáneos por adaptador | 2 | 1–4 |
| Tolerancia de reloj | 60 segundos | 0–300 |

sub: 1024 caracteres máximo; scp: 4096, identificador individual 128.
NumericDate finito y no booleano dentro de 0–2^53; se vuelve a comprobar tiempo
después de discovery/firma. RSA público 2048–4096 bits, exponente 65537.
Sin JSON duplicado, no finitos, campos privados RSA ni kid ambiguo.

El transporte comprueba deadline de 2×timeout antes/después de cada read1 acotado.
DNS sigue la planificación del SO; no se declara un SLA extremo a extremo.
Proxy ambiental desactivado, TLS con certificado/hostname verificados, redirects
rechazados y límites aun sin Content-Length. Fetcher inyectado es dependencia
confiable: debe respetar el contrato de timeout/tamaño/redirecciones.

Microsoft documenta JWKS common con claves de issuer exacto de otro tenant
(consumidores) junto a templates. Se valida la forma de todas las claves, pero
solo se admiten las del issuer exacto actual o template compatible. No falla
globalmente una JWKS válida mixta y nunca se usa la clave extranjera.
[Fuente oficial](https://learn.microsoft.com/en-us/entra/identity-platform/access-tokens).

## Evidencia del escritor y cierre funcional

RED inicial: 24 métodos, 62 fallos de aserción, sin errores, frente al esqueleto
importable que retornaba None. El encoder PyJWT impedía crear fixtures malformadas;
se corrigió el fixture para firmar JSON explícito mediante RSA cryptography,
sin escribir claves. Primera implementación: 23/24; la prueba de TTL avanzaba
3600 segundos usando un token ya vencido. Se renovó el token sintético y pasó 24/24.
Prueba adicional JWKS mixta: RED de una excepción operacional, luego GREEN con scope
por clave. Suite preindependiente: 36/36; después de corregir P2: 38/38, transporte/claims/cache/concurrencia/API.

Regresión observada: 13 dominio +18 HTTP +44 PostgreSQL; servidor 17.11,
contenedor propio eliminado y ausencia confirmada por ID. Comprobaciones finales: compileall, pip check y git diff --check exit 0; readback UTF-8/sin BOM/whitespace de seis archivos, sin claves privadas persistidas y superficies protegidas intactas.
Aviso de deprecación TestClient/httpx preexistente conservado.
Verificación independiente y comprobación del coordinador completas; commit local autorizado y evidencia en la tarea. Sin aprobación nativa.

## Corrección P2 del verificador independiente

Se detectó exp/nbf/iat=10**400: math.isfinite intentaba convertir el entero a float
antes de comprobar el rango y causaba OverflowError. Con firma inválida .AAA, la API
respondía 503 en vez de 401; fetch y lector no se ejecutaban. Es clasificación
incorrecta de entrada inválida, no bypass de autenticación. El coordinador informó
que las demás comprobaciones independientes pasaron.
Se agregaron regresiones directas y por create_app para los tres claims:
RED 38 métodos/6 aserciones fallidas; GREEN 38/38. Tipo/rango seguros antes de
math.isfinite; el mismo guard protege límites numéricos y reloj inyectado.
Regresión posterior: 13 dominio +18 HTTP +44 PostgreSQL, sin skips, exit 0;
PostgreSQL17.11, contenedor propio eliminado y ausencia por ID confirmada.
compileall/pip check/git diff --check exit 0. Retest independiente cerró P2:
38 pruebas y seis casos adversariales +/-10**400 para exp/nbf/iat, None directo,
HTTP401, fetch/lector=0. El coordinador repitió 38 Entra, exit 0.
Total escritor:113 (38+13+18+44); independiente original111 más retest.
F06 completo funcionalmente, sin afirmar alta Entra, UI o composición reales.
Gentle AI GLOBALOFF permanece disabled/unmanaged. Mirror final a cargo del coordinador.
