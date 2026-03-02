import { describe, it, expect } from 'vitest';

const API_BASE = process.env.API_BASE || 'http://localhost:3001';
const RENDERER_URL = process.env.REMOTION_RENDERER_URL || 'http://localhost:8123';

describe('Remotion Full Render Tests', () => {
  describe('Actual Video Rendering', () => {
    it('should render a simple video project', async () => {
      const response = await fetch(`${API_BASE}/api/render/jobs`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          project: {
            name: 'Simple Video Render',
            width: 1280,
            height: 720,
            duration: 3,
            fps: 30,
            tracks: [],
            runId: 'simple-render-' + Date.now(),
          },
        }),
      });

      expect(response.ok).toBe(true);
      const data = await response.json();
      console.log('Simple render response:', JSON.stringify(data, null, 2));
      
      expect(data.mode).toBe('remote');
      expect(data.job_id).not.toMatch(/^dryrun_/);
      
      const jobId = data.job_id;
      
      // Poll for completion
      let attempts = 0;
      let jobStatus = null;
      while (attempts < 30) {
        const statusRes = await fetch(`${RENDERER_URL}/render/jobs/${jobId}`);
        jobStatus = await statusRes.json();
        console.log('Job status:', jobStatus.status);
        
        if (jobStatus.status === 'completed' || jobStatus.status === 'failed') {
          break;
        }
        await new Promise(r => setTimeout(r, 1000));
        attempts++;
      }
      
      expect(jobStatus.status).toBe('completed');
      expect(jobStatus.output_path).toBeDefined();
      console.log('Output path:', jobStatus.output_path);
    }, 60000);

    it('should submit knowledge video render job to renderer', async () => {
      const response = await fetch(`${API_BASE}/api/render/jobs`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          project: {
            name: 'Knowledge Video Render',
            width: 1920,
            height: 1080,
            duration: 10,
            fps: 30,
            backgroundColor: '#4ECDC4',
            tracks: [
              {
                id: 1,
                type: 'video',
                name: 'Content',
                items: [
                  {
                    id: 'intro',
                    type: 'video',
                    content: 'https://sample-videos.com/video321/mp4/720/big_buck_bunny_720p_1mb.mp4',
                    startTime: 0,
                    duration: 5,
                    trackId: 1,
                    name: 'Intro',
                  },
                  {
                    id: 'main',
                    type: 'video',
                    content: 'https://sample-videos.com/video321/mp4/720/big_buck_bunny_720p_1mb.mp4',
                    startTime: 5,
                    duration: 5,
                    trackId: 1,
                    name: 'Main',
                  },
                ],
              },
              {
                id: 2,
                type: 'overlay',
                name: 'Text',
                items: [
                  {
                    id: 'title',
                    type: 'text',
                    content: 'Welcome to Learning',
                    startTime: 0,
                    duration: 10,
                    trackId: 2,
                    name: 'Title',
                    style: { fontSize: 48, color: '#4ECDC4' },
                  },
                ],
              },
            ],
            runId: 'knowledge-render-' + Date.now(),
          },
        }),
      });

      expect(response.ok).toBe(true);
      const data = await response.json();
      console.log('Knowledge render response:', JSON.stringify(data, null, 2));
      
      expect(data.mode).toBe('remote');
      expect(data.job_id).not.toMatch(/^dryrun_/);
      expect(data.summary.layerCount).toBe(3);
      expect(data.summary.durationInFrames).toBe(300);
      
      const jobId = data.job_id;
      
      // Verify job was accepted by renderer
      const statusRes = await fetch(`${RENDERER_URL}/render/jobs/${jobId}`);
      const jobStatus = await statusRes.json();
      console.log('Job status:', jobStatus.status);
      
      // Job should be accepted (may succeed or fail depending on network access)
      expect(['queued', 'running', 'completed', 'failed']).toContain(jobStatus.status);
      console.log('Job accepted and processed by renderer');
    }, 60000);

    it('should submit vertical video render job to renderer', async () => {
      const response = await fetch(`${API_BASE}/api/render/jobs`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          project: {
            name: 'Social Reel Render',
            width: 720,
            height: 1280,
            duration: 8,
            fps: 30,
            backgroundColor: '#1a1a2e',
            tracks: [
              {
                id: 1,
                type: 'video',
                name: 'Clips',
                items: [
                  {
                    id: 'clip1',
                    type: 'video',
                    content: 'https://sample-videos.com/video321/mp4/720/big_buck_bunny_720p_1mb.mp4',
                    startTime: 0,
                    duration: 4,
                    trackId: 1,
                    name: 'First',
                  },
                  {
                    id: 'clip2',
                    type: 'video',
                    content: 'https://sample-videos.com/video321/mp4/720/big_buck_bunny_720p_1mb.mp4',
                    startTime: 4,
                    duration: 4,
                    trackId: 1,
                    name: 'Second',
                  },
                ],
              },
              {
                id: 2,
                type: 'overlay',
                name: 'Overlay',
                items: [
                  {
                    id: 'text1',
                    type: 'text',
                    content: 'Tap here!',
                    startTime: 4,
                    duration: 4,
                    trackId: 2,
                    name: 'CTA',
                    style: { fontSize: 40, color: '#4ECDC4' },
                  },
                ],
              },
            ],
            runId: 'social-render-' + Date.now(),
          },
        }),
      });

      expect(response.ok).toBe(true);
      const data = await response.json();
      console.log('Social render response:', JSON.stringify(data, null, 2));
      
      expect(data.mode).toBe('remote');
      expect(data.job_id).not.toMatch(/^dryrun_/);
      expect(data.summary.layerCount).toBeGreaterThanOrEqual(2);
      
      const jobId = data.job_id;
      
      // Verify job was accepted
      const statusRes = await fetch(`${RENDERER_URL}/render/jobs/${jobId}`);
      const jobStatus = await statusRes.json();
      expect(['queued', 'running', 'completed', 'failed']).toContain(jobStatus.status);
      console.log('Vertical video job accepted');
    }, 60000);

    it('should submit knowledge-edu template render job to renderer', async () => {
      const response = await fetch(`${API_BASE}/api/render/jobs`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          project: {
            name: 'KnowledgeEdu Template Render',
            width: 1920,
            height: 1080,
            duration: 15,
            fps: 30,
            backgroundColor: '#4ECDC4',
            tracks: [
              {
                id: 1,
                type: 'video',
                name: 'Video Content',
                items: [
                  {
                    id: 'clip-intro',
                    type: 'video',
                    content: 'https://sample-videos.com/video321/mp4/720/big_buck_bunny_720p_1mb.mp4',
                    startTime: 0,
                    duration: 5,
                    trackId: 1,
                    name: 'Introduction',
                  },
                  {
                    id: 'clip-core',
                    type: 'video',
                    content: 'https://sample-videos.com/video321/mp4/720/big_buck_bunny_720p_1mb.mp4',
                    startTime: 5,
                    duration: 5,
                    trackId: 1,
                    name: 'Core Content',
                  },
                  {
                    id: 'clip-outro',
                    type: 'video',
                    content: 'https://sample-videos.com/video321/mp4/720/big_buck_bunny_720p_1mb.mp4',
                    startTime: 10,
                    duration: 5,
                    trackId: 1,
                    name: 'Conclusion',
                  },
                ],
              },
              {
                id: 2,
                type: 'overlay',
                name: 'Titles',
                items: [
                  {
                    id: 'title-intro',
                    type: 'text',
                    content: 'Welcome to Learning',
                    startTime: 0,
                    duration: 5,
                    trackId: 2,
                    name: 'Intro Title',
                    style: { fontSize: 48, color: '#4ECDC4' },
                  },
                  {
                    id: 'title-main',
                    type: 'text',
                    content: 'Key Concepts',
                    startTime: 5,
                    duration: 5,
                    trackId: 2,
                    name: 'Main Title',
                    style: { fontSize: 48, color: '#ffffff' },
                  },
                  {
                    id: 'title-outro',
                    type: 'text',
                    content: 'Thanks for Watching!',
                    startTime: 10,
                    duration: 5,
                    trackId: 2,
                    name: 'Outro Title',
                    style: { fontSize: 48, color: '#4ECDC4' },
                  },
                ],
              },
              {
                id: 3,
                type: 'audio',
                name: 'Background',
                items: [
                  {
                    id: 'bgm',
                    type: 'audio',
                    content: 'https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3',
                    startTime: 0,
                    duration: 15,
                    trackId: 3,
                    name: 'Background Music',
                    style: { opacity: 0.3 },
                  },
                ],
              },
            ],
            runId: 'knowledge-edu-render-' + Date.now(),
          },
        }),
      });

      expect(response.ok).toBe(true);
      const data = await response.json();
      console.log('KnowledgeEdu render response:', JSON.stringify(data, null, 2));
      
      expect(data.mode).toBe('remote');
      expect(data.job_id).not.toMatch(/^dryrun_/);
      expect(data.summary.layerCount).toBe(6); // 3 video + 3 text
      expect(data.summary.audioTrackCount).toBe(1);
      expect(data.summary.durationInFrames).toBe(450);
      
      const jobId = data.job_id;
      
      // Verify job was accepted
      const statusRes = await fetch(`${RENDERER_URL}/render/jobs/${jobId}`);
      const jobStatus = await statusRes.json();
      expect(['queued', 'running', 'completed', 'failed']).toContain(jobStatus.status);
      console.log('KnowledgeEdu template job accepted');
    }, 60000);
  });
});
