# MVP local de Prometheon Forge

> Estado: plano de control, puerta de enlace falsa y aprovisionamiento listos.
> La administración web (`/admin/`) se compila desde `admin/`; sin compilación responde un
> 503 con un mensaje claro y `/status` informa `"admin": "missing"`. El cliente se
> incorpora en la rebanada C de `openspec/changes/prometheon-forge-mvp/`.

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

## Pendiente

- Prueba de humo de extremo a extremo (`scripts/mvp-smoke.ps1`).

Diseño y especificaciones: `openspec/changes/prometheon-forge-mvp/`.
