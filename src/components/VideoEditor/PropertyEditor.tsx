import React from 'react';
import { useEditor } from '../../contexts/EditorContext';
import { ItemType } from '../../lib/types';
import { Type, Video, Trash2 } from 'lucide-react';

const PropertyEditor: React.FC = () => {
    const { project, selectedItemId, updateItem, deleteItem } = useEditor();

    const selectedItem = React.useMemo(() => {
        if (!selectedItemId) return null;
        for (const track of project.tracks) {
            const item = track.items.find(i => i.id === selectedItemId);
            if (item) return item;
        }
        return null;
    }, [project, selectedItemId]);

    if (!selectedItem) {
        return (
            <div className="flex flex-col h-full bg-[#151515] p-6 items-center justify-center text-gray-500 text-xs text-center leading-relaxed">
                Select a clip on the timeline<br />to edit properties
            </div>
        );
    }

    const handleChange = (field: string, value: any, isStyle = false) => {
        if (isStyle) {
            updateItem(selectedItem.id, {
                style: { ...selectedItem.style, [field]: value }
            });
        } else {
            updateItem(selectedItem.id, { [field]: value });
        }
    };

    return (
        <div className="flex flex-col h-full bg-[#151515] overflow-y-auto">
            <div className="p-4 border-b border-[#333] bg-[#1e1e1e] flex items-center justify-between">
                <h3 className="text-white text-xs font-semibold flex items-center gap-2">
                    {selectedItem.type === ItemType.VIDEO ? <Video size={14} /> : <Type size={14} />} Properties
                </h3>
                <button onClick={() => deleteItem(selectedItem.id)} className="text-gray-500 hover:text-red-500 transition-colors"><Trash2 size={14} /></button>
            </div>

            <div className="p-4 space-y-4">
                <div className="space-y-1">
                    <label className="text-[10px] font-bold text-gray-500 uppercase tracking-wider">Name</label>
                    <input
                        type="text"
                        value={selectedItem.name}
                        onChange={(e) => handleChange('name', e.target.value)}
                        className="w-full bg-[#222] border border-[#333] rounded px-3 py-1.5 text-xs text-white"
                    />
                </div>

                {selectedItem.type === ItemType.TEXT && (
                    <div className="space-y-1">
                        <label className="text-[10px] font-bold text-gray-500 uppercase tracking-wider">Content</label>
                        <textarea
                            value={selectedItem.content}
                            onChange={(e) => handleChange('content', e.target.value)}
                            className="w-full bg-[#222] border border-[#333] rounded px-3 py-1.5 text-xs text-white"
                        />
                    </div>
                )}

                <div className="space-y-3 pt-2">
                    <label className="text-[10px] font-bold text-gray-500 uppercase tracking-wider block">Transform</label>
                    <div className="flex justify-between text-[10px] text-gray-400"><span>Scale</span><span>{selectedItem.style?.scale || 100}%</span></div>
                    <input
                        type="range" min="10" max="200" value={selectedItem.style?.scale || 100}
                        onChange={(e) => handleChange('scale', Number(e.target.value), true)}
                        className="w-full h-1 bg-[#333] rounded-lg appearance-none cursor-pointer"
                    />
                </div>
            </div>
        </div>
    );
};

export default PropertyEditor;
