# Schema

### User
- id: String (pk, default)
- email: String (unique, nullable)
- password: String (nullable)
- emailVerified: DateTime (nullable)
- image: String (nullable)
- profile: Profile (nullable)
- subscription: Subscription (nullable)
- _relations_: accounts: Account[], sessions: Session[]

### Profile
- id: String (pk, default)
- userId: String (unique, fk)
- is_allowed: Boolean (default)
- plan: String (default)
- quota_total: Int (default)
- quota_used: Int (default)
- quota_reset: DateTime (nullable)
- _relations_: user: User

### Subscription
- id: String (pk, default)
- userId: String (unique, fk)
- paypalSubId: String (unique, nullable, fk)
- plan: String (default)
- status: String (default)
- currentPeriodEnd: DateTime (nullable)
- _relations_: user: User

### Account
- id: String (pk, default)
- userId: String (fk)
- type: String
- provider: String
- providerAccountId: String (fk)
- refresh_token: String (nullable)
- access_token: String (nullable)
- expires_at: Int (nullable)
- token_type: String (nullable)
- scope: String (nullable)
- id_token: String (nullable)
- session_state: String (nullable)
- _relations_: user: User

### Session
- id: String (pk, default)
- sessionToken: String (unique)
- userId: String (fk)
- expires: DateTime
- _relations_: user: User

### VerificationToken
- identifier: String
- token: String (unique)
- expires: DateTime
