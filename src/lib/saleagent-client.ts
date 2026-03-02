export type ClipKeyframes = { in?: string; out?: string }
export type ClipSpec = {
    idx: number;
    desc: string;
    begin_s: number;
    end_s: number;
    keyframes?: ClipKeyframes;
    scene_idx?: number;
    narration?: string;
    script?: string;
    prompt?: string;
    text?: string;
    video_url?: string;
}
export type EventItem = { thread_id?: string; run_id?: string; agent?: string; type: string; delta?: string | null; payload?: any; progress?: { current: number; total: number }; ts?: number; code?: string; content?: string }
export type RunClipResult = { idx: number; status: 'succeeded' | 'failed'; video_url?: string; detail?: any }
export type JobInfo = { run_id: string; slogan?: string; cover_url?: string; video_url?: string; share_slug?: string; status?: string; created_at?: string; updated_at?: string }
export type CrewStatus = {
    run_id: string;
    status: string;
    result?: string;
    error?: string;
    expected_clips?: number;
    video_tasks?: any[];
    context?: any;
    created_at?: string;
    updated_at?: string;
}

export interface PlanResponse {
    storyboards: ClipSpec[];
}

export function uuidv4() {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
        var r = Math.random() * 16 | 0, v = c == 'x' ? r : (r & 0x3 | 0x8);
        return v.toString(16);
    });
}

const DEFAULT_BASE = typeof process !== 'undefined' && (process.env.NEXT_PUBLIC_AGENT_URL || process.env.AGENT_URL) ? (process.env.NEXT_PUBLIC_AGENT_URL || process.env.AGENT_URL)! : 'http://localhost:8123'

export function getBaseUrl(base?: string) { return base !== undefined ? base : DEFAULT_BASE }

export async function postJson<T>(url: string, body: any, init?: RequestInit): Promise<T> {
    const res = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body), ...(init || {}) })
    if (!res.ok) { try { const err = await res.json(); throw new Error(err?.error || err?.detail || `HTTP ${res.status}`) } catch { throw new Error(`HTTP ${res.status}`) } }
    const data = await res.json()
    if (data && typeof data === 'object' && 'error' in data) {
        throw new Error(data.error as string)
    }
    return data as T
}

export async function getAgentSession(run_id: string) {
    const url = `/api/agent/session/${encodeURIComponent(run_id)}`
    const res = await fetch(url)
    if (!res.ok) {
        throw new Error(`HTTP ${res.status}`)
    }
    return res.json() as Promise<CrewStatus>
}

export async function listWorkflows(limit: number = 20) {
    const url = `/api/agent/sessions?limit=${limit}`
    const res = await fetch(url)
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    return res.json() as Promise<{ workflows: any[] }>
}

export async function uploadFile(file: File, base?: string): Promise<string> {
    const url = `/api/upload/presign`
    const data = await postJson<{ upload_url?: string; public_url?: string; headers?: Record<string, string>; error?: string }>(url, {
        filename: file.name,
        content_type: file.type || "application/octet-stream"
    })

    if (!data.upload_url || !data.public_url) {
        throw new Error(data.error || 'Failed to get upload URL')
    }

    // Use headers from response (includes signed Content-Type)
    const res = await fetch(data.upload_url, {
        method: 'PUT',
        body: file,
        headers: data.headers
    })

    if (!res.ok) {
        throw new Error(`Upload failed: ${res.statusText}`)
    }

    return data.public_url
}

export async function retryJob(run_id: string): Promise<{ status: string; run_id: string; message: string }> {
    const url = `/api/agent/retry/${encodeURIComponent(run_id)}`
    const res = await fetch(url, { method: 'POST' })
    if (!res.ok) {
        throw new Error(`HTTP ${res.status}`)
    }
    return res.json()
}

// --- Video task management ---

export type VideoTask = {
    id: string;
    run_id: string;
    clip_idx: number;
    prompt: string;
    ref_img?: string;
    duration: number;
    status: 'pending' | 'processing' | 'submitted' | 'succeeded' | 'failed';
    video_url?: string;
    error?: string;
    provider_task_id?: string;
    skill_name?: string;
    retry_count: number;
    created_at: string;
    updated_at: string;
}

export type TasksResponse = {
    run_id: string;
    tasks: VideoTask[];
    summary: {
        total: number;
        succeeded: number;
        pending: number;
        failed: number;
        all_done: boolean;
    };
}

export async function getTasksForRun(run_id: string): Promise<TasksResponse> {
    const url = `/api/agent/tasks/${encodeURIComponent(run_id)}`
    const res = await fetch(url)
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    return res.json()
}

export async function regenerateClip(
    run_id: string,
    clip_idx: number,
    new_prompt?: string
): Promise<{ status: string; run_id: string; clip_idx: number; message: string }> {
    const url = `/api/agent/regenerate/${encodeURIComponent(run_id)}`
    const res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ clip_idx, ...(new_prompt ? { new_prompt } : {}) }),
    })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    return res.json()
}

export async function stitchRun(
    run_id: string
): Promise<{ status: string; run_id: string; message: string }> {
    const url = `/api/agent/stitch/${encodeURIComponent(run_id)}`
    const res = await fetch(url, { method: 'POST' })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    return res.json()
}

