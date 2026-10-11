# MVP local de Prometheon Forge

> Estado: borrador (stub). Este documento se completa en las rebanadas A5b y
> Final de `openspec/changes/prometheon-forge-mvp/`. No describe todavía
> comandos ejecutables.

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

## Pendiente

- Arranque supervisado (`scripts/mvp-local.ps1`) y aprovisionamiento de organizaciones.
- Compilación de la administración web (`src/forge/web/admin/`, ignorada por Git).
- Prueba de humo de extremo a extremo (`scripts/mvp-smoke.ps1`).

Diseño y especificaciones: `openspec/changes/prometheon-forge-mvp/`.
