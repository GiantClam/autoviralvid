import React, { useRef, useState, useCallback } from 'react';
import { useEditor, ClipStatus } from '../../contexts/EditorContext';
import { ItemType, TimelineItem } from '../../lib/types';
import { Film, Type, RefreshCw, Trash2, Loader2, CheckCircle2, AlertCircle, Clock, GripVertical } from 'lucide-react';

const SCALE = 50;

// Status indicator badge
const StatusBadge: React.FC<{ status?: ClipStatus }> = ({ status }) => {
    if (!status) return null;

    const config: Record<ClipStatus, { icon: React.ReactNode; color: string; label: string }> = {
        pending: { icon: <Clock size={10} />, color: 'bg-yellow-500', label: 'Queued' },
        processing: { icon: <Loader2 size={10} className="animate-spin" />, color: 'bg-[#E11D48]', label: 'Processing' },
        submitted: { icon: <Loader2 size={10} className="animate-spin" />, color: 'bg-cyan-500', label: 'Generating' },
        succeeded: { icon: <CheckCircle2 size={10} />, color: 'bg-green-500', label: 'Done' },
        failed: { icon: <AlertCircle size={10} />, color: 'bg-red-500', label: 'Failed' },
    };

    const c = config[status];
    return (
        <span className={`flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[8px] text-white ${c.color}`}>
            {c.icon}
            <span>{c.label}</span>
        </span>
    );
};

// Context menu for clip actions
const ClipContextMenu: React.FC<{
    x: number;
    y: number;
    clipIdx: number;
    itemId: string;
    status?: ClipStatus;
    onRegenerate: () => void;
    onDelete: () => void;
    onClose: () => void;
}> = ({ x, y, onRegenerate, onDelete, onClose }) => {
    return (
        <div
            className="fixed z-50 bg-[#2a2a2a] border border-[#444] rounded-lg shadow-2xl py-1 min-w-[160px]"
            style={{ left: x, top: y }}
            onClick={e => e.stopPropagation()}
        >
            <button
                onClick={() => { onRegenerate(); onClose(); }}
                className="w-full px-3 py-2 text-left text-xs text-white hover:bg-[#3a3a3a] flex items-center gap-2 transition-colors"
            >
                <RefreshCw size={12} />
                Regenerate
            </button>
            <div className="border-t border-[#444] my-0.5" />
            <button
                onClick={() => { onDelete(); onClose(); }}
                className="w-full px-3 py-2 text-left text-xs text-red-400 hover:bg-[#3a3a3a] flex items-center gap-2 transition-colors"
            >
                <Trash2 size={12} />
                Delete Clip
            </button>
        </div>
    );
};

const TimelineItemBlock: React.FC<{
    item: TimelineItem;
    isSelected: boolean;
    clipStatus?: ClipStatus;
    isDragOver?: boolean;
    onSelect: () => void;
    onContextMenu: (e: React.MouseEvent) => void;
    onDragStart: (e: React.DragEvent) => void;
    onDragOver: (e: React.DragEvent) => void;
    onDrop: (e: React.DragEvent) => void;
    onDragEnd: () => void;
}> = ({ item, isSelected, clipStatus, isDragOver, onSelect, onContextMenu, onDragStart, onDragOver, onDrop, onDragEnd }) => {
    let bgColor = 'bg-[#E11D48]';
    if (item.type === ItemType.IMAGE) bgColor = 'bg-[#BE123C]';
    if (item.type === ItemType.TEXT) bgColor = 'bg-orange-600';
    if (item.type === ItemType.AUDIO) bgColor = 'bg-emerald-600';

    const isGenerating = clipStatus && ['pending', 'processing', 'submitted'].includes(clipStatus);
    const isFailed = clipStatus === 'failed';

    return (
        <div
            draggable
            onClick={(e) => { e.stopPropagation(); onSelect(); }}
            onContextMenu={(e) => { e.preventDefault(); e.stopPropagation(); onContextMenu(e); }}
            onDragStart={onDragStart}
            onDragOver={onDragOver}
            onDrop={onDrop}
            onDragEnd={onDragEnd}
            className={`absolute h-[64px] rounded border-2 cursor-grab active:cursor-grabbing transition-all flex flex-col justify-center px-3 gap-1 text-white text-xs overflow-hidden
                ${bgColor}
                ${isGenerating ? 'opacity-60 animate-pulse' : ''}
                ${isFailed ? 'opacity-70 border-red-500' : ''}
                ${isDragOver ? 'border-yellow-400 scale-105' : ''}
                ${isSelected ? 'border-white z-10 scale-[1.02] shadow-xl shadow-black/50' : 'border-transparent hover:opacity-100'}
            `}
            style={{ left: `${item.startTime * SCALE}px`, width: `${item.duration * SCALE}px`, top: '8px' }}
        >
            <div className="flex items-center gap-1.5">
                <GripVertical size={10} className="opacity-40 shrink-0" />
                {item.type === ItemType.VIDEO && <Film size={12} />}
                {item.type === ItemType.TEXT && <Type size={12} />}
                <span className="truncate font-medium">{item.name}</span>
            </div>
            {clipStatus && item.type === ItemType.VIDEO && (
                <StatusBadge status={clipStatus} />
            )}
        </div>
    );
};

const Timeline: React.FC = () => {
    const { project, currentTime, seek, selectedItemId, selectItem, updateTrackItems, clipStatuses, regenerateItem, deleteItem } = useEditor();
    const timelineRef = useRef<HTMLDivElement>(null);
    const [contextMenu, setContextMenu] = useState<{ x: number; y: number; clipIdx: number; itemId: string } | null>(null);
    const [dragItemId, setDragItemId] = useState<string | null>(null);
    const [dragOverItemId, setDragOverItemId] = useState<string | null>(null);

    const handleTimelineClick = (e: React.MouseEvent) => {
        if (!timelineRef.current) return;
        const rect = timelineRef.current.getBoundingClientRect();
        const x = e.clientX - rect.left + timelineRef.current.scrollLeft;
        seek(Math.max(0, x / SCALE));
        setContextMenu(null);
    };

    const getClipIdx = (itemId: string): number => {
        const match = itemId.match(/clip-(\d+)/);
        return match ? parseInt(match[1], 10) : -1;
    };

    // Drag-and-drop handlers for reordering clips within a track
    const handleDragStart = useCallback((e: React.DragEvent, itemId: string) => {
        setDragItemId(itemId);
        e.dataTransfer.effectAllowed = 'move';
        e.dataTransfer.setData('text/plain', itemId);
    }, []);

    const handleDragOver = useCallback((e: React.DragEvent, itemId: string) => {
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';
        if (itemId !== dragItemId) {
            setDragOverItemId(itemId);
        }
    }, [dragItemId]);

    const handleDrop = useCallback((e: React.DragEvent, targetItemId: string, trackId: number) => {
        e.preventDefault();
        if (!dragItemId || dragItemId === targetItemId) {
            setDragItemId(null);
            setDragOverItemId(null);
            return;
        }

        const track = project.tracks.find(t => t.id === trackId);
        if (!track) return;

        const items = [...track.items];
        const dragIdx = items.findIndex(i => i.id === dragItemId);
        const dropIdx = items.findIndex(i => i.id === targetItemId);

        if (dragIdx === -1 || dropIdx === -1) return;

        // Remove dragged item and insert at drop position
        const [draggedItem] = items.splice(dragIdx, 1);
        items.splice(dropIdx, 0, draggedItem);

        // Recalculate start times sequentially
        let runningStart = 0;
        const reorderedItems = items.map(item => {
            const updated = { ...item, startTime: runningStart };
            runningStart += item.duration;
            return updated;
        });

        updateTrackItems(trackId, reorderedItems);
        setDragItemId(null);
        setDragOverItemId(null);
    }, [dragItemId, project.tracks, updateTrackItems]);

    const handleDragEnd = useCallback(() => {
        setDragItemId(null);
        setDragOverItemId(null);
    }, []);

    return (
        <div className="flex-1 bg-[#151515] flex flex-col border-t border-[#333]">
            {contextMenu && (
                <div className="fixed inset-0 z-40" onClick={() => setContextMenu(null)} />
            )}

            <div className="flex-1 flex overflow-hidden relative">
                <div className="w-24 bg-[#1e1e1e] border-r border-[#333] shrink-0 pt-8">
                    {project.tracks.map(track => (
                        <div key={track.id} className="h-20 border-b border-[#333] flex flex-col justify-center px-4 gap-1">
                            <span className="text-[10px] text-white font-bold">{track.name}</span>
                            <span className="text-[8px] text-gray-500 uppercase">{track.type}</span>
                        </div>
                    ))}
                </div>

                <div
                    ref={timelineRef}
                    className="flex-1 overflow-x-auto relative bg-[#111]"
                    onMouseDown={handleTimelineClick}
                >
                    <div style={{ width: `${Math.max(project.duration + 10, 60) * SCALE}px`, height: '100%' }} className="relative pt-8">
                        <div className="absolute top-0 h-8 border-b border-[#333] w-full flex items-end">
                            {Array.from({ length: Math.ceil(project.duration + 5) }).map((_, i) => (
                                <div key={i} className="absolute h-3 border-l border-gray-700 text-[8px] text-gray-600 pl-1" style={{ left: `${i * SCALE}px` }}>{i}s</div>
                            ))}
                        </div>

                        {project.tracks.map(track => (
                            <div key={track.id} className="h-20 border-b border-[#222] relative">
                                {track.items.map(item => {
                                    const clipIdx = getClipIdx(item.id);
                                    return (
                                        <TimelineItemBlock
                                            key={item.id}
                                            item={item}
                                            isSelected={selectedItemId === item.id}
                                            clipStatus={clipIdx >= 0 ? clipStatuses.get(clipIdx) : undefined}
                                            isDragOver={dragOverItemId === item.id}
                                            onSelect={() => selectItem(item.id)}
                                            onContextMenu={(e) => {
                                                if (clipIdx >= 0) {
                                                    setContextMenu({ x: e.clientX, y: e.clientY, clipIdx, itemId: item.id });
                                                }
                                            }}
                                            onDragStart={(e) => handleDragStart(e, item.id)}
                                            onDragOver={(e) => handleDragOver(e, item.id)}
                                            onDrop={(e) => handleDrop(e, item.id, track.id)}
                                            onDragEnd={handleDragEnd}
                                        />
                                    );
                                })}
                            </div>
                        ))}
                        <div className="absolute top-0 bottom-0 w-[2px] bg-red-600 z-40 pointer-events-none" style={{ left: `${currentTime * SCALE}px` }} />
                    </div>
                </div>
            </div>

            {contextMenu && (
                <ClipContextMenu
                    x={contextMenu.x}
                    y={contextMenu.y}
                    clipIdx={contextMenu.clipIdx}
                    itemId={contextMenu.itemId}
                    status={clipStatuses.get(contextMenu.clipIdx)}
                    onRegenerate={() => regenerateItem(contextMenu.clipIdx)}
                    onDelete={() => deleteItem(contextMenu.itemId)}
                    onClose={() => setContextMenu(null)}
                />
            )}
        </div>
    );
};

export default Timeline;
