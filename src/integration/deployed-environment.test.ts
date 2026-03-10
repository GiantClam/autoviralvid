import { describe, expect, it } from 'vitest';

const RUN_DEPLOYED_INTEGRATION_TESTS = process.env.RUN_DEPLOYED_INTEGRATION_TESTS === '1';
const RUN_DIGITAL_HUMAN_E2E = process.env.RUN_DEPLOYED_DIGITAL_HUMAN_E2E === '1';
const RUN_LONG_DIGITAL_HUMAN_E2E = process.env.RUN_DEPLOYED_LONG_DIGITAL_HUMAN_E2E === '1';
const ALLOW_PAID_DEPLOYED_E2E = process.env.ALLOW_PAID_DEPLOYED_E2E === '1';

const DEFAULT_AVATAR_URL =
  'https://cdn.pixabay.com/photo/2016/11/29/13/14/attractive-1869761_1280.jpg';
const DEFAULT_SHORT_AUDIO_URL =
  'https://s.autoviralvid.com/uploads/test_dh_audio_20s_20260310.mp3';

const FRONTEND_BASE_URL = normalizeBaseUrl(
  process.env.DEPLOYED_FRONTEND_URL || process.env.API_BASE,
);
const BACKEND_BASE_URL = normalizeBaseUrl(
  process.env.DEPLOYED_BACKEND_URL ||
    process.env.AGENT_URL ||
    process.env.NEXT_PUBLIC_AGENT_URL ||
    process.env.NEXT_PUBLIC_API_BASE,
);
const BACKEND_BEARER_TOKEN = process.env.DEPLOYED_BACKEND_BEARER_TOKEN;
const DEPLOYED_TEST_EMAIL =
  process.env.DEPLOYED_TEST_EMAIL || 'integration-test@example.com';
const DEPLOYED_SMOKE_TEST_TIMEOUT_MS = parseInteger(
  process.env.DEPLOYED_SMOKE_TEST_TIMEOUT_MS,
  15_000,
);
const DEPLOYED_FETCH_RETRY_COUNT = parseInteger(
  process.env.DEPLOYED_FETCH_RETRY_COUNT,
  3,
);
const DIGITAL_HUMAN_TIMEOUT_MS = parseInteger(
  process.env.DEPLOYED_DIGITAL_HUMAN_TIMEOUT_MS,
  15 * 60 * 1000,
);
const DIGITAL_HUMAN_POLL_INTERVAL_MS = parseInteger(
  process.env.DEPLOYED_DIGITAL_HUMAN_POLL_INTERVAL_MS,
  15_000,
);

const smokeDescribe = RUN_DEPLOYED_INTEGRATION_TESTS ? describe : describe.skip;
const paidDescribe =
  RUN_DEPLOYED_INTEGRATION_TESTS && ALLOW_PAID_DEPLOYED_E2E ? describe : describe.skip;
const shortDhDescribe =
  RUN_DEPLOYED_INTEGRATION_TESTS && ALLOW_PAID_DEPLOYED_E2E && RUN_DIGITAL_HUMAN_E2E
    ? describe
    : describe.skip;
const longDhDescribe =
  RUN_DEPLOYED_INTEGRATION_TESTS &&
  ALLOW_PAID_DEPLOYED_E2E &&
  RUN_LONG_DIGITAL_HUMAN_E2E
    ? describe
    : describe.skip;

function normalizeBaseUrl(value?: string) {
  if (!value) return '';
  return value.replace(/\/+$/, '');
}

function parseInteger(value: string | undefined, fallback: number) {
  const parsed = Number.parseInt(value || '', 10);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function requireEnv(name: string, value: string) {
  if (!value) {
    throw new Error(`Missing required env var: ${name}`);
  }
  return value;
}

function buildUrl(baseUrl: string, path: string) {
  return `${baseUrl}${path.startsWith('/') ? path : `/${path}`}`;
}

function createJsonHeaders(extra?: HeadersInit) {
  return {
    Accept: 'application/json',
    'Content-Type': 'application/json',
    ...(extra || {}),
  };
}

function createBackendHeaders() {
  if (!BACKEND_BEARER_TOKEN) {
    return createJsonHeaders();
  }

  return createJsonHeaders({
    Authorization: `Bearer ${BACKEND_BEARER_TOKEN}`,
  });
}

async function fetchWithTimeout(url: string, init?: RequestInit, timeoutMs = 30_000) {
  let lastError: unknown;

  for (let attempt = 1; attempt <= DEPLOYED_FETCH_RETRY_COUNT; attempt += 1) {
    try {
      return await fetch(url, {
        ...init,
        signal: AbortSignal.timeout(timeoutMs),
      });
    } catch (error) {
      lastError = error;
      if (attempt >= DEPLOYED_FETCH_RETRY_COUNT) {
        throw error;
      }
      await new Promise((resolve) => setTimeout(resolve, attempt * 500));
    }
  }

  throw lastError;
}

async function readJsonResponse(response: Response) {
  const text = await response.text();
  try {
    return {
      text,
      data: text ? JSON.parse(text) : null,
    };
  } catch {
    return {
      text,
      data: null,
    };
  }
}

function expectJsonContentType(response: Response) {
  expect(response.headers.get('content-type') || '').toContain('application/json');
}

function expectHtmlContentType(response: Response) {
  expect(response.headers.get('content-type') || '').toContain('text/html');
}

function pendingTaskCount(payload: any) {
  if (payload?.tasks_summary && typeof payload.tasks_summary === 'object') {
    const summary = payload.tasks_summary as Record<string, number>;
    return (
      (summary.queued || 0) +
      (summary.pending || 0) +
      (summary.processing || 0) +
      (summary.submitted || 0)
    );
  }
  return 0;
}

function extractTaskVideoUrls(payload: any) {
  if (!Array.isArray(payload?.tasks)) return [];
  return payload.tasks
    .map((task: any) => task?.video_url)
    .filter((value: unknown): value is string => typeof value === 'string' && value.length > 0);
}

async function fetchProjectByRunId(runId: string) {
  const backendBase = requireEnv('DEPLOYED_BACKEND_URL', BACKEND_BASE_URL);
  const response = await fetchWithTimeout(buildUrl(backendBase, `/api/v1/projects/${runId}`), {
    headers: createBackendHeaders(),
  });
  const payload = await readJsonResponse(response);
  return {
    response,
    payload,
  };
}

async function createDigitalHumanProject(options: {
  audioUrl: string;
  avatarUrl?: string;
  theme?: string;
  duration?: number;
}) {
  const backendBase = requireEnv('DEPLOYED_BACKEND_URL', BACKEND_BASE_URL);
  const response = await fetchWithTimeout(buildUrl(backendBase, '/api/v1/projects'), {
    method: 'POST',
    headers: createBackendHeaders(),
    body: JSON.stringify({
      template_id: 'digital-human',
      theme: options.theme || 'Digital human deployment verification',
      product_image_url: options.avatarUrl || DEFAULT_AVATAR_URL,
      style: 'modern clean',
      duration: options.duration || 30,
      orientation: 'portrait',
      aspect_ratio: '9:16',
      audio_url: options.audioUrl,
      voice_mode: 0,
      motion_prompt: 'Presenter introduces the product with natural hand movement',
    }),
  }, 60_000);
  const payload = await readJsonResponse(response);
  return {
    response,
    payload,
  };
}

async function submitDigitalHumanProject(runId: string) {
  const backendBase = requireEnv('DEPLOYED_BACKEND_URL', BACKEND_BASE_URL);
  const response = await fetchWithTimeout(
    buildUrl(backendBase, `/api/v1/projects/${runId}/digital-human`),
    {
      method: 'POST',
      headers: createBackendHeaders(),
    },
    60_000,
  );
  const payload = await readJsonResponse(response);
  return {
    response,
    payload,
  };
}

async function fetchDigitalHumanStatus(runId: string) {
  const backendBase = requireEnv('DEPLOYED_BACKEND_URL', BACKEND_BASE_URL);
  const response = await fetchWithTimeout(buildUrl(backendBase, `/api/v1/projects/${runId}/status`), {
    headers: createBackendHeaders(),
  });
  const payload = await readJsonResponse(response);
  return {
    response,
    payload,
  };
}

async function waitForFinalVideo(runId: string, timeoutMs: number) {
  const startedAt = Date.now();
  let lastStatusPayload: any = null;
  let lastProjectPayload: any = null;

  while (Date.now() - startedAt < timeoutMs) {
    const statusResult = await fetchDigitalHumanStatus(runId);
    expect(statusResult.response.ok).toBe(true);
    expectJsonContentType(statusResult.response);
    lastStatusPayload = statusResult.payload.data;

    const projectResult = await fetchProjectByRunId(runId);
    expect(projectResult.response.ok).toBe(true);
    expectJsonContentType(projectResult.response);
    lastProjectPayload = projectResult.payload.data;

    const projectVideoUrl = lastProjectPayload?.video_url;
    if (typeof projectVideoUrl === 'string' && projectVideoUrl.length > 0) {
      return {
        finalVideoUrl: projectVideoUrl,
        lastStatusPayload,
        lastProjectPayload,
      };
    }

    const taskVideoUrls = extractTaskVideoUrls(lastStatusPayload);
    if (taskVideoUrls.length > 0 && pendingTaskCount(lastStatusPayload) === 0) {
      return {
        finalVideoUrl: taskVideoUrls[taskVideoUrls.length - 1],
        lastStatusPayload,
        lastProjectPayload,
      };
    }

    if (lastStatusPayload?.has_failed && pendingTaskCount(lastStatusPayload) === 0) {
      throw new Error(
        `Digital human run ${runId} failed: ${JSON.stringify(lastStatusPayload)}`,
      );
    }

    await new Promise((resolve) => setTimeout(resolve, DIGITAL_HUMAN_POLL_INTERVAL_MS));
  }

  throw new Error(
    `Timed out waiting for final video for run ${runId}. Last status=${JSON.stringify(
      lastStatusPayload,
    )}, last project=${JSON.stringify(lastProjectPayload)}`,
  );
}

smokeDescribe('Deployed Environment Smoke Tests', { timeout: DEPLOYED_SMOKE_TEST_TIMEOUT_MS }, () => {
  it('requires DEPLOYED_FRONTEND_URL when deployed tests are enabled', () => {
    expect(requireEnv('DEPLOYED_FRONTEND_URL', FRONTEND_BASE_URL)).toMatch(/^https?:\/\//);
  });

  it('serves the public homepage', async () => {
    const response = await fetchWithTimeout(buildUrl(FRONTEND_BASE_URL, '/'));
    expect(response.ok).toBe(true);
    expectHtmlContentType(response);
    const html = await response.text();
    expect(html.toLowerCase()).toContain('<html');
  });

  it.each([
    '/legal/privacy',
    '/legal/terms',
    '/robots.txt',
    '/sitemap.xml',
  ])('serves %s without server errors', async (path) => {
    const response = await fetchWithTimeout(buildUrl(FRONTEND_BASE_URL, path));
    expect(response.status).toBeLessThan(500);
  });

  it('returns an auth-aware response from /api/auth/api-token', async () => {
    const response = await fetchWithTimeout(buildUrl(FRONTEND_BASE_URL, '/api/auth/api-token'), {
      method: 'POST',
      headers: createJsonHeaders(),
      body: JSON.stringify({}),
    });
    expectJsonContentType(response);
    expect([200, 401]).toContain(response.status);

    const payload = await readJsonResponse(response);
    if (response.status === 200) {
      expect(payload.data?.token).toEqual(expect.any(String));
    } else {
      expect(payload.data?.error).toBeTruthy();
    }
  });

  it('validates forgot-password input without 5xx errors', async () => {
    const invalidResponse = await fetchWithTimeout(
      buildUrl(FRONTEND_BASE_URL, '/api/auth/forgot-password'),
      {
        method: 'POST',
        headers: createJsonHeaders(),
        body: JSON.stringify({}),
      },
    );
    expect(invalidResponse.status).toBe(400);
    expectJsonContentType(invalidResponse);

    const validResponse = await fetchWithTimeout(
      buildUrl(FRONTEND_BASE_URL, '/api/auth/forgot-password'),
      {
        method: 'POST',
        headers: createJsonHeaders(),
        body: JSON.stringify({ email: DEPLOYED_TEST_EMAIL }),
      },
    );
    expect(validResponse.status).toBe(200);
    expectJsonContentType(validResponse);
  });

  it('accepts render job requests through the deployed frontend API', async () => {
    const response = await fetchWithTimeout(buildUrl(FRONTEND_BASE_URL, '/api/render/jobs'), {
      method: 'POST',
      headers: createJsonHeaders(),
      body: JSON.stringify({
        project: {
          name: 'Deployed smoke render job',
          width: 1280,
          height: 720,
          duration: 5,
          fps: 30,
          tracks: [],
        },
      }),
    });

    expect(response.ok).toBe(true);
    expectJsonContentType(response);
    const payload = await readJsonResponse(response);
    expect(payload.data?.status).toBe('accepted');
    expect(['dry_run', 'remote']).toContain(payload.data?.mode);
    expect(payload.data?.summary?.durationInFrames).toBe(150);
  });

  it('exposes agent session proxy without 5xx errors', async () => {
    const response = await fetchWithTimeout(
      buildUrl(FRONTEND_BASE_URL, '/api/agent/sessions?limit=1'),
      {
        headers: { Accept: 'application/json' },
      },
    );
    expect(response.status).toBeLessThan(500);
    expectJsonContentType(response);
  });

  it('exposes quota route without 5xx errors', async () => {
    const response = await fetchWithTimeout(buildUrl(FRONTEND_BASE_URL, '/api/quota'), {
      headers: { Accept: 'application/json' },
    });
    expect(response.status).toBeLessThan(500);
    expectJsonContentType(response);
  });

  it('serves backend docs when DEPLOYED_BACKEND_URL is provided', async () => {
    const backendBase = requireEnv('DEPLOYED_BACKEND_URL', BACKEND_BASE_URL);
    const response = await fetchWithTimeout(buildUrl(backendBase, '/docs'));
    expect(response.ok).toBe(true);
    expectHtmlContentType(response);
  });

  it('serves backend project listing with a valid auth posture', async () => {
    const backendBase = requireEnv('DEPLOYED_BACKEND_URL', BACKEND_BASE_URL);
    const response = await fetchWithTimeout(buildUrl(backendBase, '/api/v1/projects?limit=1'), {
      headers: createBackendHeaders(),
    });
    expect([200, 401]).toContain(response.status);

    const payload = await readJsonResponse(response);
    if (response.status === 200) {
      expect(Array.isArray(payload.data?.projects)).toBe(true);
    } else {
      expect(payload.data?.detail || payload.data?.error).toBeTruthy();
    }
  });
});

shortDhDescribe('Deployed Digital Human E2E', () => {
  it(
    'creates, submits, and completes a digital human run against the deployed backend',
    { timeout: DIGITAL_HUMAN_TIMEOUT_MS + 60_000 },
    async () => {
      const audioUrl =
        process.env.DEPLOYED_DIGITAL_HUMAN_AUDIO_URL || DEFAULT_SHORT_AUDIO_URL;

      const createResult = await createDigitalHumanProject({
        audioUrl,
        avatarUrl: process.env.DEPLOYED_DIGITAL_HUMAN_AVATAR_URL,
        theme: process.env.DEPLOYED_DIGITAL_HUMAN_THEME,
        duration: parseInteger(process.env.DEPLOYED_DIGITAL_HUMAN_DURATION, 30),
      });

      expect(createResult.response.ok).toBe(true);
      expectJsonContentType(createResult.response);
      const runId = createResult.payload.data?.run_id;
      expect(runId).toEqual(expect.any(String));

      const submitResult = await submitDigitalHumanProject(runId);
      expect(submitResult.response.ok).toBe(true);
      expectJsonContentType(submitResult.response);

      const completion = await waitForFinalVideo(runId, DIGITAL_HUMAN_TIMEOUT_MS);
      expect(completion.finalVideoUrl).toMatch(/^https?:\/\//);
    },
  );
});

longDhDescribe('Deployed Long Digital Human E2E', () => {
  it(
    'completes a long-audio digital human run and returns a final video URL',
    { timeout: DIGITAL_HUMAN_TIMEOUT_MS + 120_000 },
    async () => {
      const audioUrl = requireEnv(
        'DEPLOYED_LONG_DIGITAL_HUMAN_AUDIO_URL',
        process.env.DEPLOYED_LONG_DIGITAL_HUMAN_AUDIO_URL || '',
      );

      const createResult = await createDigitalHumanProject({
        audioUrl,
        avatarUrl: process.env.DEPLOYED_DIGITAL_HUMAN_AVATAR_URL,
        theme:
          process.env.DEPLOYED_LONG_DIGITAL_HUMAN_THEME ||
          'Long-form digital human deployment verification',
        duration: parseInteger(process.env.DEPLOYED_LONG_DIGITAL_HUMAN_DURATION, 240),
      });

      expect(createResult.response.ok).toBe(true);
      const runId = createResult.payload.data?.run_id;
      expect(runId).toEqual(expect.any(String));

      const submitResult = await submitDigitalHumanProject(runId);
      expect(submitResult.response.ok).toBe(true);

      const completion = await waitForFinalVideo(runId, DIGITAL_HUMAN_TIMEOUT_MS);
      expect(completion.finalVideoUrl).toMatch(/^https?:\/\//);
      expect(pendingTaskCount(completion.lastStatusPayload)).toBe(0);
    },
  );
});
