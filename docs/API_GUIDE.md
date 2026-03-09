# AutoViralVid API Guide

> For frontend developers integrating with the backend API.

## Base URL

| Environment | URL |
|------------|-----|
| Development | `http://localhost:8123` |
| Production | Set via `NEXT_PUBLIC_API_BASE`, `NEXT_PUBLIC_AGENT_URL`, or `AGENT_URL` |

## Vercel Notes

When deploying the Next.js frontend to Vercel:

- `AUTH_SECRET` or `NEXTAUTH_SECRET` must be configured
- `NEXTAUTH_URL` or `NEXT_PUBLIC_SITE_URL` must be configured
- `AGENT_URL` or `NEXT_PUBLIC_AGENT_URL` must point to the deployed Python backend
- `NEXT_PUBLIC_API_BASE` is recommended for browser-side direct API clients

Production routes no longer fall back to `localhost`; missing backend/auth configuration now fails fast with a clear error instead of silently proxying to an invalid local address.

## Authentication

All protected endpoints require a JWT Bearer token:

```
Authorization: Bearer <token>
```

### Obtaining a Token

```typescript
// POST /api/auth/api-token (Next.js API route)
const res = await fetch('/api/auth/api-token', { method: 'POST' });
const { token } = await res.json();
```

The `project-client.ts` helper handles this automatically.

---

## Interactive Docs

The backend serves auto-generated API documentation:

- **Swagger UI**: `GET /docs`
- **ReDoc**: `GET /redoc`

---

## Core Endpoints

### 1. Create Project

```
POST /api/v1/projects
```

**Body:**
```json
{
  "template_id": "product-ad",
  "theme": "Summer sunscreen spray review",
  "product_image_url": "https://...",
  "style": "现代简约",
  "duration": 30,
  "orientation": "vertical",
  "aspect_ratio": "9:16"
}
```

**Digital Human extra fields:**
```json
{
  "template_id": "digital-human",
  "audio_url": "https://...",
  "voice_mode": 0,
  "motion_prompt": "Model doing product demo"
}
```

**Response:** `200` with project metadata including `run_id`.

### 2. Generate Storyboard

```
POST /api/v1/projects/{run_id}/storyboard
```

Triggers AI storyboard generation. Returns generated scenes.

### 3. Get Project Status

```
GET /api/v1/projects/{run_id}/status
```

Returns current project phase and progress details.

### 4. Submit Digital Human

```
POST /api/v1/projects/{run_id}/digital-human
```

Enqueues digital human video generation tasks.

### 5. File Upload

```
POST /upload/presign
```

**Body:**
```json
{
  "filename": "avatar.png",
  "content_type": "image/png"
}
```

**Response:**
```json
{
  "upload_url": "https://r2.../presigned-put-url",
  "public_url": "https://cdn.../avatar.png"
}
```

Upload the file directly to `upload_url` via HTTP PUT.

### 6. AI Chat Assistant

```
POST /api/v1/ai/chat
```

**Body:**
```json
{
  "message": "Help me write a video script about...",
  "project_context": { "template_id": "product-ad", "theme": "..." }
}
```

---

## Error Responses

All errors follow a consistent JSON envelope:

```json
{
  "error": "Error description",
  "details": [...]  // optional, for validation errors
}
```

| Status | Meaning |
|--------|---------|
| 401 | Unauthorized — invalid/missing JWT |
| 403 | Forbidden — insufficient permissions |
| 404 | Resource not found |
| 422 | Validation error — check `details` |
| 429 | Rate limited — check `Retry-After` header |
| 500 | Internal server error |

---

## Rate Limiting

Default: **120 requests/minute** per IP.

Response headers on all requests:
- `X-RateLimit-Limit`: Max requests per window
- `X-RateLimit-Remaining`: Remaining requests
- `Retry-After`: Seconds until reset (when limited)

---

## WebSocket / SSE

Some endpoints stream responses via Server-Sent Events (SSE):
- `/agent/session/{run_id}` — Real-time project generation updates
