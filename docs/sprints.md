# Entregas incrementales de Prometheon Forge

Construir un producto genérico sin modificar el hotel operativo ni los snapshots
de OpenYak y OmniRoute. Los incrementos expresan dependencias, no fechas prometidas.

| Sprint | Entrega | Condición de salida |
|---|---|---|
| S1 | Contratos ejecutables y política de membresías | Denegaciones entre organizaciones y por suspensión; bootstrap sin secretos; DB/RLS se prueban por separado |
| S2 | Inicio corporativo y spike del cliente | Entra PKCE y sesión Forge validados; sin claves manuales ni identidad de prueba en producción |
| S3 | Administración y marca por organización | Altas, bajas y configuración versionada; dos empresas con el mismo cliente |
| S4 | OmniRoute y presupuestos | Rutas y capacidades por empresa; reservas atómicas; límites y reintentos veraces |
| S5 | Herramientas de imágenes | Trabajos idempotentes con propietario; referencias, edición y descarga autorizada; costos ocultos al usuario |
| S6 | Skills y auditoría | Respaldo de borradores separado de publicación revisada; grants, restauración y eventos redactados |
| S7 | Empaquetado y piloto | Actualizador Windows firmado; instalación limpia y restauración; piloto del hotel y segunda organización |

## Primer corte de S1

Implementar únicamente autorización de membresías y proyección pública de bootstrap
como dominio puro. El contrato detallado está en [foundation.md](changes/foundation.md).
No constituye la API completa PF-10 ni demuestra aislamiento PostgreSQL.

## Dependencias y siguiente paso

Antes de cerrar S1 faltan contratos HTTP, adaptadores confiables y pruebas reales de
PostgreSQL/RLS. S2 requiere registro y consentimiento Entra autorizados. Integraciones,
gastos, acceso remoto y cambios productivos requieren autorización separada.
Refinar estimaciones después de medir el primer corte, no antes de tener evidencia.

## Segundo corte de S1: transporte de bootstrap

F04 añade `/forge/v1/bootstrap` y liveness `/healthz` con denegación predeterminada,
puertos confiables inyectados y errores estructurados. Contrato: [api-bootstrap.md](changes/api-bootstrap.md).
La autoverificación local, verificación independiente y spot check del padre pasaron.
Commit documentado en el task; revisión nativa no aprobada. Sin Entra ni PostgreSQL/RLS, por lo
que S1 continúa abierto. F05 reserva la prueba real de DB/RLS como unidad separada.
