# Database

> **Navigation aid.** Schema shapes and field types extracted via AST. Read the actual schema source files before writing migrations or query logic.

**prisma** — 6 models

### User

pk: `id` (String)

- `id`: String _(pk, default)_
- `email`: String _(unique, nullable)_
- `password`: String _(nullable)_
- `emailVerified`: DateTime _(nullable)_
- `image`: String _(nullable)_
- `profile`: Profile _(nullable)_
- `subscription`: Subscription _(nullable)_
- _relations_: accounts: Account[], sessions: Session[]

### Profile

pk: `id` (String) · fk: userId

- `id`: String _(pk, default)_
- `userId`: String _(unique, fk)_
- `is_allowed`: Boolean _(default)_
- `plan`: String _(default)_
- `quota_total`: Int _(default)_
- `quota_used`: Int _(default)_
- `quota_reset`: DateTime _(nullable)_
- _relations_: user: User

### Subscription

pk: `id` (String) · fk: userId, paypalSubId

- `id`: String _(pk, default)_
- `userId`: String _(unique, fk)_
- `paypalSubId`: String _(unique, nullable, fk)_
- `plan`: String _(default)_
- `status`: String _(default)_
- `currentPeriodEnd`: DateTime _(nullable)_
- _relations_: user: User

### Account

pk: `id` (String) · fk: userId, providerAccountId

- `id`: String _(pk, default)_
- `userId`: String _(fk)_
- `type`: String
- `provider`: String
- `providerAccountId`: String _(fk)_
- `refresh_token`: String _(nullable)_
- `access_token`: String _(nullable)_
- `expires_at`: Int _(nullable)_
- `token_type`: String _(nullable)_
- `scope`: String _(nullable)_
- `id_token`: String _(nullable)_
- `session_state`: String _(nullable)_
- _relations_: user: User

### Session

pk: `id` (String) · fk: userId

- `id`: String _(pk, default)_
- `sessionToken`: String _(unique)_
- `userId`: String _(fk)_
- `expires`: DateTime
- _relations_: user: User

### VerificationToken

- `identifier`: String
- `token`: String _(unique)_
- `expires`: DateTime

## Schema Source Files

Read and edit these files when adding columns, creating migrations, or changing relations:

- `/models.py` — imported by **4** files
- `//models.py` — imported by **2** files

---
_Back to [overview.md](./overview.md)_