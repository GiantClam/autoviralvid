# Payments

> **Navigation aid.** Route list and file locations extracted via AST. Read the source files listed below before implementing or modifying this subsystem.

The Payments subsystem handles **1 routes** and touches: db, payment.

## Routes

- `POST` `/api/paypal/webhook` → out: { received } [db, payment]
  `src/app/api/paypal/webhook/route.ts`

## Source Files

Read these before implementing or modifying this subsystem:
- `src/app/api/paypal/webhook/route.ts`

---
_Back to [overview.md](./overview.md)_