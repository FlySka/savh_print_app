# DB Summary

## Panorama general

- Base PostgreSQL con `70` tablas y `137` FKs declaradas en `docs/generated/db/bd_resume.csv`.
- Schemas detectados:
  - `core`: `57` tablas
  - `public`: `10` tablas
  - `ingest`: `2` tablas
  - `audit`: `1` tabla
- El repo modela `55` tablas con `managed = False`.
- Hay `9` tablas físicas creadas desde migraciones SQL del repo aunque sus modelos sigan con `managed = False`.
- Hay `5` tablas visibles en BD sin app activa dueña en `INSTALLED_APPS`.
- La referencia exacta de columnas, PK y FK vive en `docs/generated/db/bd_resume.csv`.
- El mapa visual de relaciones vive en `docs/generated/db/bd_schema.png`.

## Clasificación por administración de tablas

### Tablas estándar de Django y contrib en `public`

- Estas tablas sí forman parte de la persistencia estándar de Django para autenticación, permisos, sesión, admin y migraciones.
- Tablas:
  - `public.auth_group`
  - `public.auth_group_permissions`
  - `public.auth_permission`
  - `public.auth_user`
  - `public.auth_user_groups`
  - `public.auth_user_user_permissions`
  - `public.django_admin_log`
  - `public.django_content_type`
  - `public.django_migrations`
  - `public.django_session`

### Tablas `managed = False` materializadas desde migraciones SQL del repo

- `pricing`
  - `core.price_lists`
  - `core.price_rules`
  - `core.customer_price_list_assignments`
  - `core.customer_price_overrides`
- `inventory`
  - `core.inventory_stock_entries`
  - `core.inventory_stock_movements`
  - `core.inventory_sale_assignments`
  - `core.inventory_sale_assignment_lines`
- `cashflow`
  - `core.cashflow_movements`

### Tablas `managed = False` preexistentes o externas al ORM normal

- Aquí cae el resto de tablas `core`, `audit` e `ingest`.
- El repo las modela o las consume, pero no las administra con migraciones ORM estándar.
- También viven aquí las tablas existentes sin owner activo en apps actuales, como `core.app_users`, `core.deliveries` y el subdominio de comisiones de vendedores.

## Mapa por app activa y tablas que usa hoy

### `catalog`

- `core.dim_payment_methods`
- `core.dim_expense_groups`
- `core.dim_expense_types`
- `core.dim_economic_types`
- `core.dim_sales_statuses`
- `core.dim_sales_billing_statuses`
- `core.dim_sales_payment_statuses`
- `core.dim_sale_types`
- `core.dim_commercial_models`
- `core.dim_customer_types`
- `core.dim_order_statuses`
- `core.dim_purchase_statuses`
- `core.dim_shipping_statuses`
- `core.dim_entity_type`
- `core.dim_event_type`

### `products`

- `core.products`
- `core.codes`
- `core.dim_categories`
- `core.dim_varieties`
- `core.dim_calibers`
- `core.dim_conventions`

### `parties`

- `core.parties`
- `core.parties_customer`
- `core.parties_supplier`
- `core.parties_salesperson`
- `core.parties_employee`
- `core.parties_recipient`

### `possessions`

- `core.dim_type_assets`
- `core.assets`
- `core.assets_vehicles`

### `audit_logs`

- `audit.audit_log`

### `ingests`

- `ingest.ingest_events`
- `ingest.entity_events`

### `purchases`

- `core.product_purchases`
- `core.product_purchase_items`

### `inventory`

- `core.product_receipts`
- `core.product_receipt_items`
- `core.product_losses`
- `core.inventory_stock_entries`
- `core.inventory_stock_movements`
- `core.inventory_sale_assignments`
- `core.inventory_sale_assignment_lines`

### `pricing`

- `core.price_lists`
- `core.price_rules`
- `core.customer_price_list_assignments`
- `core.customer_price_overrides`

### `sales`

- `core.orders`
- `core.order_items`
- `core.sales`
- `core.sale_items`

### `treasury`

- `core.payments`
- `core.payment_applications`
- `core.expenses`
- `core.purchase_payment_applications`

### `cashflow`

- `core.cashflow_movements`

### `users`

- `users` es un app transversal apoyado en tablas estándar de Django, no dueño de tablas operativas `core.*`.
- Persistencia base usada por autenticación web, permisos, sesión, admin y metadatos:
  - `public.auth_group`
  - `public.auth_group_permissions`
  - `public.auth_permission`
  - `public.auth_user`
  - `public.auth_user_groups`
  - `public.auth_user_user_permissions`
  - `public.django_admin_log`
  - `public.django_content_type`
  - `public.django_migrations`
  - `public.django_session`

## Tablas existentes sin app activa dueña hoy

- `core.app_users`
  - tabla legacy de compatibilidad operativa
  - varias columnas `*_user_id` y `deleted_by_user_id` referencian esta tabla, no `public.auth_user`
  - no equivale al modelo `User` activo de Django
  - apps que la usan hoy como compatibilidad de actor: `audit_logs`, `ingests`, `purchases`, `inventory`, `sales` y `treasury`
- `core.deliveries`
  - tabla existente en BD ligada a `core.orders`
  - hoy no existe un app activo `deliveries` en `INSTALLED_APPS`
  - debe tratarse como subdominio visible en la BD, pero no como módulo activo del repo
  - uso visible hoy: referencia documental desde `sales` y placeholder de navegación compartida; no hay owner runtime activo identificado
- `core.dim_salesperson_contract_types`
  - dimensión de tipos de contrato de vendedor
  - uso hoy: sin app activa consumidora identificada en runtime
- `core.dim_salesperson_commission_bases`
  - dimensión de bases de comisión de vendedor
  - uso hoy: sin app activa consumidora identificada en runtime
- `core.salesperson_contracts`
  - subdominio de contratos/comisiones de vendedores
  - referencia `core.parties_salesperson`, `core.dim_salesperson_contract_types` y `core.dim_salesperson_commission_bases`
  - hoy no tiene owner explícito en apps activas
  - uso hoy: sin app activa consumidora identificada en runtime

## Relaciones y observaciones importantes

- `core.parties` es la raíz de clientes, proveedores, vendedores, empleados y destinatarios.
- `core.products` es la raíz de productos y dimensiones comerciales consumidas por compras, ventas e inventario.
- `core.orders` conecta cliente y destinatario; `core.sales` referencia `core.orders`.
- `core.payments` se aplica a ventas mediante `core.payment_applications`.
- `core.expenses` se aplica a compras mediante `core.purchase_payment_applications`.
- `core.product_receipt_items` alimenta `core.inventory_stock_entries`.
- `core.inventory_stock_movements` deja trazabilidad append-only de recepción, ubicación, traslado, repesaje, merma y consumo.
- `core.inventory_sale_assignments` y `core.inventory_sale_assignment_lines` conectan `inventory` con `core.sale_items` sin mover la lógica física a `sales`.
- Muchas tablas transaccionales exponen `deleted_at`, `deleted_by_user_id` e `ingest_event_id`.
- `core.product_purchases` mantiene `estado_compra_id` como estado funcional visible y `is_active` como bandera operativa real.
- `audit.audit_log` guarda snapshots JSON de cambios.
- `ingest.ingest_events` y `ingest.entity_events` modelan trazabilidad de integración externa.
- Algunas columnas `*_id` relevantes no tienen FK declarada en la BD; cuando importe la integridad exacta, manda `docs/generated/db/bd_resume.csv`.

## Nota arquitectónica

- Este documento resume la base de datos, pero no reemplaza la arquitectura del repo.
- Ownership de apps, fronteras públicas y reglas cross-app viven en `README.md`, `AGENTS.md`, `docs/architecture/cross_app_boundaries.md` y `docs/architecture/audits/2026-04-01_modular_monolith_audit.md`.
- Si una documentación vieja contradice al repo real, mandan el código actual y la auditoría repo-level.

## Fuente de verdad estructural

- `docs/generated/db/bd_resume.csv`
- `docs/generated/db/bd_schema.png`
