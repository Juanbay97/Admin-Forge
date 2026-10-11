# MVP local de Prometheon Forge

> Estado: recorrido funcional completo en local. Plano de control, administración web, puerta de enlace
> falsa y cliente (compilación de producción) se levantan y se prueban de extremo a extremo en Chrome real
> con scripts\mvp-smoke.ps1. Cada rebanada está en openspec/changes/prometheon-forge-mvp/.

## Objetivo

Un recorrido funcional local, solo en loopback: administración web por empresa,
puerta de enlace falsa compatible con OpenAI y cliente de escritorio en
navegador, sin que ninguna persona usuaria maneje claves de proveedor.

## Puertos reservados

| Puerto | Componente |
|---|---|
| 3410 | Plano de control y administración web (`/admin/`) |
| 3411 | Interfaz del cliente |
| 3412 | Backend del espacio de trabajo del cliente |
| 3413 | Puerta de enlace falsa |
| aleatorio (loopback) | PostgreSQL 17 propio |

Nunca se usan 3319, 3320, 3331 ni 3332 (demostración anterior). Si 3410 o 3413
están ocupados, el arranque falla sin tocar el otro proceso y sin crear recursos.

## Arranque

```powershell
scripts\mvp-local.ps1                      # PostgreSQL 17 propio + datos de ejemplo + 3413 + 3410
scripts\mvp-local.ps1 -RequireAdminBuild   # además exige la compilación de la administración web
```

Imprime una línea JSON `ready` con los orígenes, el espacio de trabajo privado y
la ruta de `credentials.json` (contraseñas de las cuentas y clave de puerta de enlace
de cada organización; nunca se imprimen). Ctrl+C detiene todo: el contenedor propio
se elimina (con lectura de confirmación) y el espacio de trabajo se borra.

Datos de ejemplo (dos organizaciones aisladas): `org-a` y `org-b`, cada una con una
persona administradora, un departamento y un miembro, con contraseñas y claves de
puerta de enlace distintas. La clave de cada organización se registra desde la
administración o por la API (`PUT /forge/v1/orgs/{id}/gateway` con
`"endpoint": "http://127.0.0.1:3413"`).

## Piezas por separado

```powershell
$env:PYTHONPATH = 'src'
.venv\Scripts\python.exe -m forge.mvp_local serve --config <config.json>        # solo el plano de control
.venv\Scripts\python.exe -m forge.fake_gateway --keys-file <claves.txt> [--port 3413]
.venv\Scripts\python.exe -m forge.provision --operator-file <operador.json> --credentials-file <salida.json> seed
.venv\Scripts\python.exe -m forge.contract --write                              # regenera contract/forge-mvp.contract.json
```

`serve` solo lee el archivo de configuración y el archivo de secretos que este nombra
(no variables de entorno); cualquier campo ausente, desconocido o mal formado termina
con un código finito y sin abrir ningún puerto. `GET /forge/v1/contract` entrega la
versión y el hash del contrato que el cliente fija.

## Administración web de extremo a extremo

```powershell
scripts\admin-e2e.ps1   # compila /admin, levanta la pila propia, ejecuta Playwright y la detiene
```

Compila `admin/` (`src/forge/web/admin/`, ignorada por Git), arranca la misma pila que
`scripts\mvp-local.ps1 -RequireAdminBuild` y ejecuta `admin/e2e/admin-flow.spec.ts` en Chrome
del sistema contra el plano de control real y la puerta de enlace falsa: montaje con la CSP real
(sin violaciones, fuente propia cargada, un script en línea bloqueado), inicio de sesión de la
persona administradora de `org-a`, invitación y suspensión de miembros, guardado de la clave de
puerta de enlace, actualización y publicación del catálogo, y el miembro viendo exactamente los
alias publicados. Requiere `npm ci` previo en `admin/`, la imagen fijada de PostgreSQL en la
caché local y Docker; no descarga nada. Cada espera tiene límite y al final confirma que el
contenedor propio y el espacio de trabajo privado ya no existen.

## Cómo ejecutar el MVP

Todo es solo loopback y usa recursos propios (contenedor, espacio de trabajo privado, directorio de datos del
cliente) que se eliminan al detener. Nunca se usan 3319, 3320, 3331 ni 3332.

**Requisitos (una vez):** Docker Desktop en marcha con la imagen fijada de PostgreSQL 17 en la caché local
(`scripts/postgres-image.txt`), Chrome instalado, y las dependencias ya instaladas: `npm ci` en `admin/`,
`npm ci` en `clients\openyak\frontend` y el entorno `clients\openyak\backend\.venv`.

### Opción 1: prueba completa automática

```powershell
scripts\mvp-smoke.ps1    # unos 6 a 10 minutos; la compilación de producción del cliente es lo más lento
```

Compila `/admin`, levanta la pila propia, ejecuta el flujo de administración en Chrome (alta de miembro,
clave de puerta de enlace, publicación), arranca el cliente con su lanzador (`next build` + `next start`),
ejecuta el flujo del miembro (activar cuenta, iniciar sesión, ver solo lo publicado, chat con tokens en
streaming, sin clave ni host de la puerta de enlace en el navegador, otra organización sin acceso) y
detiene y elimina todo. Termina con `mvp-smoke: PASS` y código 0. Cada espera tiene límite.

### Opción 2: a mano

1. Pila (terminal 1, desde la raíz de este repositorio; compile `admin` antes con `npm run build`):

   ```powershell
   scripts\mvp-local.ps1 -RequireAdminBuild
   ```

   Imprime una línea JSON `ready` con `admin_url`, `workspace` y `credentials_file`.
2. Cliente (terminal 2, desde `clients\openyak`; el directorio de datos debe ser absoluto, estar fuera del
   repositorio y no ser el de OpenYak real):

   ```powershell
   node scripts/forge-managed.mjs --control-plane-origin http://127.0.0.1:3410 --data-dir "$env:TEMP\forge-client-data"
   ```

   Hace la compilación de producción (varios minutos) y escribe `{"stage":"ready",...}` cuando 3411 responde.
3. Abrir la administración: `http://127.0.0.1:3410/admin/`. Abrir el cliente: `http://127.0.0.1:3411`.
4. Credenciales: archivo `credentials.json` dentro del espacio de trabajo privado que informa la línea
   `ready` (`credentials_file`). Ábralo solo en local; no lo pegue ni lo imprima. Contiene las cuentas de
   `org-a` y `org-b` y la clave de puerta de enlace de cada una.
5. Recorrido: en la administración inicie sesión como administrador de `org-a`, invite a un miembro
   (Members), guarde la puerta de enlace `http://127.0.0.1:3413` con la clave de `org-a` (Gateway), actualice
   y publique el catálogo (Catalog). El correo queda en `<espacio de trabajo>\mailbox\*.eml`: abra el enlace
   `http://127.0.0.1:3411/onboarding#...` que contiene, active la cuenta y entre en el cliente.
6. Detener: `Ctrl+C` en cada terminal (cliente primero). La pila elimina su contenedor y su espacio de
   trabajo; borre el directorio de datos del cliente.

### Límites conocidos

- Un proceso del cliente se une a un solo perfil de miembro: para entrar como otra persona (u otra
  organización) reinicie el cliente. El segundo inicio de sesión recibe una denegación, sin datos del primero.
- `next build` reescribe `frontend/next-env.d.ts` y `frontend/tsconfig.json` (archivos versionados); descarte
  esos cambios con `git checkout` antes de confirmar.
- El inicio de sesión tiene un límite por cuenta en ventanas de 15 minutos; repetir ejecuciones contra la misma
  pila puede bloquear temporalmente a la persona administradora (una pila nueva lo restablece).
- Docker Desktop (almacén containerd) puede fallar en `docker image inspect` por resumen hasta usar la imagen
  una vez (`CACHED_PINNED_IMAGE_REQUIRED`): `scripts\mvp-smoke.ps1` lo resuelve con un contenedor descartable;
  a mano, ejecute `docker run --rm --pull never --entrypoint postgres <imagen> --version` y reintente.

Diseño y especificaciones: `openspec/changes/prometheon-forge-mvp/`.