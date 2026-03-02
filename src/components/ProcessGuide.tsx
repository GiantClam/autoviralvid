import React from 'react';
import { MousePointer2, MessageSquare, Wand2, Download, X, HelpCircle } from 'lucide-react';

export interface ProcessGuideProps {
    onClose?: () => void;
    className?: string;
}

export function ProcessGuide({ onClose, className = '' }: ProcessGuideProps) {
    const steps = [
        { icon: <MousePointer2 className="w-5 h-5" />, title: '1. 选择模板', color: 'blue' },
        { icon: <MessageSquare className="w-5 h-5" />, title: '2. 描述创意', color: 'purple' },
        { icon: <Wand2 className="w-5 h-5" />, title: '3. 自动生成', color: 'indigo' },
        { icon: <Download className="w-5 h-5" />, title: '4. 编辑导出', color: 'emerald' }
    ];

    return (
        <div className={`bg-[#18181b]/80 backdrop-blur-xl border-b border-white/10 p-6 relative group overflow-hidden ${className}`}>
            <div className="max-w-4xl mx-auto flex justify-between items-center">
                <div className="flex gap-8 overflow-x-auto custom-scrollbar pb-2">
                    {steps.map((step, i) => (
                        <div key={i} className="flex items-center gap-3 shrink-0">
                            <div className={`p-2 rounded-lg bg-white/5 text-gray-400 border border-white/10`}>{step.icon}</div>
                            <span className="text-sm font-medium text-gray-300">{step.title}</span>
                        </div>
                    ))}
                </div>
                {onClose && <button onClick={onClose} className="p-1.5 hover:bg-white/10 rounded-full text-gray-500 hover:text-white">✕</button>}
            </div>
        </div>
    );
}
