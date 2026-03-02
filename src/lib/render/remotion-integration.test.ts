import { describe, it, expect } from 'vitest';

const API_BASE = process.env.API_BASE || 'http://localhost:3001';
const RENDERER_URL = process.env.REMOTION_RENDERER_URL || 'http://localhost:8123';

describe('Remotion Integration Tests', () => {
  describe('End-to-End Render Pipeline', () => {
    it('should forward render job to remote renderer when configured', async () => {
      const response = await fetch(`${API_BASE}/api/render/jobs`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          project: {
            name: 'E2E Render Test',
            width: 1280,
            height: 720,
            duration: 5,
            fps: 30,
            tracks: [],
            runId: 'e2e-test-' + Date.now(),
          },
        }),
      });

      expect(response.ok).toBe(true);
      const data = await response.json();
      console.log('E2E Test Response:', JSON.stringify(data, null, 2));
      
      if (data.mode === 'remote') {
        expect(data.job_id).toBeDefined();
        expect(data.job_id).not.toMatch(/^dryrun_/);
        
        const statusResponse = await fetch(`${RENDERER_URL}/render/jobs/${data.job_id}`);
        if (statusResponse.ok) {
          const jobStatus = await statusResponse.json();
          console.log('Job Status:', JSON.stringify(jobStatus, null, 2));
        }
      } else {
        console.log('Running in dry-run mode. Set REMOTION_RENDERER_URL=http://localhost:8123 for full E2E testing.');
      }
    });

    it('should process complex knowledge video composition', async () => {
      const response = await fetch(`${API_BASE}/api/render/jobs`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          project: {
            name: 'Knowledge Video Production',
            width: 1920,
            height: 1080,
            duration: 120,
            fps: 30,
            backgroundColor: '#4ECDC4',
            tracks: [
              {
                id: 1,
                type: 'video',
                name: 'Main Content',
                items: [
                  {
                    id: 'intro',
                    type: 'video',
                    content: 'https://sample-videos.com/video321/mp4/720/big_buck_bunny_720p_1mb.mp4',
                    startTime: 0,
                    duration: 10,
                    trackId: 1,
                    name: 'Intro Scene',
                  },
                  {
                    id: 'section1',
                    type: 'video',
                    content: 'https://sample-videos.com/video321/mp4/720/big_buck_bunny_720p_1mb.mp4',
                    startTime: 10,
                    duration: 40,
                    trackId: 1,
                    name: 'Section 1',
                  },
                  {
                    id: 'section2',
                    type: 'video',
                    content: 'https://sample-videos.com/video321/mp4/720/big_buck_bunny_720p_1mb.mp4',
                    startTime: 50,
                    duration: 40,
                    trackId: 1,
                    name: 'Section 2',
                  },
                  {
                    id: 'outro',
                    type: 'video',
                    content: 'https://sample-videos.com/video321/mp4/720/big_buck_bunny_720p_1mb.mp4',
                    startTime: 90,
                    duration: 30,
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
                    duration: 10,
                    trackId: 2,
                    name: 'Intro Title',
                    style: { fontSize: 56, color: '#4ECDC4' },
                  },
                  {
                    id: 'title-section1',
                    type: 'text',
                    content: 'Chapter 1: Getting Started',
                    startTime: 10,
                    duration: 40,
                    trackId: 2,
                    name: 'Section 1 Title',
                    style: { fontSize: 48, color: '#ffffff' },
                  },
                  {
                    id: 'title-section2',
                    type: 'text',
                    content: 'Chapter 2: Deep Dive',
                    startTime: 50,
                    duration: 40,
                    trackId: 2,
                    name: 'Section 2 Title',
                    style: { fontSize: 48, color: '#ffffff' },
                  },
                  {
                    id: 'title-outro',
                    type: 'text',
                    content: 'Thanks for Watching!',
                    startTime: 90,
                    duration: 30,
                    trackId: 2,
                    name: 'Outro Title',
                    style: { fontSize: 56, color: '#4ECDC4' },
                  },
                ],
              },
              {
                id: 3,
                type: 'audio',
                name: 'Background Music',
                items: [
                  {
                    id: 'bgm',
                    type: 'audio',
                    content: 'https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3',
                    startTime: 0,
                    duration: 120,
                    trackId: 3,
                    name: 'Background Music',
                    style: { opacity: 0.3 },
                  },
                ],
              },
            ],
            runId: 'knowledge-e2e-' + Date.now(),
            threadId: 'thread-main',
          },
        }),
      });

      expect(response.ok).toBe(true);
      const data = await response.json();
      
      console.log('Knowledge Video Response:', JSON.stringify(data, null, 2));
      
      expect(data.status).toBe('accepted');
      expect(data.summary.fps).toBe(30);
      expect(data.summary.durationInFrames).toBe(3600);
      expect(data.summary.durationSeconds).toBe(120);
      expect(data.summary.layerCount).toBeGreaterThanOrEqual(7);
      expect(data.summary.audioTrackCount).toBe(1);
    });

    it('should handle vertical format for social media', async () => {
      const response = await fetch(`${API_BASE}/api/render/jobs`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          project: {
            name: 'Social Media Reel',
            width: 720,
            height: 1280,
            duration: 30,
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
                    duration: 15,
                    trackId: 1,
                    name: 'First Clip',
                  },
                  {
                    id: 'clip2',
                    type: 'video',
                    content: 'https://sample-videos.com/video321/mp4/720/big_buck_bunny_720p_1mb.mp4',
                    startTime: 15,
                    duration: 15,
                    trackId: 1,
                    name: 'Second Clip',
                  },
                ],
              },
              {
                id: 2,
                type: 'overlay',
                name: 'Text',
                items: [
                  {
                    id: 'text1',
                    type: 'text',
                    content: 'Did you know?',
                    startTime: 0,
                    duration: 15,
                    trackId: 2,
                    name: 'Question',
                    style: { fontSize: 40, color: '#ffffff' },
                  },
                  {
                    id: 'text2',
                    type: 'text',
                    content: 'Tap to learn more!',
                    startTime: 15,
                    duration: 15,
                    trackId: 2,
                    name: 'CTA',
                    style: { fontSize: 40, color: '#4ECDC4' },
                  },
                ],
              },
            ],
            runId: 'social-' + Date.now(),
          },
        }),
      });

      expect(response.ok).toBe(true);
      const data = await response.json();
      
      console.log('Social Media Response:', JSON.stringify(data, null, 2));
      
      expect(data.summary.fps).toBe(30);
      expect(data.summary.durationInFrames).toBe(900);
      expect(data.summary.durationSeconds).toBe(30);
    });
  });

  describe('Template Compositions', () => {
    it('should support knowledge-edu template metadata', async () => {
      const response = await fetch(`${API_BASE}/api/render/jobs`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          project: {
            name: 'KnowledgeEdu Template',
            width: 1920,
            height: 1080,
            duration: 60,
            fps: 30,
            backgroundColor: '#4ECDC4',
            tracks: [],
            runId: 'template-knowledge-edu',
          },
          composition: {
            id: 'composition-knowledge-edu',
            width: 1920,
            height: 1080,
            fps: 30,
            durationInFrames: 1800,
            backgroundColor: '#4ECDC4',
            layers: [
              {
                id: 'layer1',
                itemType: 'video',
                type: 'video',
                trackId: 1,
                name: 'Content',
                source: 'https://example.com/content.mp4',
                startFrame: 0,
                durationInFrames: 1800,
                style: { primaryColor: '#4ECDC4' },
              },
            ],
            audioTracks: [],
            metadata: {
              projectName: 'KnowledgeEdu Template',
              runId: 'template-knowledge-edu',
              generatedAt: new Date().toISOString(),
            },
          },
        }),
      });

      expect(response.ok).toBe(true);
      const data = await response.json();
      
      expect(data.summary.fps).toBe(30);
      expect(data.summary.durationInFrames).toBe(1800);
      expect(data.summary.layerCount).toBe(1);
    });
  });
});
