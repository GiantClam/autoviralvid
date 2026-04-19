# Subscription + Credits + Billing Implementation Plan


> Status update (2026-04-16): Any V7 endpoint billing references are decommissioned and historical only.
> Current production PPT chargeable endpoint: `/ppt/generate-from-prompt`.

> Use this plan to execute the work task-by-task with tight verification after each step.

**Goal:** 在 Vercel 部署架构下落地 `Stripe + PayPal + 统一积分账本 + 所有视频/生成类 API 扣费 + 失败回滚 + 对账` 的生产级计费系统。

**Architecture:** 保留现有 Next.js + FastAPI 双服务，不引入 Medusa 作为计费核心。采用“统一 Billing Core + Provider Adapter(Stripe/PayPal) + 账本(ledger) + API 网关扣费拦截”模型。所有前端流量统一经过 Next API 代理层进行鉴权、预扣费、失败补偿，Webhook 只负责订阅状态与充值入账，不直接改业务状态。

**Tech Stack:** Next.js App Router, Prisma(PostgreSQL), NextAuth, Stripe SDK, PayPal REST API/Webhook, FastAPI(既有业务后端), Vercel Cron/Background Job(对账)

---

## 0. 现状与差距（基于当前代码）

### 已有能力
- 已有 `Profile.quota_total/quota_used/quota_reset` 及 `Subscription(paypalSubId)`。
- 已有 PayPal 订阅创建与 webhook 处理：
  - `src/lib/paypal.ts`
  - `src/app/api/paypal/create-subscription/route.ts`
  - `src/app/api/paypal/webhook/route.ts`
- 已有部分生成链路扣费（pre-charge + failure refund）：
  - `src/app/api/projects/[...path]/route.ts`
  - `src/lib/quota.ts`

### 关键缺口
- 仅 PayPal，缺 Stripe 订阅与 webhook。
- 扣费是“计数器模式”，缺“可审计账本（ledger）”和幂等事件表。
- 仍存在绕过扣费路径：`src/app/ppt/page.tsx` 直接请求 `NEXT_PUBLIC_AGENT_URL/api/v1/ppt/*`。
- 扣费规则只覆盖部分 `/projects/{id}/...`，未统一覆盖全部生成型 API（当前重点为 `/ppt/generate-from-prompt`）。
- 缺 provider 无关的统一 Plan/Price Catalog。

### 架构决策
- 不采用 Medusa 作为主计费引擎（可做电商层，但不适合你当前“生成 API 按调用扣费”核心链路）。
- 继续自建 Billing Core，并将 Stripe/PayPal 作为支付通道适配器。

---

## 1. 目标能力（验收标准）

1. 支持 `Stripe + PayPal` 两种订阅购买、续费、取消、降级。
2. 所有“生成型 API”统一扣费，且可配置每个端点/动作的消耗单位。
3. 扣费具有幂等性（重试不重复扣）与失败补偿（业务失败自动退款）。
4. 账本可审计：每次预扣、确认、退款、充值、订阅赠送都可追踪。
5. 前端不允许直连可计费后端端点（统一经 Next API 代理）。
6. 具备日常对账任务，发现漏单/重复扣费时可自动告警。

---

## 2. 领域模型与数据设计

### Task 1: 建立统一账本与支付事件模型

**Files:**
- Modify: `prisma/schema.prisma`
- Create: `prisma/migrations/<timestamp>_billing_core/*`
- Modify: `src/lib/prisma.ts`（若需导出新模型 helper）

**Step 1: 新增模型（最小闭环）**
- `BillingLedger`：
  - `id, userId, type(debit|credit|refund|grant), units, source(subscription|api_usage|manual), referenceType, referenceId, idempotencyKey, metadata, createdAt`
- `BillingUsageRecord`：
  - `id, userId, endpoint, method, units, status(precharged|committed|refunded), requestId, runId, providerTraceId, idempotencyKey, createdAt, updatedAt`
- `PaymentCustomer`：
  - `id, userId, provider(stripe|paypal), providerCustomerId, createdAt`
- `PaymentSubscription`：
  - `id, userId, provider, providerSubId, planCode, status, currentPeriodStart, currentPeriodEnd, cancelAtPeriodEnd, metadata`
- `PaymentWebhookEvent`：
  - `id, provider, eventId(unique), eventType, payloadHash, processedAt, status`
- `PlanCatalog`（可先静态配置，后续再表化）

**Step 2: 保留兼容字段**
- 继续保留 `Profile.quota_*`（迁移期读取兼容），新逻辑以 ledger 为准，quota 作为缓存/投影。

**Step 3: 生成迁移并校验**
Run: `npx prisma migrate dev --name billing_core`
Expected: migration 成功且 Prisma Client 可生成。

**Step 4: 类型检查**
Run: `npx tsc --noEmit`
Expected: PASS。

---

## 3. 统一计费核心（Provider 无关）

### Task 2: 实现 Billing Core Service

**Files:**
- Create: `src/lib/billing/types.ts`
- Create: `src/lib/billing/plan-catalog.ts`
- Create: `src/lib/billing/ledger.ts`
- Create: `src/lib/billing/usage-charger.ts`
- Modify: `src/lib/quota.ts`（改为调用 ledger 读写）

**Step 1: 统一 Plan 定义**
- `plan-catalog.ts` 只维护一次：`free/pro/enterprise` 的价格、月赠送积分、provider price id 映射。
- 消除 `paypal.ts` 与其他位置的重复 plan 常量。

**Step 2: 账本能力**
- `grantMonthlyCredits(userId, planCode)`
- `prechargeUsage({userId, endpoint, units, idempotencyKey})`
- `commitUsage(usageRecordId)`
- `refundUsage(usageRecordId, reason)`
- `getBalance(userId)`

**Step 3: 幂等保证**
- 对 `idempotencyKey` 建唯一约束。
- 同 key 重试返回同一 usage record，不重复扣费。

**Step 4: 保持旧接口兼容**
- `checkQuota/consumeQuota/refundQuota` 内部转调新账本逻辑，避免前端立刻大改。

**Step 5: 单测**
- Create: `src/lib/billing/__tests__/ledger.test.ts`
- 覆盖：并发预扣、重复请求幂等、失败退款、余额不足。

---

## 4. 支付通道：Stripe + PayPal

### Task 3: Provider Adapter 抽象

**Files:**
- Create: `src/lib/billing/providers/types.ts`
- Create: `src/lib/billing/providers/stripe.ts`
- Create: `src/lib/billing/providers/paypal.ts`
- Modify: `src/lib/paypal.ts`（降级为 provider 实现或封装迁移）

**Step 1: 统一接口**
- `createCheckoutSession(planCode, user)`
- `cancelSubscription(subscriptionId)`
- `parseWebhook(request)`
- `mapEventToDomainEvent(...)`

**Step 2: Stripe 实现**
- 使用 `stripe.checkout.sessions.create(mode=subscription)`。
- 保存 `customer`、`subscription` 映射。

**Step 3: PayPal 实现**
- 复用现有逻辑，补齐 webhook 校验与事件映射。

---

### Task 4: API 路由（支付）

**Files:**
- Create: `src/app/api/billing/checkout/stripe/route.ts`
- Create: `src/app/api/billing/checkout/paypal/route.ts`
- Create: `src/app/api/billing/portal/stripe/route.ts`
- Create: `src/app/api/billing/subscription/route.ts`
- Create: `src/app/api/billing/webhook/stripe/route.ts`
- Create: `src/app/api/billing/webhook/paypal/route.ts`
- Modify: `src/app/api/paypal/*`（兼容到新路由，逐步废弃）

**Step 1: 下单入口统一**
- 前端统一调 `/api/billing/checkout/:provider`。

**Step 2: webhook 幂等处理**
- 先写 `PaymentWebhookEvent` 再处理业务，重复 eventId 直接 ACK。

**Step 3: 订阅状态投影**
- webhook 仅更新 `PaymentSubscription` + 调用 `grantMonthlyCredits`。

**Step 4: 集成测试**
- Create: `src/app/api/billing/__tests__/webhook-idempotency.test.ts`
- 覆盖重复事件、乱序事件、撤销与恢复。

---

## 5. 全量生成 API 扣费覆盖

### Task 5: 建立“计费端点策略表”并统一接入

**Files:**
- Create: `src/lib/billing/charge-policy.ts`
- Modify: `src/app/api/projects/[...path]/route.ts`
- Create: `src/app/api/ppt/[...path]/route.ts`
- Modify: `src/app/ppt/page.tsx`
- Modify: `src/components/ProjectForm.tsx`（仅保留 prompt 生成链路）

**Step 1: 策略表化**
- 按 endpoint + method 配置 `units`，例如：
  - `/projects/{id}/storyboard` = 1
  - `/projects/{id}/images` = 1
  - `/projects/{id}/videos` = 1
  - `/projects/{id}/digital-human` = 2
  - `/projects/{id}/render` = 1
  - `/ppt/generate-from-prompt` = 1

**Step 2: 代理层统一预扣费**
- `projects` 代理继续保留，改为基于 `charge-policy.ts` 判定。
- 新增 `ppt` 代理，禁止前端直连 `NEXT_PUBLIC_AGENT_URL/api/v1/ppt/*`。

**Step 3: 失败补偿**
- 业务失败（HTTP 非 2xx 或 envelope success=false）自动 `refundUsage`。

**Step 4: 幂等键规则**
- 默认键：`userId + method + normalizedPath + bodyHash + 10min time bucket`。
- 若前端传 `X-Idempotency-Key`，优先使用。

**Step 5: 端到端验证**
- 执行现有 E2E：
  - `python scripts/ui_ppt_prompt_web_e2e.py`
  - `npm run test:integration`
- 验证：每次成功生成产生 debit；失败路径产生 refund。

---

## 6. 前端订阅与积分体验

### Task 6: Checkout 与配额展示统一

**Files:**
- Modify: `src/components/PricingModal.tsx`
- Modify: `src/components/QuotaBar.tsx`
- Create: `src/app/api/billing/me/route.ts`
- Modify: `src/lib/i18n/en.ts`, `src/lib/i18n/zh.ts`

**Step 1: 双通道支付 UI**
- PricingModal 提供 Stripe / PayPal 选择。

**Step 2: 展示余额来源**
- 显示 `monthly grant + purchased credits + consumed + remaining`。

**Step 3: 错误文案标准化**
- 区分 `quota_exceeded`、`billing_unavailable`、`provider_unavailable`。

---

## 7. 对账、风控与运维

### Task 7: 对账与告警

**Files:**
- Create: `src/lib/billing/reconcile.ts`
- Create: `src/app/api/internal/billing/reconcile/route.ts`
- Create: `scripts/billing/reconcile.ts`
- Modify: `vercel.json`（增加 Cron）
- Create: `docs/runbooks/billing-reconcile.md`

**Step 1: 日对账**
- 比较 `PaymentSubscription` / provider 事件 / `BillingLedger`。
- 输出 mismatch 列表（漏记、重复扣费、漏退款）。

**Step 2: 告警**
- mismatch > 0 触发日志告警（后续可接 Sentry/Slack）。

**Step 3: 回放修复脚本**
- 支持按 `eventId` 重新处理 webhook。

---

## 8. 迁移与灰度发布

### Task 8: 分阶段上线

**Files:**
- Create: `docs/plans/rollout-billing-v2-checklist.md`
- Modify: `.env.example`
- Modify: `docs/VERCEL_RAILWAY_SPLIT_DEPLOYMENT.md`

**Step 1: 环境变量**
- Stripe: `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PRICE_PRO`, `STRIPE_PRICE_ENTERPRISE`
- PayPal: `PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET`, `PAYPAL_WEBHOOK_ID`, `PAYPAL_PLAN_PRO`, `PAYPAL_PLAN_ENTERPRISE`
- Core: `GENERATION_BILLING_ENABLED=true`, `BILLING_STRICT_MODE=true`

**Step 2: 灰度开关**
- `BILLING_ENFORCE_PPT=false`（先观察后开启）
- 稳定后全量置 true。

**Step 3: 回滚策略**
- 仅关闭 enforcement，不关闭 webhook 入账。

---

## 9. 测试计划（必须通过）

### Task 9: 测试矩阵

**Files:**
- Create: `src/lib/billing/__tests__/usage-charger.test.ts`
- Create: `src/app/api/projects/__tests__/billing-proxy.test.ts`
- Create: `src/app/api/ppt/__tests__/billing-proxy.test.ts`
- Modify: `src/integration/deployed-environment.test.ts`

**Step 1: 单元测试**
- 账本 debit/refund/幂等/并发。

**Step 2: 路由测试**
- 命中计费端点扣费。
- 非计费端点不扣费。
- 下游失败自动退款。

**Step 3: 集成测试**
- Stripe/PayPal webhook 模拟。
- 全流程：购买 -> 入账 -> 生成扣费 -> 失败退款。

**Step 4: 回归命令**
Run:
- `npx prisma generate`
- `npx tsc --noEmit`
- `npm run lint`
- `npm test`
Expected: 全部 PASS。

---

## 10. 最终落地顺序（建议 2 周）

- Day 1-2: Task 1-2（数据层 + 核心账本）
- Day 3-4: Task 3-4（Stripe/PayPal adapter + webhook）
- Day 5-6: Task 5（全量 API 扣费接入）
- Day 7: Task 6（前端支付/积分）
- Day 8: Task 7（对账）
- Day 9: Task 9（测试收敛）
- Day 10: Task 8（灰度发布）

---

## 11. 风险与控制

- 风险: 重复 webhook 导致重复入账。
  - 控制: `PaymentWebhookEvent.eventId` 唯一约束 + 幂等处理。
- 风险: 前端绕过代理直连后端。
  - 控制: 前端仅允许 `/api/*`，并在后端对公网请求做签名或 token 校验。
- 风险: 失败退款遗漏导致用户投诉。
  - 控制: usage 记录状态机 + 定时对账 + 手工回放工具。

---

## 12. 完成定义（DoD）

- Stripe 与 PayPal 均可完成订阅支付与续费事件处理。
- 生成类 API 全覆盖扣费并具备失败自动退款。
- 所有扣费动作在 ledger 中可追溯。
- 无前端直连可计费后端 API。
- 核心测试、集成测试、E2E 全通过。
- Runbook 和部署文档更新完成。
