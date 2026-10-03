# SDD: autorización y bootstrap de dominio

Primer corte de S1: un sujeto autenticado solo obtiene la proyección pública de una
organización activa donde su membresía está activa. Fuente: PF-02 y PF-10 en los
documentos de diseño externos `outputs/prometheon-forge/specs/`.

## Contrato

La identidad es un valor inmutable entregado por un futuro adaptador que validará
la sesión corporativa. Construir este valor no autentica a nadie. No se interpretan
cabeceras, correos ni tokens en este módulo; no existe autenticación simulada HTTP.

La decisión compara sujeto, organización solicitada, organización de la membresía
y organización de la configuración. Toda discordancia deniega. Organización y
membresía deben estar activas. El bootstrap enumera campos públicos explícitamente;
nunca expande diccionarios arbitrarios de configuración.

## Aceptación ejecutable

Los casos se ubican en `tests/test_foundation.py` y se ejecutan con
`python -m unittest discover -s tests -v`.

| Caso | Prueba | Resultado |
|---|---|---|
| A01 | `test_missing_identity_denied` | Sin contexto autenticado, deniega |
| A02 | `test_unknown_membership_denied` | Sin membresía conocida, deniega |
| A03 | `test_wrong_requested_organization_denied` | Organización ajena solicitada, deniega |
| A04 | `test_inactive_membership_denied` | Membresía suspendida o archivada, deniega |
| A05 | `test_inactive_organization_denied` | Organización inactiva, deniega |
| A06 | `test_active_member_receives_public_bootstrap` | Membresía propia activa, permite |
| A07 | `test_bootstrap_is_allowlisted` | Omite secretos, claves, costos y configuración administrativa |
| A08 | `test_other_subject_denied` | Membresía de otro sujeto, deniega |
| A09 | `test_foreign_configuration_denied` | Configuración de otra organización, deniega |
| A10 | `test_identity_is_immutable` | El contexto no puede mutarse |
| A11 | `test_foreign_organization_record_denied` | Registro de organización ajena, deniega |
| A12 | `test_foreign_membership_record_denied` | Registro de membresía ajena, deniega |
| A13 | `test_empty_identity_fields_denied` | Proveedor, emisor o sujeto nulo, vacío o en blanco, deniega |

## Límites y verificación

No incluye login, endpoints, DB/RLS, proveedores, presupuestos ni cliente. Las
capacidades efectivas y el resto de PF-10 quedan pendientes: no se fabrican grants.
El adaptador futuro debe consultar datos confiables y aplicar revocaciones por solicitud.
Errores de dominio no son todavía códigos HTTP.

Observar RED antes de implementar, luego GREEN, `python -m compileall -q src tests`
y `git diff --check`. Un runner ausente no cuenta como RED. Verificación de runtime:
no aplica porque todavía no hay un límite HTTP. La reversión de este corte elimina
el módulo, sus pruebas y configuración del proyecto sin afectar sistemas externos.

El runtime local Python 3.12.14 no incluye pytest. Se usa `unittest` estándar sin
instalaciones ni dependencias adicionales; la política RED → GREEN no cambia.


## Evidencia del primer corte

En la carpeta canónica `N:/Proyects/forge`, Python 3.12.14 ejecutó 13 pruebas:
RED con 23 errores de `NotImplementedError` (incluye subcasos), después GREEN con
13 pruebas aprobadas. `compileall` pasó. No hubo instalaciones ni servicios externos.
La revisión independiente y los commits siguen pendientes; S1 no está cerrado.
