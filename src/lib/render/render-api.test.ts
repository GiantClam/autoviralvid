import { describe, it, expect, beforeAll, afterAll } from 'vitest';

const API_BASE = process.env.API_BASE || 'http://localhost:3001';

describe('Render API Integration Tests', () => {
  const testTimeout = 30000;
  
  describe('POST /api/render/jobs', () => {
    it('should accept empty project and return valid response', async () => {
      const response = await fetch(`${API_BASE}/api/render/jobs`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          project: {
            name: 'Test Empty Project',
            width: 1920,
            height: 1080,
            duration: 10,
            fps: 30,
            tracks: [],
            backgroundColor: '#000000',
          },
        }),
      });

      expect(response.ok).toBe(true);
      const data = await response.json();
      expect(data.status).toBe('accepted');
      expect(['dry_run', 'remote']).toContain(data.mode);
      expect(data.job_id).toMatch(/^(dryrun_|render_)/);
      expect(data.summary.fps).toBe(30);
      expect(data.summary.durationInFrames).toBe(300);
      expect(data.summary.layerCount).toBe(0);
    });

    it('should accept full composition payload', async () => {
      const response = await fetch(`${API_BASE}/api/render/jobs`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          engine: 'remotion',
          project: {
            name: 'Full Composition Test',
            runId: 'test-run-123',
          },
          composition: {
            id: 'composition-full',
            width: 1920,
            height: 1080,
            fps: 30,
            durationInFrames: 300,
            backgroundColor: '#000000',
            layers: [
              {
                id: 'layer1',
                itemType: 'video',
                type: 'video',
                trackId: 1,
                name: 'Intro',
                source: 'https://example.com/intro.mp4',
                startFrame: 0,
                durationInFrames: 150,
                style: {},
              },
            ],
            audioTracks: [],
            metadata: {
              projectName: 'Full Composition Test',
              generatedAt: new Date().toISOString(),
            },
          },
        }),
      });

      expect(response.ok).toBe(true);
      const data = await response.json();
      expect(data.status).toBe('accepted');
      expect(data.summary.layerCount).toBe(1);
    });

    it('should handle video with multiple layers', async () => {
      const response = await fetch(`${API_BASE}/api/render/jobs`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          project: {
            name: 'Multi Layer Test',
            width: 1920,
            height: 1080,
            duration: 20,
            fps: 30,
            tracks: [
              {
                id: 1,
                type: 'video',
                name: 'Video Track',
                items: [
                  {
                    id: 'video-1',
                    type: 'video',
                    content: 'https://sample-videos.com/video321/mp4/720/big_buck_bunny_720p_1mb.mp4',
                    startTime: 0,
                    duration: 10,
                    trackId: 1,
                    name: 'Clip 1',
                  },
                  {
                    id: 'video-2',
                    type: 'video',
                    content: 'https://sample-videos.com/video321/mp4/720/big_buck_bunny_720p_1mb.mp4',
                    startTime: 10,
                    duration: 10,
                    trackId: 1,
                    name: 'Clip 2',
                  },
                ],
              },
              {
                id: 2,
                type: 'overlay',
                name: 'Text Track',
                items: [
                  {
                    id: 'text-1',
                    type: 'text',
                    content: 'Welcome to the Test',
                    startTime: 0,
                    duration: 5,
                    trackId: 2,
                    name: 'Title',
                    style: { fontSize: 48, color: '#ffffff' },
                  },
                ],
              },
            ],
          },
        }),
      });

      expect(response.ok).toBe(true);
      const data = await response.json();
      expect(data.summary.layerCount).toBe(3);
      expect(data.summary.durationInFrames).toBe(600);
    });

    it('should handle audio tracks', async () => {
      const response = await fetch(`${API_BASE}/api/render/jobs`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          project: {
            name: 'Audio Test',
            width: 1920,
            height: 1080,
            duration: 30,
            fps: 30,
            tracks: [
              {
                id: 1,
                type: 'video',
                name: 'Video',
                items: [
                  {
                    id: 'video-1',
                    type: 'video',
                    content: 'https://example.com/video.mp4',
                    startTime: 0,
                    duration: 30,
                    trackId: 1,
                    name: 'Main Video',
                  },
                ],
              },
              {
                id: 2,
                type: 'audio',
                name: 'Audio',
                items: [
                  {
                    id: 'audio-1',
                    type: 'audio',
                    content: 'https://example.com/bgm.mp3',
                    startTime: 0,
                    duration: 30,
                    trackId: 2,
                    name: 'Background Music',
                    style: { opacity: 0.5 },
                  },
                ],
              },
            ],
          },
        }),
      });

      expect(response.ok).toBe(true);
      const data = await response.json();
      expect(data.summary.audioTrackCount).toBe(1);
    });

    it('should reject invalid payload', async () => {
      const response = await fetch(`${API_BASE}/api/render/jobs`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          invalid: 'payload',
        }),
      });

      expect(response.ok).toBe(false);
      expect(response.status).toBe(400);
      const data = await response.json();
      expect(data.error).toBeDefined();
    });

    it('should handle knowledge-edu template project', async () => {
      const response = await fetch(`${API_BASE}/api/render/jobs`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          project: {
            name: 'Knowledge Video',
            width: 1920,
            height: 1080,
            duration: 60,
            fps: 30,
            backgroundColor: '#4ECDC4',
            tracks: [
              {
                id: 1,
                type: 'video',
                name: 'Content',
                items: [
                  {
                    id: 'clip-intro',
                    type: 'video',
                    content: 'https://example.com/intro.mp4',
                    startTime: 0,
                    duration: 5,
                    trackId: 1,
                    name: 'Introduction',
                  },
                  {
                    id: 'clip-main',
                    type: 'video',
                    content: 'https://example.com/main.mp4',
                    startTime: 5,
                    duration: 50,
                    trackId: 1,
                    name: 'Main Content',
                  },
                  {
                    id: 'clip-outro',
                    type: 'video',
                    content: 'https://example.com/outro.mp4',
                    startTime: 55,
                    duration: 5,
                    trackId: 1,
                    name: 'Conclusion',
                  },
                ],
              },
              {
                id: 2,
                type: 'overlay',
                name: 'Text',
                items: [
                  {
                    id: 'title-1',
                    type: 'text',
                    content: 'Welcome to Learning',
                    startTime: 0,
                    duration: 5,
                    trackId: 2,
                    name: 'Intro Title',
                    style: { fontSize: 48, color: '#4ECDC4' },
                  },
                ],
              },
              {
                id: 3,
                type: 'audio',
                name: 'Audio',
                items: [
                  {
                    id: 'bgm',
                    type: 'audio',
                    content: 'https://example.com/background.mp3',
                    startTime: 0,
                    duration: 60,
                    trackId: 3,
                    name: 'Background Music',
                    style: { opacity: 0.3 },
                  },
                ],
              },
            ],
            runId: 'knowledge-run-001',
            threadId: 'thread-knowledge',
          },
        }),
      });

      expect(response.ok).toBe(true);
      const data = await response.json();
      expect(data.summary.fps).toBe(30);
      expect(data.summary.durationInFrames).toBe(1800);
      expect(data.summary.durationSeconds).toBe(60);
      expect(data.summary.layerCount).toBeGreaterThanOrEqual(3);
      expect(data.summary.audioTrackCount).toBe(1);
    });

    it('should handle custom fps (60fps)', async () => {
      const response = await fetch(`${API_BASE}/api/render/jobs`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          project: {
            name: '60fps Test',
            width: 1920,
            height: 1080,
            duration: 10,
            fps: 60,
            tracks: [],
          },
        }),
      });

      expect(response.ok).toBe(true);
      const data = await response.json();
      expect(data.summary.fps).toBe(60);
      expect(data.summary.durationInFrames).toBe(600);
    });

    it('should handle vertical video (9:16)', async () => {
      const response = await fetch(`${API_BASE}/api/render/jobs`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          project: {
            name: 'Vertical Video',
            width: 720,
            height: 1280,
            duration: 15,
            fps: 30,
            tracks: [],
          },
        }),
      });

      expect(response.ok).toBe(true);
      const data = await response.json();
      expect(data.summary.durationInFrames).toBe(450);
    });
  });

  describe('Agent Render Service', () => {
    it('should have render service health check', { timeout: 10000 }, async () => {
      const response = await fetch('http://localhost:8123/render/health');
      expect(response.ok).toBe(true);
      const data = await response.json();
      expect(data.service).toBe('ffmpeg-renderer');
      expect(data.ffmpeg_available).toBe(true);
    });
  });
});
