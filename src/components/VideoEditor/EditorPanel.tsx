import React, { useMemo, useState } from 'react';
import Player from './Player';
import Timeline from './Timeline';
import AssetLibrary from './AssetLibrary';
import PropertyEditor from './PropertyEditor';
import { Download, Clapperboard, Loader2, Sparkles, ExternalLink, CheckCircle2 } from 'lucide-react';
import { useEditor } from '../../contexts/EditorContext';
import { buildRenderJobRequest, summarizeRenderJob } from '../../lib/render';

const EditorPanel: React.FC = () => {
    const {
        project,
        allClipsDone,
        isStitching,
        stitchAll,
        isSyncing,
        videoTasks,
        finalVideoUrl,
    } = useEditor();
    const [isSubmittingRender, setIsSubmittingRender] = useState(false);
    const [lastRenderMessage, setLastRenderMessage] = useState<string | null>(null);

    const renderRequest = useMemo(() => {
        return buildRenderJobRequest({
            ...project,
            fps: project.fps || 30,
            backgroundColor: project.backgroundColor || '#000000'
        });
    }, [project]);

    const renderSummary = useMemo(() => summarizeRenderJob(renderRequest), [renderRequest]);

    const downloadJson = (payload: unknown, filename: string) => {
        const dataStr = `data:text/json;charset=utf-8,${encodeURIComponent(JSON.stringify(payload, null, 2))}`;
        const downloadAnchorNode = document.createElement('a');
        downloadAnchorNode.setAttribute('href', dataStr);
        downloadAnchorNode.setAttribute('download', filename);
        document.body.appendChild(downloadAnchorNode);
        downloadAnchorNode.click();
        downloadAnchorNode.remove();
    };

    const handleExportTimeline = () => {
        downloadJson(project, `${project.name.replace(/\s+/g, '_')}_timeline.json`);
    };

    const handleSubmitRenderJob = async () => {
        setIsSubmittingRender(true);
        setLastRenderMessage(null);
        try {
            const res = await fetch('/api/render/jobs', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(renderRequest)
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok) throw new Error(data?.error || `HTTP ${res.status}`);
            const msg = data?.job_id
                ? `Render job submitted: ${data.job_id}`
                : `Render request accepted`;
            setLastRenderMessage(msg);
        } catch (error) {
            setLastRenderMessage(`Render failed: ${error instanceof Error ? error.message : 'Unknown error'}`);
        } finally {
            setIsSubmittingRender(false);
        }
    };

    // Count task statuses for the status bar
    const succeededCount = videoTasks.filter(t => t.status === 'succeeded').length;
    const totalCount = videoTasks.length;
    const pendingCount = videoTasks.filter(t => ['pending', 'processing', 'submitted'].includes(t.status)).length;
    const failedCount = videoTasks.filter(t => t.status === 'failed').length;

    return (
        <div className="flex flex-col h-full w-full bg-[#000]">
            <div className="h-12 bg-[#1e1e1e] border-b border-[#333] flex items-center justify-between px-6 shrink-0 z-30">
                <div className="flex items-center gap-2">
                    <h1 className="text-white font-bold text-lg bg-gradient-to-r from-[#E11D48] to-[#F43F5E] bg-clip-text text-transparent">AutoViralVid</h1>
                    <span className="text-gray-500 text-sm">/</span>
                    <span className="text-gray-300 text-sm font-medium truncate max-w-[200px]">{project.name}</span>
                </div>

                <div className="flex items-center gap-3">
                    <button
                        onClick={handleExportTimeline}
                        className="px-3 py-1 rounded-md text-xs font-medium bg-zinc-700 text-white hover:bg-zinc-600 transition-colors flex items-center gap-1.5"
                    >
                        <Download size={14} />
                        Export
                    </button>

                    {/* One-Click Stitch Button - the main CTA */}
                    <button
                        onClick={stitchAll}
                        disabled={!allClipsDone || isStitching}
                        className={`px-4 py-1.5 rounded-md text-xs font-bold transition-all flex items-center gap-1.5 shadow-lg
                            ${allClipsDone && !isStitching
                                ? 'bg-gradient-to-r from-purple-600 to-pink-600 text-white hover:from-purple-500 hover:to-pink-500 shadow-purple-500/30'
                                : 'bg-zinc-700 text-gray-400 cursor-not-allowed'
                            }`}
                    >
                        {isStitching ? (
                            <>
                                <Loader2 size={14} className="animate-spin" />
                                Stitching...
                            </>
                        ) : finalVideoUrl ? (
                            <>
                                <CheckCircle2 size={14} />
                                Stitched!
                            </>
                        ) : (
                            <>
                                <Sparkles size={14} />
                                Synthesize Video
                            </>
                        )}
                    </button>

                    {/* Legacy render button */}
                    <button
                        onClick={handleSubmitRenderJob}
                        disabled={isSubmittingRender}
                        className="px-3 py-1 rounded-md text-xs font-medium bg-emerald-600 text-white hover:bg-emerald-500 transition-colors flex items-center gap-1.5 disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                        {isSubmittingRender ? <Loader2 size={14} className="animate-spin" /> : <Clapperboard size={14} />}
                        Render
                    </button>
                </div>
            </div>

            {/* Status bar */}
            <div className="h-8 px-6 border-b border-[#333] bg-[#121212] flex items-center justify-between text-[10px] text-gray-400">
                <span className="flex items-center gap-3">
                    {totalCount > 0 && (
                        <>
                            <span className="text-green-400">{succeededCount}/{totalCount} clips done</span>
                            {pendingCount > 0 && <span className="text-yellow-400">{pendingCount} generating</span>}
                            {failedCount > 0 && <span className="text-red-400">{failedCount} failed</span>}
                        </>
                    )}
                    {isSyncing && <span className="text-cyan-400 flex items-center gap-1"><Loader2 size={10} className="animate-spin" /> Syncing...</span>}
                </span>
                <span>
                    {renderSummary.durationSeconds.toFixed(1)}s @ {renderSummary.fps}fps | {renderSummary.layerCount} layers
                </span>
                {finalVideoUrl && (
                    <a
                        href={finalVideoUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-purple-400 hover:text-purple-300 flex items-center gap-1 transition-colors"
                    >
                        <ExternalLink size={10} />
                        Download Final Video
                    </a>
                )}
                {!finalVideoUrl && (
                    <span className={lastRenderMessage?.includes('failed') ? 'text-red-400' : 'text-emerald-400'}>
                        {lastRenderMessage || (allClipsDone ? 'All clips ready! Click "Synthesize Video"' : 'Waiting for clips...')}
                    </span>
                )}
            </div>

            <div className="flex-1 flex flex-col min-h-0">
                <div className="h-[60%] flex border-b border-[#333]">
                    <div className="w-[300px] shrink-0 border-r border-[#333]">
                        <AssetLibrary />
                    </div>
                    <div className="flex-1 min-w-0">
                        <Player />
                    </div>
                    <div className="w-[300px] shrink-0 border-l border-[#333]">
                        <PropertyEditor />
                    </div>
                </div>

                <div className="h-[40%] min-h-[200px]">
                    <Timeline />
                </div>
            </div>
        </div>
    );
};

export default EditorPanel;
