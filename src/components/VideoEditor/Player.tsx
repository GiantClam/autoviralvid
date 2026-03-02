import React, { useMemo, useRef, useEffect } from 'react';
import { useEditor } from '../../contexts/EditorContext';
import { ItemType } from '../../lib/types';
import { Play, Pause, SkipBack, SkipForward } from 'lucide-react';

const Player: React.FC = () => {
    const { project, currentTime, isPlaying, togglePlay, seek } = useEditor();
    const videoRef = useRef<HTMLVideoElement>(null);

    const activeItems = useMemo(() => {
        return project.tracks.flatMap(track =>
            track.items.filter(item =>
                currentTime >= item.startTime && currentTime < (item.startTime + item.duration)
            )
        ).sort((a, b) => a.trackId - b.trackId);
    }, [project, currentTime]);

    const activeVideo = activeItems.find(i => i.type === ItemType.VIDEO);
    const activeImage = activeItems.find(i => i.type === ItemType.IMAGE);
    const activeTexts = activeItems.filter(i => i.type === ItemType.TEXT);

    useEffect(() => {
        const video = videoRef.current;
        if (!video || !activeVideo) return;
        const targetTime = Math.max(0, currentTime - activeVideo.startTime);
        if (isPlaying) {
            if (video.paused) video.play().catch(() => { });
            if (Math.abs(video.currentTime - targetTime) > 0.3) video.currentTime = targetTime;
        } else {
            video.pause();
            if (Math.abs(video.currentTime - targetTime) > 0.05) video.currentTime = targetTime;
        }
    }, [currentTime, isPlaying, activeVideo]);

    const formatTime = (seconds: number) => {
        const mins = Math.floor(seconds / 60);
        const secs = Math.floor(seconds % 60);
        return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
    };

    return (
        <div className="flex flex-col h-full bg-[#111]">
            <div className="flex-1 flex items-center justify-center p-8 bg-[#0a0a0a] relative overflow-hidden">
                <div
                    className="relative bg-black shadow-2xl overflow-hidden"
                    style={{
                        aspectRatio: `${project.width}/${project.height}`,
                        height: '100%',
                        backgroundColor: project.backgroundColor || '#000000'
                    }}
                >
                    {activeVideo ? (
                        <video
                            ref={videoRef}
                            src={activeVideo.content}
                            className="absolute w-full h-full object-cover"
                            style={{
                                transform: `scale(${(activeVideo.style?.scale || 100) / 100}) rotate(${activeVideo.style?.rotation || 0}deg)`,
                                opacity: activeVideo.style?.opacity ?? 1
                            }}
                            muted
                        />
                    ) : activeImage ? (
                        <img
                            src={activeImage.content}
                            className="absolute w-full h-full object-cover"
                            style={{
                                transform: `scale(${(activeImage.style?.scale || 100) / 100}) rotate(${activeImage.style?.rotation || 0}deg)`,
                                opacity: activeImage.style?.opacity ?? 1
                            }}
                            alt="scene"
                        />
                    ) : null}

                    {activeTexts.map(text => (
                        <div
                            key={text.id}
                            className="absolute transform -translate-x-1/2 -translate-y-1/2 pointer-events-none text-center"
                            style={{
                                left: `${text.style?.x ?? 50}%`,
                                top: `${text.style?.y ?? 50}%`,
                                color: text.style?.color ?? 'white',
                                fontSize: `${(text.style?.fontSize ?? 24) * 0.5}px`,
                                opacity: text.style?.opacity ?? 1
                            }}
                        >
                            {text.content}
                        </div>
                    ))}
                </div>
            </div>

            <div className="h-10 bg-[#1e1e1e] border-t border-[#333] flex items-center justify-center gap-6 px-6 shrink-0">
                <button onClick={() => seek(0)} className="text-gray-400 hover:text-white"><SkipBack size={14} /></button>
                <button
                    onClick={togglePlay}
                    className="w-7 h-7 rounded-full bg-white text-black flex items-center justify-center hover:bg-gray-200 transition-colors"
                >
                    {isPlaying ? <Pause size={12} fill="currentColor" /> : <Play size={12} fill="currentColor" className="ml-0.5" />}
                </button>
                <button onClick={() => seek(project.duration)} className="text-gray-400 hover:text-white"><SkipForward size={14} /></button>
                <div className="text-gray-500 font-mono text-[10px] ml-4">{formatTime(currentTime)} / {formatTime(project.duration)}</div>
            </div>
        </div>
    );
};

export default Player;
