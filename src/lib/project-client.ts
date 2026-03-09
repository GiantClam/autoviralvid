/**
 * REST API client for the form-driven video generation workflow.
 * Talks to the FastAPI backend at /api/v1/...
 *
 * Authentication: automatically fetches a short-lived JWT from
 * /api/auth/api-token and attaches it as a Bearer token.
 */

function getApiBase() {
  const configured =
    process.env.NEXT_PUBLIC_API_BASE ||
    process.env.NEXT_PUBLIC_AGENT_URL;

  if (configured) {
    return configured.replace(/\/+$/, '');
  }

  if (process.env.NODE_ENV === 'production') {
    throw new Error('Missing NEXT_PUBLIC_API_BASE or NEXT_PUBLIC_AGENT_URL for production deployment.');
  }

  return 'http://localhost:8123';
}

// ---------------------------------------------------------------------------
// Token management — cache the JWT and refresh before it expires
// ---------------------------------------------------------------------------
let _cachedToken: string | null = null;
let _tokenExpiresAt = 0; // ms since epoch

async function getApiToken(): Promise<string | null> {
  // Return cached token if still fresh (with 60s buffer)
  if (_cachedToken && Date.now() < _tokenExpiresAt - 60_000) {
    return _cachedToken;
  }

  try {
    const res = await fetch('/api/auth/api-token', { method: 'POST' });
    if (!res.ok) {
      // Not logged in or auth disabled — clear cache and proceed without token
      _cachedToken = null;
      _tokenExpiresAt = 0;
      return null;
    }
    const data = await res.json();
    _cachedToken = data.token ?? null;
    _tokenExpiresAt = Date.now() + (data.expires_in ?? 3600) * 1000;
    return _cachedToken;
  } catch {
    // Network error / auth not available — proceed without token
    _cachedToken = null;
    _tokenExpiresAt = 0;
    return null;
  }
}

/** Call this on logout to clear cached credentials */
export function clearApiToken() {
  _cachedToken = null;
  _tokenExpiresAt = 0;
}

// ---------------------------------------------------------------------------
// Core fetch wrapper
// ---------------------------------------------------------------------------
async function apiFetch<T = unknown>(path: string, init?: RequestInit): Promise<T> {
  const url = `${getApiBase()}/api/v1${path}`;

  // Build auth header
  const token = await getApiToken();
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(init?.headers as Record<string, string> || {}),
  };
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const res = await fetch(url, { ...init, headers });

  // If we get a 401 the token may have been invalidated — clear cache and
  // retry once with a fresh token.
  if (res.status === 401 && token) {
    _cachedToken = null;
    _tokenExpiresAt = 0;
    const freshToken = await getApiToken();
    if (freshToken) {
      headers['Authorization'] = `Bearer ${freshToken}`;
      const retryRes = await fetch(url, { ...init, headers });
      if (!retryRes.ok) {
        const body = await retryRes.text().catch(() => '');
        throw new Error(`API ${retryRes.status}: ${body}`);
      }
      return retryRes.json();
    }
  }

  if (!res.ok) {
    const body = await res.text().catch(() => '');
    throw new Error(`API ${res.status}: ${body}`);
  }
  return res.json();
}

// ── Types ──

export interface ProjectParams {
  template_id: string;
  theme: string;
  product_image_url?: string;
  style?: string;
  duration?: number;
  orientation?: string;
  video_type?: string;
  aspect_ratio?: string;
  // Digital human params
  audio_url?: string;
  voice_mode?: number;       // 0=直接用音频, 1=克隆声音+文本合成
  voice_text?: string;       // 克隆声音后合成语音的文本
  motion_prompt?: string;    // 数字人动作描述
}

export interface Project {
  run_id: string;
  template_id: string;
  theme: string;
  status: string;
  storyboards?: StoryboardData | null;
  created_at?: string;
  [key: string]: unknown;
}

export interface StoryboardScene {
  idx: number;
  desc: string;
  narration?: string;
  prompt?: string;
  image_url?: string;
}

export interface StoryboardData {
  scenes: StoryboardScene[];
}

export interface VideoTask {
  id?: string;
  run_id: string;
  clip_idx: number;
  status: 'pending' | 'processing' | 'submitted' | 'succeeded' | 'failed';
  video_url?: string;
  prompt?: string;
  duration?: number;
  error?: string;
}

export interface ProjectStatus {
  run_id: string;
  status: string;
  tasks: VideoTask[];
  summary: {
    total: number;
    succeeded: number;
    pending: number;
    failed: number;
    all_done: boolean;
  };
}

// ── API methods ──

export const projectApi = {
  /** Create a new project */
  create: (params: ProjectParams) =>
    apiFetch<Project>('/projects', {
      method: 'POST',
      body: JSON.stringify(params),
    }),

  /** List projects */
  list: (limit = 40) =>
    apiFetch<Project[]>(`/projects?limit=${limit}`),

  /** Get project details */
  get: (runId: string) =>
    apiFetch<Project>(`/projects/${runId}`),

  /** Generate storyboard (background) */
  generateStoryboard: (runId: string) =>
    apiFetch<{ status: string }>(`/projects/${runId}/storyboard`, {
      method: 'POST',
    }),

  /** Update a single scene */
  updateScene: (runId: string, sceneIdx: number, data: { description?: string; narration?: string }) =>
    apiFetch<{ status: string }>(`/projects/${runId}/storyboard/scenes/${sceneIdx}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  /** Generate storyboard images (background) */
  generateImages: (runId: string) =>
    apiFetch<{ status: string }>(`/projects/${runId}/images`, {
      method: 'POST',
    }),

  /** Regenerate one image */
  regenerateImage: (runId: string, sceneIdx: number, newPrompt?: string) =>
    apiFetch<{ status: string }>(`/projects/${runId}/images/${sceneIdx}/regenerate`, {
      method: 'POST',
      body: JSON.stringify({ new_prompt: newPrompt }),
    }),

  /** Submit video generation (background) */
  submitVideos: (runId: string) =>
    apiFetch<{ status: string }>(`/projects/${runId}/videos`, {
      method: 'POST',
    }),

  /** Submit digital human video generation (background) */
  submitDigitalHuman: (runId: string) =>
    apiFetch<{ status: string }>(`/projects/${runId}/digital-human`, {
      method: 'POST',
    }),

  /** Regenerate one video clip */
  regenerateVideo: (runId: string, clipIdx: number, newPrompt?: string) =>
    apiFetch<{ status: string }>(`/projects/${runId}/videos/${clipIdx}/regenerate`, {
      method: 'POST',
      body: JSON.stringify({ new_prompt: newPrompt }),
    }),

  /** Get project status with all tasks */
  getStatus: (runId: string) =>
    apiFetch<ProjectStatus>(`/projects/${runId}/status`),

  /** Trigger final render */
  render: (runId: string) =>
    apiFetch<{ status: string; video_url?: string }>(`/projects/${runId}/render`, {
      method: 'POST',
    }),

  /** Create batch projects */
  createBatch: (params: {
    template_id: string;
    product_images: string[];
    theme: string;
    style?: string;
    duration?: number;
    orientation?: string;
    aspect_ratio?: string;
  }) =>
    apiFetch<{ run_ids: string[] }>('/projects/batch', {
      method: 'POST',
      body: JSON.stringify(params),
    }),

  /** AI assistant chat */
  aiChat: (message: string, projectContext?: Record<string, unknown>) =>
    apiFetch<{ reply: string }>('/ai/chat', {
      method: 'POST',
      body: JSON.stringify({ message, project_context: projectContext }),
    }),
};
