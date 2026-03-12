"use client";

import React, { createContext, useContext, useState, useCallback, useRef, useEffect } from 'react';
import {
  projectApi,
  Project,
  ProjectTaskSummary,
  StoryboardData,
  StoryboardScene,
  VideoTask,
  ProjectStatus,
} from '@/lib/project-client';

// ── Types ──

export type ProjectPhase =
  | 'idle'           // No project yet
  | 'configuring'    // Form filling
  | 'generating_storyboard'
  | 'storyboard_ready'
  | 'generating_images'
  | 'images_ready'
  | 'generating_videos'
  | 'stitching'      // All segments done, stitching into final video
  | 'videos_ready'   // All clips done
  | 'rendering'
  | 'completed'      // Final video ready
  | 'error';

interface ProjectContextType {
  // Current project
  project: Project | null;
  phase: ProjectPhase;
  error: string | null;

  // Storyboard
  storyboard: StoryboardData | null;
  scenes: StoryboardScene[];

  // Video tasks
  tasks: VideoTask[];
  taskSummary: { total: number; succeeded: number; pending: number; failed: number; allDone: boolean };

  // Final output
  finalVideoUrl: string | null;

  // Actions
  createProject: (params: {
    template_id: string;
    theme: string;
    product_image_url?: string;
    style?: string;
    duration?: number;
    orientation?: string;
    aspect_ratio?: string;
    audio_url?: string;
    voice_mode?: number;
    voice_text?: string;
    motion_prompt?: string;
  }) => Promise<void>;
  generateStoryboard: () => Promise<void>;
  updateScene: (idx: number, data: { description?: string; narration?: string }) => Promise<void>;
  generateImages: () => Promise<void>;
  regenerateImage: (idx: number, prompt?: string) => Promise<void>;
  submitVideos: () => Promise<void>;
  submitDigitalHuman: () => Promise<void>;
  regenerateVideo: (clipIdx: number, prompt?: string) => Promise<void>;
  renderFinal: () => Promise<void>;
  loadProject: (runId: string) => Promise<void>;
  resetProject: () => void;

  // Loading states
  isLoading: boolean;
}

const ProjectContext = createContext<ProjectContextType | undefined>(undefined);

export const ProjectProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [project, setProject] = useState<Project | null>(null);
  const [phase, setPhase] = useState<ProjectPhase>('idle');
  const [error, setError] = useState<string | null>(null);
  const [storyboard, setStoryboard] = useState<StoryboardData | null>(null);
  const [tasks, setTasks] = useState<VideoTask[]>([]);
  const [taskSummary, setTaskSummary] = useState({ total: 0, succeeded: 0, pending: 0, failed: 0, allDone: false });
  const [finalVideoUrl, setFinalVideoUrl] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const runIdRef = useRef<string | null>(null);

  const scenes = storyboard?.scenes || [];

  const toTaskSummaryState = useCallback((summary?: Partial<ProjectTaskSummary> | null) => ({
    total: summary?.total ?? 0,
    succeeded: summary?.succeeded ?? 0,
    pending:
      (summary?.pending ?? 0) +
      (summary?.queued ?? 0) +
      (summary?.processing ?? 0) +
      (summary?.submitted ?? 0),
    failed: summary?.failed ?? 0,
    allDone: summary?.all_done ?? false,
  }), []);

  // Cleanup polling on unmount
  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  const startPolling = useCallback((runId: string) => {
    stopPolling();
    runIdRef.current = runId;

    pollRef.current = setInterval(async () => {
      if (runIdRef.current !== runId) {
        stopPolling();
        return;
      }
      try {
        const status: ProjectStatus = await projectApi.getStatus(runId);
        setTasks(status.tasks);
        setTaskSummary(toTaskSummaryState(status.summary));

        // Also refresh project to get latest storyboard
        try {
          const proj = await projectApi.get(runId);
          setProject(proj);
          if (proj.storyboards && typeof proj.storyboards === 'object') {
            setStoryboard(proj.storyboards as StoryboardData);
          }
          // Auto-advance phase based on project status
          const s = proj.status || '';
          const videoUrl =
            (proj as Record<string, unknown>).video_url as string | undefined ||
            (proj.final_video_url as string | undefined) ||
            (proj.result_video_url as string | undefined);
          if (s === 'storyboard_ready' && phase === 'generating_storyboard') {
            setPhase('storyboard_ready');
          } else if (s === 'images_ready' && phase === 'generating_images') {
            setPhase('images_ready');
          } else if (status.summary.all_done && (phase === 'generating_videos' || phase === 'stitching')) {
            // All tasks done — check if final video is ready or still stitching
            if (videoUrl || (proj.final_video_url as string)) {
              // Final video is ready (digital human auto-stitch completed)
              setFinalVideoUrl(videoUrl || null);
              setPhase('completed');
              stopPolling();
            } else if (status.summary.total > 1) {
              // Multi-segment: all segments done but no final video yet → stitching
              setPhase('stitching');
              // Keep polling to detect when stitch completes
            } else {
              // Single task: all done
              setPhase('videos_ready');
              stopPolling();
            }
          } else if (s === 'completed') {
            setFinalVideoUrl(videoUrl || null);
            setPhase('completed');
            stopPolling();
          }
        } catch { /* ignore */ }
      } catch {
        // silently retry
      }
    }, 4000);
  }, [stopPolling, phase, toTaskSummaryState]);

  const createProject = useCallback(async (params: {
    template_id: string;
    theme: string;
    product_image_url?: string;
    style?: string;
    duration?: number;
    orientation?: string;
    aspect_ratio?: string;
    // Digital human params
    audio_url?: string;
    voice_mode?: number;
    voice_text?: string;
    motion_prompt?: string;
  }) => {
    setIsLoading(true);
    setError(null);
    try {
      const proj = await projectApi.create(params);
      setProject(proj);
      runIdRef.current = proj.run_id;
      setPhase('configuring');
      setStoryboard(null);
      setTasks([]);
      setFinalVideoUrl(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to create project');
      setPhase('error');
    } finally {
      setIsLoading(false);
    }
  }, []);

  const generateStoryboard = useCallback(async () => {
    if (!project?.run_id) return;
    setIsLoading(true);
    setError(null);
    setPhase('generating_storyboard');
    try {
      await projectApi.generateStoryboard(project.run_id);
      startPolling(project.run_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to generate storyboard');
      setPhase('error');
    } finally {
      setIsLoading(false);
    }
  }, [project, startPolling]);

  const updateScene = useCallback(async (idx: number, data: { description?: string; narration?: string }) => {
    if (!project?.run_id) return;
    try {
      await projectApi.updateScene(project.run_id, idx, data);
      // Refresh project
      const proj = await projectApi.get(project.run_id);
      setProject(proj);
      if (proj.storyboards) setStoryboard(proj.storyboards as StoryboardData);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to update scene');
    }
  }, [project]);

  const generateImages = useCallback(async () => {
    if (!project?.run_id) return;
    setIsLoading(true);
    setError(null);
    setPhase('generating_images');
    try {
      await projectApi.generateImages(project.run_id);
      startPolling(project.run_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to generate images');
      setPhase('error');
    } finally {
      setIsLoading(false);
    }
  }, [project, startPolling]);

  const regenerateImage = useCallback(async (idx: number, prompt?: string) => {
    if (!project?.run_id) return;
    try {
      await projectApi.regenerateImage(project.run_id, idx, prompt);
      startPolling(project.run_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to regenerate image');
    }
  }, [project, startPolling]);

  const submitVideos = useCallback(async () => {
    if (!project?.run_id) return;
    setIsLoading(true);
    setError(null);
    setPhase('generating_videos');
    try {
      await projectApi.submitVideos(project.run_id);
      startPolling(project.run_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to submit videos');
      setPhase('error');
    } finally {
      setIsLoading(false);
    }
  }, [project, startPolling]);

  const submitDigitalHuman = useCallback(async () => {
    // Use runIdRef to avoid stale closure — when called immediately after
    // createProject(), the React state `project` hasn't re-rendered yet,
    // but runIdRef.current is already set synchronously.
    const runId = project?.run_id || runIdRef.current;
    if (!runId) return;
    setIsLoading(true);
    setError(null);
    setPhase('generating_videos');
    try {
      await projectApi.submitDigitalHuman(runId);
      startPolling(runId);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to submit digital human');
      setPhase('error');
    } finally {
      setIsLoading(false);
    }
  }, [project, startPolling]);

  const regenerateVideo = useCallback(async (clipIdx: number, prompt?: string) => {
    if (!project?.run_id) return;
    try {
      await projectApi.regenerateVideo(project.run_id, clipIdx, prompt);
      startPolling(project.run_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to regenerate video');
    }
  }, [project, startPolling]);

  const renderFinal = useCallback(async () => {
    if (!project?.run_id) return;
    setIsLoading(true);
    setError(null);
    setPhase('rendering');
    try {
      const result = await projectApi.render(project.run_id);
      if (result.video_url) {
        setFinalVideoUrl(result.video_url);
        setPhase('completed');
      } else {
        startPolling(project.run_id);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to render');
      setPhase('error');
    } finally {
      setIsLoading(false);
    }
  }, [project, startPolling]);

  const loadProject = useCallback(async (runId: string) => {
    setIsLoading(true);
    setError(null);
    stopPolling();
    try {
      const proj = await projectApi.get(runId);
      setProject(proj);
      runIdRef.current = runId;

      if (proj.storyboards) {
        setStoryboard(proj.storyboards as StoryboardData);
      }

      if (proj.video_tasks?.length) {
        setTasks(proj.video_tasks);
      }

      if (proj.task_summary) {
        setTaskSummary(toTaskSummaryState(proj.task_summary));
      }

      // Load tasks
      try {
        const status = await projectApi.getStatus(runId);
        setTasks(status.tasks);
        setTaskSummary(toTaskSummaryState(status.summary));

        // Determine phase
        const resultVideoUrl =
          (proj.video_url as string | undefined) ||
          (proj.final_video_url as string | undefined) ||
          (proj.result_video_url as string | undefined) ||
          (status.video_url ?? undefined);

        if (resultVideoUrl) {
          setFinalVideoUrl(resultVideoUrl);
          setPhase('completed');
        } else if (status.summary.all_done && status.summary.total > 0) {
          setPhase('videos_ready');
        } else if (status.summary.total > 0) {
          setPhase('generating_videos');
          startPolling(runId);
        } else if (proj.storyboards) {
          // Check if images exist
          const sb = proj.storyboards as StoryboardData;
          const hasImages = sb.scenes?.some(s => s.image_url);
          setPhase(hasImages ? 'images_ready' : 'storyboard_ready');
        } else {
          setPhase('configuring');
        }
      } catch {
        const resultVideoUrl =
          (proj.video_url as string | undefined) ||
          (proj.final_video_url as string | undefined) ||
          (proj.result_video_url as string | undefined);
        if (resultVideoUrl) {
          setFinalVideoUrl(resultVideoUrl);
          setPhase('completed');
        } else {
          setPhase(proj.storyboards ? 'storyboard_ready' : 'configuring');
        }
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load project');
      setPhase('error');
    } finally {
      setIsLoading(false);
    }
  }, [startPolling, stopPolling, toTaskSummaryState]);

  const resetProject = useCallback(() => {
    stopPolling();
    setProject(null);
    setPhase('idle');
    setError(null);
    setStoryboard(null);
    setTasks([]);
    setTaskSummary({ total: 0, succeeded: 0, pending: 0, failed: 0, allDone: false });
    setFinalVideoUrl(null);
    runIdRef.current = null;
  }, [stopPolling]);

  return (
    <ProjectContext.Provider value={{
      project,
      phase,
      error,
      storyboard,
      scenes,
      tasks,
      taskSummary,
      finalVideoUrl,
      createProject,
      generateStoryboard,
      updateScene,
      generateImages,
      regenerateImage,
      submitVideos,
      submitDigitalHuman,
      regenerateVideo,
      renderFinal,
      loadProject,
      resetProject,
      isLoading,
    }}>
      {children}
    </ProjectContext.Provider>
  );
};

export const useProject = () => {
  const context = useContext(ProjectContext);
  if (!context) throw new Error('useProject must be used within ProjectProvider');
  return context;
};
