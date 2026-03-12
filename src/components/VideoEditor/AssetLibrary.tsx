import React, { useRef } from 'react';
import { useEditor } from '../../contexts/EditorContext';
import { Upload, Video, Music } from 'lucide-react';
import { Asset, ItemType } from '../../lib/types';

const AssetLibrary: React.FC = () => {
    const { assets, addAsset } = useEditor();
    const fileInputRef = useRef<HTMLInputElement>(null);

    const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (!file) return;

        const url = URL.createObjectURL(file);
        let type = ItemType.VIDEO;

        if (file.type.startsWith('image/')) type = ItemType.IMAGE;
        else if (file.type.startsWith('audio/')) type = ItemType.AUDIO;

        addAsset({
            id: `asset-${Date.now()}`,
            type,
            name: file.name,
            url,
            thumbnail: type === ItemType.IMAGE ? url : undefined
        });
    };

    const handleDragStart = (e: React.DragEvent, asset: Asset) => {
        e.dataTransfer.setData('application/json', JSON.stringify(asset));
        e.dataTransfer.effectAllowed = 'copy';
    };

    return (
        <div className="flex flex-col h-full bg-[#0F0F23] border-r border-white/[0.08]">
            <div className="p-4 border-b border-white/[0.08]">
                <h3 className="text-white font-semibold mb-4 text-sm">Assets</h3>
                <button
                    onClick={() => fileInputRef.current?.click()}
                    className="w-full bg-white/[0.05] hover:bg-white/[0.08] text-white py-2 rounded-md flex items-center justify-center gap-2 transition-all duration-200 border border-white/[0.08] border-dashed text-xs cursor-pointer"
                >
                    <Upload size={14} />
                    <span>Import Media</span>
                </button>
                <input type="file" ref={fileInputRef} className="hidden" accept="image/*,video/*,audio/*" onChange={handleFileUpload} />
            </div>

            <div className="flex-1 overflow-y-auto p-3">
                <div className="grid grid-cols-2 gap-3">
                    {assets.map(asset => (
                        <div
                            key={asset.id}
                            draggable
                            onDragStart={(e) => handleDragStart(e, asset)}
                            className="group relative aspect-square bg-white/[0.03] rounded-lg overflow-hidden border border-transparent hover:border-[#E11D48] cursor-grab"
                        >
                            {(asset.type === ItemType.IMAGE || asset.thumbnail) && (asset.thumbnail || asset.url) ? (
                                // eslint-disable-next-line @next/next/no-img-element
                                <img src={asset.thumbnail || asset.url} alt={asset.name} className="w-full h-full object-cover" />
                            ) : (
                                <div className="w-full h-full flex items-center justify-center text-gray-500">
                                    {asset.type === ItemType.VIDEO && <Video size={20} />}
                                    {asset.type === ItemType.AUDIO && <Music size={20} />}
                                </div>
                            )}
                        </div>
                    ))}
                </div>
            </div>
        </div>
    );
};

export default AssetLibrary;
