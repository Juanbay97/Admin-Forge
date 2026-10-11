# MVP local de Prometheon Forge

> Estado: plano de control, puerta de enlace falsa y aprovisionamiento listos.
> La administración web (`/admin/`) y el cliente se incorporan en las rebanadas B y C
> de `openspec/changes/prometheon-forge-mvp/`; hasta entonces `/admin/` responde un
> 503 con un mensaje claro y `/status` informa `"admin": "missing"`.

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

## Pendiente

- Compilación de la administración web (`src/forge/web/admin/`, ignorada por Git).
- Prueba de humo de extremo a extremo (`scripts/mvp-smoke.ps1`).

Diseño y especificaciones: `openspec/changes/prometheon-forge-mvp/`.
