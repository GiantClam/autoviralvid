"use client"

import React, { createContext, useContext, useState, useEffect, useRef, useCallback } from 'react';
import { VideoProject, TimelineItem, Asset, ItemType } from '../lib/types';
import { INITIAL_PROJECT, INITIAL_ASSETS } from '../constants';
import { VideoTask, getTasksForRun, regenerateClip, stitchRun } from '../lib/saleagent-client';

// Status for each clip in the editor
export type ClipStatus = 'pending' | 'processing' | 'submitted' | 'succeeded' | 'failed';

interface EditorContextType {
    project: VideoProject;
    setProject: React.Dispatch<React.SetStateAction<VideoProject>>;
    currentTime: number;
    isPlaying: boolean;
    togglePlay: () => void;
    seek: (time: number) => void;
    updateTrackItems: (trackId: number, newItems: TimelineItem[]) => void;
    selectedItemId: string | null;
    selectItem: (id: string | null) => void;
    assets: Asset[];
    addAsset: (asset: Asset) => void;
    updateItem: (itemId: string, updates: Partial<TimelineItem>) => void;
    deleteItem: (itemId: string) => void;
    // Phase 1 additions
    videoTasks: VideoTask[];
    clipStatuses: Map<number, ClipStatus>;
    syncFromRunId: (runId: string) => Promise<void>;
    regenerateItem: (clipIdx: number, newPrompt?: string) => Promise<void>;
    stitchAll: () => Promise<void>;
    isSyncing: boolean;
    isStitching: boolean;
    allClipsDone: boolean;
    finalVideoUrl: string | null;
    setFinalVideoUrl: (url: string | null) => void;
}

const EditorContext = createContext<EditorContextType | undefined>(undefined);

export const EditorProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
    const [project, setProject] = useState<VideoProject>(INITIAL_PROJECT || {
        name: 'Untitled Project',
        width: 1280,
        height: 720,
        fps: 30,
        duration: 15,
        backgroundColor: '#000000',
        tracks: [
            { id: 1, type: 'video', name: 'Main Track', items: [] },
            { id: 2, type: 'overlay', name: 'Text Overlay', items: [] },
            { id: 3, type: 'audio', name: 'Background Music', items: [] }
        ]
    });
    const [currentTime, setCurrentTime] = useState(0);
    const [isPlaying, setIsPlaying] = useState(false);
    const [selectedItemId, setSelectedItemId] = useState<string | null>(null);
    const [assets, setAssets] = useState<Asset[]>(INITIAL_ASSETS || []);

    // Phase 1 state
    const [videoTasks, setVideoTasks] = useState<VideoTask[]>([]);
    const [clipStatuses, setClipStatuses] = useState<Map<number, ClipStatus>>(new Map());
    const [isSyncing, setIsSyncing] = useState(false);
    const [isStitching, setIsStitching] = useState(false);
    const [allClipsDone, setAllClipsDone] = useState(false);
    const [finalVideoUrl, setFinalVideoUrl] = useState<string | null>(null);
    const syncIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
    const activeRunIdRef = useRef<string | null>(null);

    const lastTimeRef = useRef<number>(0);
    const requestRef = useRef<number | null>(null);

    const animate = (time: number) => {
        if (lastTimeRef.current !== 0) {
            const deltaTime = (time - lastTimeRef.current) / 1000;
            setCurrentTime(prev => {
                const next = prev + deltaTime;
                if (next >= project.duration) {
                    setIsPlaying(false);
                    return 0;
                }
                return next;
            });
        }
        lastTimeRef.current = time;
        if (isPlaying) {
            requestRef.current = requestAnimationFrame(animate);
        }
    };

    useEffect(() => {
        if (isPlaying) {
            lastTimeRef.current = 0;
            requestRef.current = requestAnimationFrame(animate);
        } else {
            if (requestRef.current) {
                cancelAnimationFrame(requestRef.current);
            }
            lastTimeRef.current = 0;
        }
        return () => {
            if (requestRef.current) cancelAnimationFrame(requestRef.current);
        };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [isPlaying, project.duration]);

    // Cleanup polling on unmount
    useEffect(() => {
        return () => {
            if (syncIntervalRef.current) clearInterval(syncIntervalRef.current);
        };
    }, []);

    const togglePlay = () => setIsPlaying(prev => !prev);

    const seek = (time: number) => {
        setIsPlaying(false);
        setCurrentTime(Math.max(0, Math.min(time, project.duration)));
    };

    const updateTrackItems = (trackId: number, newItems: TimelineItem[]) => {
        setProject(prev => ({
            ...prev,
            tracks: prev.tracks.map(t =>
                t.id === trackId ? { ...t, items: newItems } : t
            )
        }));
    };

    const updateItem = (itemId: string, updates: Partial<TimelineItem>) => {
        setProject(prev => {
            const newTracks = prev.tracks.map(track => {
                const itemIndex = track.items.findIndex(i => i.id === itemId);
                if (itemIndex === -1) return track;
                const originalItem = track.items[itemIndex];
                const newItems = [...track.items];
                const updatedItem = { ...originalItem, ...updates };
                if (updates.style && originalItem.style) {
                    updatedItem.style = { ...originalItem.style, ...updates.style };
                } else if (updates.style) {
                    updatedItem.style = updates.style;
                }
                newItems[itemIndex] = updatedItem;
                return { ...track, items: newItems };
            });
            return { ...prev, tracks: newTracks };
        });
    };

    const deleteItem = (itemId: string) => {
        setProject(prev => {
            const newTracks = prev.tracks.map(track => ({
                ...track,
                items: track.items.filter(i => i.id !== itemId)
            }));
            return { ...prev, tracks: newTracks };
        });
        if (selectedItemId === itemId) {
            setSelectedItemId(null);
        }
    };

    const selectItem = (id: string | null) => {
        setSelectedItemId(id);
    };

    const addAsset = (asset: Asset) => {
        setAssets(prev => [asset, ...prev]);
    };

    // ---- Phase 1: sync tasks from backend ----

    const applyTasksToTimeline = useCallback((tasks: VideoTask[]) => {
        const newStatuses = new Map<number, ClipStatus>();
        const videoItems: TimelineItem[] = [];
        let runningStart = 0;

        for (const task of tasks) {
            newStatuses.set(task.clip_idx, task.status);
            const dur = task.duration || 10;
            videoItems.push({
                id: `clip-${task.clip_idx}`,
                type: ItemType.VIDEO,
                content: task.video_url || '',
                startTime: runningStart,
                duration: dur,
                trackId: 1,
                name: task.status === 'succeeded'
                    ? `Scene ${task.clip_idx + 1}`
                    : `Scene ${task.clip_idx + 1} (${task.status})`,
            });
            runningStart += dur;
        }

        setClipStatuses(newStatuses);
        setVideoTasks(tasks);

        const allDone = tasks.length > 0 && tasks.every(t => t.status === 'succeeded');
        setAllClipsDone(allDone);

        // Update the video track (track id 1)
        setProject(prev => {
            const totalDuration = Math.max(runningStart, prev.duration);
            return {
                ...prev,
                duration: totalDuration,
                tracks: prev.tracks.map(t =>
                    t.id === 1 ? { ...t, items: videoItems } : t
                ),
            };
        });

        // Add completed clips as assets
        const completedAssets: Asset[] = tasks
            .filter(t => t.status === 'succeeded' && t.video_url)
            .map(t => ({
                id: `asset-clip-${t.clip_idx}`,
                type: ItemType.VIDEO,
                url: t.video_url!,
                name: `Scene ${t.clip_idx + 1}`,
            }));

        if (completedAssets.length > 0) {
            setAssets(prev => {
                const existingIds = new Set(prev.map(a => a.id));
                const newAssets = completedAssets.filter(a => !existingIds.has(a.id));
                return newAssets.length > 0 ? [...prev, ...newAssets] : prev;
            });
        }
    }, []);

    const syncFromRunId = useCallback(async (runId: string) => {
        if (!runId) return;
        activeRunIdRef.current = runId;
        setIsSyncing(true);

        try {
            const response = await getTasksForRun(runId);
            applyTasksToTimeline(response.tasks);

            // Update project runId
            setProject(prev => ({ ...prev, runId }));

            // If not all done, start polling every 5 seconds
            if (!response.summary.all_done) {
                if (syncIntervalRef.current) clearInterval(syncIntervalRef.current);
                syncIntervalRef.current = setInterval(async () => {
                    if (activeRunIdRef.current !== runId) {
                        if (syncIntervalRef.current) clearInterval(syncIntervalRef.current);
                        return;
                    }
                    try {
                        const updated = await getTasksForRun(runId);
                        applyTasksToTimeline(updated.tasks);
                        if (updated.summary.all_done && syncIntervalRef.current) {
                            clearInterval(syncIntervalRef.current);
                            syncIntervalRef.current = null;
                        }
                    } catch {
                        // silently retry on next interval
                    }
                }, 5000);
            }
        } catch (err) {
            console.error('[EditorContext] Failed to sync tasks:', err);
        } finally {
            setIsSyncing(false);
        }
    }, [applyTasksToTimeline]);

    const regenerateItem = useCallback(async (clipIdx: number, newPrompt?: string) => {
        const runId = activeRunIdRef.current || project.runId;
        if (!runId) return;

        // Optimistic status update
        setClipStatuses(prev => new Map(prev).set(clipIdx, 'pending'));

        try {
            await regenerateClip(runId, clipIdx, newPrompt);
            // Restart polling
            await syncFromRunId(runId);
        } catch (err) {
            console.error('[EditorContext] Failed to regenerate clip:', err);
        }
    }, [project.runId, syncFromRunId]);

    const stitchAll = useCallback(async () => {
        const runId = activeRunIdRef.current || project.runId;
        if (!runId) return;

        setIsStitching(true);
        try {
            await stitchRun(runId);
            // The stitching runs in background; we can poll for completion
            // For now, just indicate it's in progress
        } catch (err) {
            console.error('[EditorContext] Failed to stitch:', err);
        } finally {
            setIsStitching(false);
        }
    }, [project.runId]);

    return (
        <EditorContext.Provider value={{
            project,
            setProject,
            currentTime,
            isPlaying,
            togglePlay,
            seek,
            updateTrackItems,
            selectedItemId,
            selectItem,
            assets,
            addAsset,
            updateItem,
            deleteItem,
            // Phase 1
            videoTasks,
            clipStatuses,
            syncFromRunId,
            regenerateItem,
            stitchAll,
            isSyncing,
            isStitching,
            allClipsDone,
            finalVideoUrl,
            setFinalVideoUrl,
        }}>
            {children}
        </EditorContext.Provider>
    );
};

export const useEditor = () => {
    const context = useContext(EditorContext);
    if (!context) throw new Error('useEditor must be used within EditorProvider');
    return context;
};
