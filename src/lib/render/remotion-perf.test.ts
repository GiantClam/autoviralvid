import { describe, it, expect } from 'vitest';

const API_BASE = process.env.API_BASE || 'http://localhost:3001';
const RENDERER_URL = process.env.REMOTION_RENDERER_URL || 'http://localhost:8123';

describe('Remotion Performance Tests', () => {
  describe('1-minute video rendering performance', () => {
    it('should render a 1-minute knowledge video (color background + text only) and measure time', async () => {
      const startTime = Date.now();
      
      const response = await fetch(`${API_BASE}/api/render/jobs`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          project: {
            name: 'Performance Test 1min',
            width: 1920,
            height: 1080,
            duration: 60,
            fps: 30,
            backgroundColor: '#4ECDC4',
            tracks: [
              {
                id: 2,
                type: 'overlay',
                name: 'Text',
                items: [
                  {
                    id: 'title1',
                    type: 'text',
                    content: 'Chapter 1: Introduction',
                    startTime: 0,
                    duration: 15,
                    trackId: 2,
                    name: 'Title 1',
                    style: { fontSize: 72, color: '#ffffff' },
                  },
                  {
                    id: 'title2',
                    type: 'text',
                    content: 'Chapter 2: Main Content',
                    startTime: 15,
                    duration: 15,
                    trackId: 2,
                    name: 'Title 2',
                    style: { fontSize: 72, color: '#ffffff' },
                  },
                  {
                    id: 'title3',
                    type: 'text',
                    content: 'Chapter 3: Deep Dive',
                    startTime: 30,
                    duration: 15,
                    trackId: 2,
                    name: 'Title 3',
                    style: { fontSize: 72, color: '#ffffff' },
                  },
                  {
                    id: 'title4',
                    type: 'text',
                    content: 'Chapter 4: Conclusion',
                    startTime: 45,
                    duration: 15,
                    trackId: 2,
                    name: 'Title 4',
                    style: { fontSize: 72, color: '#ffffff' },
                  },
                ],
              },
            ],
            runId: 'perf-1min-' + Date.now(),
          },
        }),
      });

      expect(response.ok).toBe(true);
      const data = await response.json();
      
      console.log('\n========== RENDER JOB SUBMITTED ==========');
      console.log('Job ID:', data.job_id);
      console.log('Duration:', data.summary.durationSeconds, 'seconds');
      console.log('Layers:', data.summary.layerCount);
      console.log('Audio Tracks:', data.summary.audioTrackCount);
      console.log('Resolution:', data.composition?.width, 'x', data.composition?.height);
      console.log('FPS:', data.composition?.fps);
      console.log('==========================================\n');
      
      const jobId = data.job_id;
      
      // Poll for completion
      let attempts = 0;
      let jobStatus = null;
      
      while (attempts < 300) { // 5 minutes max
        const statusRes = await fetch(`${RENDERER_URL}/render/jobs/${jobId}`);
        jobStatus = await statusRes.json();
        
        const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
        console.log(`[${elapsed}s] Job status: ${jobStatus.status}`);
        
        if (jobStatus.status === 'completed' || jobStatus.status === 'failed') {
          break;
        }
        
        await new Promise(r => setTimeout(r, 1000));
        attempts++;
      }
      
      const totalTime = Date.now() - startTime;
      const totalTimeSeconds = (totalTime / 1000).toFixed(2);
      
      console.log('\n========== RENDER COMPLETE ==========');
      console.log('Total time:', totalTimeSeconds, 'seconds');
      console.log('Status:', jobStatus.status);
      console.log('Output:', jobStatus.output_path);
      console.log('====================================\n');
      
      if (jobStatus.status === 'failed') {
        console.log('Error:', jobStatus.error);
        console.log('Log:', jobStatus.log_path);
      }
      
      // Performance assertions
      expect(jobStatus.status).toBe('completed');
      expect(jobStatus.output_path).toBeDefined();
      
      // Output performance metrics
      const videoDuration = 60; // seconds
      const renderSpeed = (videoDuration / (totalTime / 1000)).toFixed(2);
      
      console.log('\n========== PERFORMANCE METRICS ==========');
      console.log(`Video duration: ${videoDuration}s`);
      console.log(`Render time: ${totalTimeSeconds}s`);
      console.log(`Real-time factor: ${renderSpeed}x (how many times faster than real-time)`);
      console.log(`Time per second of video: ${(totalTime / 1000 / videoDuration * 1000).toFixed(0)}ms`);
      console.log('=========================================\n');
    }, 300000); // 5 minute timeout
  });

  describe('30-second video rendering performance', () => {
    it('should render a 30-second video (color background + text) and measure time', async () => {
      const startTime = Date.now();
      
      const response = await fetch(`${API_BASE}/api/render/jobs`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          project: {
            name: 'Performance Test 30s',
            width: 1920,
            height: 1080,
            duration: 30,
            fps: 30,
            backgroundColor: '#1a1a2e',
            tracks: [
              {
                id: 2,
                type: 'overlay',
                name: 'Text',
                items: [
                  {
                    id: 'title1',
                    type: 'text',
                    content: 'Welcome',
                    startTime: 0,
                    duration: 10,
                    trackId: 2,
                    name: 'Title 1',
                    style: { fontSize: 80, color: '#4ECDC4' },
                  },
                  {
                    id: 'title2',
                    type: 'text',
                    content: 'Key Points',
                    startTime: 10,
                    duration: 10,
                    trackId: 2,
                    name: 'Title 2',
                    style: { fontSize: 80, color: '#ffffff' },
                  },
                  {
                    id: 'title3',
                    type: 'text',
                    content: 'Thank You',
                    startTime: 20,
                    duration: 10,
                    trackId: 2,
                    name: 'Title 3',
                    style: { fontSize: 80, color: '#4ECDC4' },
                  },
                ],
              },
            ],
            runId: 'perf-30s-' + Date.now(),
          },
        }),
      });

      expect(response.ok).toBe(true);
      const data = await response.json();
      
      console.log('\n========== RENDER JOB SUBMITTED ==========');
      console.log('Job ID:', data.job_id);
      console.log('Duration:', data.summary.durationSeconds, 'seconds');
      console.log('==========================================\n');
      
      const jobId = data.job_id;
      
      // Poll for completion
      let attempts = 0;
      let jobStatus = null;
      
      while (attempts < 180) {
        const statusRes = await fetch(`${RENDERER_URL}/render/jobs/${jobId}`);
        jobStatus = await statusRes.json();
        
        const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
        console.log(`[${elapsed}s] Job status: ${jobStatus.status}`);
        
        if (jobStatus.status === 'completed' || jobStatus.status === 'failed') {
          break;
        }
        
        await new Promise(r => setTimeout(r, 1000));
        attempts++;
      }
      
      const totalTime = Date.now() - startTime;
      const totalTimeSeconds = (totalTime / 1000).toFixed(2);
      
      console.log('\n========== RENDER COMPLETE ==========');
      console.log('Total time:', totalTimeSeconds, 'seconds');
      console.log('Status:', jobStatus.status);
      console.log('====================================\n');
      
      expect(jobStatus.status).toBe('completed');
      
      const videoDuration = 30;
      const renderSpeed = (videoDuration / (totalTime / 1000)).toFixed(2);
      
      console.log('\n========== PERFORMANCE METRICS ==========');
      console.log(`Video duration: ${videoDuration}s`);
      console.log(`Render time: ${totalTimeSeconds}s`);
      console.log(`Real-time factor: ${renderSpeed}x`);
      console.log('=========================================\n');
    }, 180000);
  });
});
