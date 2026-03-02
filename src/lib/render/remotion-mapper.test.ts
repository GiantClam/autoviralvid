import { describe, it, expect } from 'vitest';
import {
  toRemotionComposition,
  buildRenderJobRequest,
  summarizeRenderJob,
} from '@/lib/render/remotion-mapper';
import { ItemType, VideoProject } from '@/lib/types';

describe('remotion-mapper', () => {
  describe('toRemotionComposition', () => {
    it('should convert empty project to composition', () => {
      const project: VideoProject = {
        name: 'Test Project',
        width: 1920,
        height: 1080,
        duration: 10,
        fps: 30,
        tracks: [],
        backgroundColor: '#000000',
      };

      const composition = toRemotionComposition(project);

      expect(composition.id).toBe('composition-editor');
      expect(composition.width).toBe(1920);
      expect(composition.height).toBe(1080);
      expect(composition.fps).toBe(30);
      expect(composition.durationInFrames).toBe(300);
      expect(composition.backgroundColor).toBe('#000000');
      expect(composition.layers).toEqual([]);
      expect(composition.audioTracks).toEqual([]);
    });

    it('should convert video item to layer', () => {
      const project: VideoProject = {
        name: 'Video Test',
        width: 1920,
        height: 1080,
        duration: 5,
        fps: 30,
        tracks: [
          {
            id: 1,
            type: 'video',
            name: 'Video Track',
            items: [
              {
                id: 'video-1',
                type: ItemType.VIDEO,
                content: 'https://example.com/video.mp4',
                startTime: 0,
                duration: 5,
                trackId: 1,
                name: 'Intro Video',
              },
            ],
          },
        ],
      };

      const composition = toRemotionComposition(project);

      expect(composition.layers).toHaveLength(1);
      expect(composition.layers[0]).toMatchObject({
        id: 'video-1',
        itemType: ItemType.VIDEO,
        type: 'video',
        trackId: 1,
        name: 'Intro Video',
        source: 'https://example.com/video.mp4',
        startFrame: 0,
        durationInFrames: 150,
      });
    });

    it('should convert image item to layer', () => {
      const project: VideoProject = {
        name: 'Image Test',
        width: 1920,
        height: 1080,
        duration: 3,
        fps: 30,
        tracks: [
          {
            id: 1,
            type: 'video',
            name: 'Image Track',
            items: [
              {
                id: 'image-1',
                type: ItemType.IMAGE,
                content: 'https://example.com/image.jpg',
                startTime: 2,
                duration: 3,
                trackId: 1,
                name: 'Background',
              },
            ],
          },
        ],
      };

      const composition = toRemotionComposition(project);

      expect(composition.layers).toHaveLength(1);
      expect(composition.layers[0].type).toBe('image');
      expect(composition.layers[0].source).toBe('https://example.com/image.jpg');
      expect(composition.layers[0].startFrame).toBe(60); // 2s * 30fps
      expect(composition.layers[0].durationInFrames).toBe(90); // 3s * 30fps
    });

    it('should convert text item to layer', () => {
      const project: VideoProject = {
        name: 'Text Test',
        width: 1920,
        height: 1080,
        duration: 5,
        fps: 30,
        tracks: [
          {
            id: 2,
            type: 'overlay',
            name: 'Text Track',
            items: [
              {
                id: 'text-1',
                type: ItemType.TEXT,
                content: 'Hello World',
                startTime: 1,
                duration: 3,
                trackId: 2,
                name: 'Title',
                style: {
                  fontSize: 48,
                  color: '#ffffff',
                },
              },
            ],
          },
        ],
      };

      const composition = toRemotionComposition(project);

      expect(composition.layers).toHaveLength(1);
      expect(composition.layers[0].type).toBe('text');
      expect(composition.layers[0].text).toBe('Hello World');
      expect(composition.layers[0].startFrame).toBe(30);
      expect(composition.layers[0].durationInFrames).toBe(90);
      expect(composition.layers[0].style).toMatchObject({
        fontSize: 48,
        color: '#ffffff',
      });
    });

    it('should convert audio item to audio track', () => {
      const project: VideoProject = {
        name: 'Audio Test',
        width: 1920,
        height: 1080,
        duration: 10,
        fps: 30,
        tracks: [
          {
            id: 3,
            type: 'audio',
            name: 'Audio Track',
            items: [
              {
                id: 'audio-1',
                type: ItemType.AUDIO,
                content: 'https://example.com/bgm.mp3',
                startTime: 0,
                duration: 10,
                trackId: 3,
                name: 'Background Music',
                style: {
                  opacity: 0.5,
                },
              },
            ],
          },
        ],
      };

      const composition = toRemotionComposition(project);

      expect(composition.audioTracks).toHaveLength(1);
      expect(composition.audioTracks[0]).toMatchObject({
        id: 'audio-1',
        trackId: 3,
        name: 'Background Music',
        source: 'https://example.com/bgm.mp3',
        startFrame: 0,
        durationInFrames: 300,
        volume: 0.5,
      });
    });

    it('should handle custom fps', () => {
      const project: VideoProject = {
        name: 'FPS Test',
        width: 1920,
        height: 1080,
        duration: 10,
        fps: 60,
        tracks: [],
      };

      const composition = toRemotionComposition(project);

      expect(composition.fps).toBe(60);
      expect(composition.durationInFrames).toBe(600);
    });

    it('should default to 30fps when fps not provided', () => {
      const project: VideoProject = {
        name: 'Default FPS Test',
        width: 1920,
        height: 1080,
        duration: 10,
        tracks: [],
      };

      const composition = toRemotionComposition(project);

      expect(composition.fps).toBe(30);
    });

    it('should include runId and threadId in metadata', () => {
      const project: VideoProject = {
        name: 'Metadata Test',
        width: 1920,
        height: 1080,
        duration: 5,
        fps: 30,
        tracks: [],
        runId: 'run-123',
        threadId: 'thread-456',
      };

      const composition = toRemotionComposition(project);

      expect(composition.metadata.runId).toBe('run-123');
      expect(composition.metadata.threadId).toBe('thread-456');
    });

    it('should sort items by trackId then startTime', () => {
      const project: VideoProject = {
        name: 'Sort Test',
        width: 1920,
        height: 1080,
        duration: 10,
        fps: 30,
        tracks: [
          {
            id: 2,
            type: 'video',
            name: 'Track 2',
            items: [
              {
                id: 'item-a',
                type: ItemType.VIDEO,
                content: 'a.mp4',
                startTime: 5,
                duration: 2,
                trackId: 2,
                name: 'A',
              },
            ],
          },
          {
            id: 1,
            type: 'video',
            name: 'Track 1',
            items: [
              {
                id: 'item-b',
                type: ItemType.VIDEO,
                content: 'b.mp4',
                startTime: 0,
                duration: 2,
                trackId: 1,
                name: 'B',
              },
            ],
          },
        ],
      };

      const composition = toRemotionComposition(project);

      // Items should be sorted: track 1 first, then track 2
      expect(composition.layers).toHaveLength(2);
      expect(composition.layers[0].name).toBe('B');
      expect(composition.layers[1].name).toBe('A');
    });
  });

  describe('buildRenderJobRequest', () => {
    it('should build render job request with default engine', () => {
      const project: VideoProject = {
        name: 'Job Test',
        width: 1920,
        height: 1080,
        duration: 10,
        fps: 30,
        tracks: [],
      };

      const request = buildRenderJobRequest(project);

      expect(request.engine).toBe('remotion');
      expect(request.project.name).toBe('Job Test');
      expect(request.composition).toBeDefined();
    });

    it('should allow custom runId and threadId', () => {
      const project: VideoProject = {
        name: 'Job Test',
        width: 1920,
        height: 1080,
        duration: 10,
        tracks: [],
      };

      const request = buildRenderJobRequest(project, {
        runId: 'custom-run',
        threadId: 'custom-thread',
      });

      expect(request.project.runId).toBe('custom-run');
      expect(request.project.threadId).toBe('custom-thread');
    });

    it('should allow custom engine', () => {
      const project: VideoProject = {
        name: 'Job Test',
        width: 1920,
        height: 1080,
        duration: 10,
        tracks: [],
      };

      const request = buildRenderJobRequest(project, {
        engine: 'native',
      });

      expect(request.engine).toBe('native');
    });
  });

  describe('summarizeRenderJob', () => {
    it('should generate correct summary', () => {
      const request = {
        engine: 'remotion' as const,
        project: { name: 'Summary Test' },
        composition: {
          id: 'test',
          width: 1920,
          height: 1080,
          fps: 30,
          durationInFrames: 300,
          backgroundColor: '#000000',
          layers: [
            { id: '1', itemType: ItemType.VIDEO, type: 'video' as const, trackId: 1, name: 'Clip 1', startFrame: 0, durationInFrames: 150 },
            { id: '2', itemType: ItemType.TEXT, type: 'text' as const, trackId: 2, name: 'Text 1', text: 'Hello', startFrame: 0, durationInFrames: 150 },
          ],
          audioTracks: [
            { id: 'a1', trackId: 3, name: 'BGM', source: 'bgm.mp3', startFrame: 0, durationInFrames: 300, volume: 0.5 },
          ],
          metadata: { projectName: 'Test', generatedAt: '2024-01-01' },
        },
      };

      const summary = summarizeRenderJob(request);

      expect(summary.fps).toBe(30);
      expect(summary.durationInFrames).toBe(300);
      expect(summary.durationSeconds).toBe(10);
      expect(summary.layerCount).toBe(2);
      expect(summary.audioTrackCount).toBe(1);
    });
  });
});
