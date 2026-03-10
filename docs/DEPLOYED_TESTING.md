# Deployed Environment Testing

This repository includes a Vitest suite for validating the deployed frontend and backend:

- Vercel frontend smoke coverage
- Railway backend reachability
- frontend-to-backend proxy checks
- optional paid digital-human end-to-end verification

## Command

```bash
npm run test:deployed
```

## Required env vars

```bash
DEPLOYED_FRONTEND_URL=https://your-frontend.vercel.app
DEPLOYED_BACKEND_URL=https://your-backend.railway.app
```

## Optional env vars

Use these when your deployed backend requires auth or when you want deeper verification.

```bash
DEPLOYED_BACKEND_BEARER_TOKEN=
DEPLOYED_TEST_EMAIL=integration-test@example.com
```

## Optional paid E2E

These tests create real digital-human jobs and may incur external API costs.
The default short-audio fixture now uses `https://s.autoviralvid.com/uploads/test_dh_audio_20s_20260310.mp3`
to avoid third-party CDN access issues.

```bash
ALLOW_PAID_DEPLOYED_E2E=1
RUN_DEPLOYED_DIGITAL_HUMAN_E2E=1
DEPLOYED_DIGITAL_HUMAN_AUDIO_URL=https://...
DEPLOYED_DIGITAL_HUMAN_AVATAR_URL=https://...
DEPLOYED_DIGITAL_HUMAN_TIMEOUT_MS=900000
DEPLOYED_DIGITAL_HUMAN_POLL_INTERVAL_MS=15000
```

For long-audio verification:

```bash
ALLOW_PAID_DEPLOYED_E2E=1
RUN_DEPLOYED_LONG_DIGITAL_HUMAN_E2E=1
DEPLOYED_LONG_DIGITAL_HUMAN_AUDIO_URL=https://...
DEPLOYED_LONG_DIGITAL_HUMAN_DURATION=240
```

Paid E2E also requires the deployed backend to have a valid `RUNNINGHUB_API_KEY`.

## What the suite checks

Smoke tests:

- homepage
- privacy/terms/robots/sitemap
- auth token endpoint
- forgot-password validation path
- render job submission endpoint
- agent sessions proxy
- quota endpoint
- backend docs
- backend `/api/v1/projects` auth posture

Paid E2E tests:

- create digital-human project
- submit digital-human generation
- poll status until completion
- verify final video URL is returned
