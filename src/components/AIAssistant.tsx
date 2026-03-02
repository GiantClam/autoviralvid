"use client";

import React, { useState, useRef, useCallback, useEffect } from 'react';
import {
  MessageCircle,
  X,
  Send,
  Loader2,
  Sparkles,
  Minimize2,
  Wand2,
} from 'lucide-react';
import { projectApi } from '@/lib/project-client';
import { useProject } from '@/contexts/ProjectContext';

interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  timestamp: number;
}

export default function AIAssistant() {
  const { project, scenes, phase } = useProject();
  const [isOpen, setIsOpen] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      role: 'assistant',
      content: '你好！我是 AI 创意助手。我可以帮你优化分镜描述、推荐风格搭配、解答生成问题。有什么需要帮助的吗？',
      timestamp: Date.now(),
    },
  ]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  useEffect(() => {
    if (isOpen) {
      setTimeout(() => inputRef.current?.focus(), 100);
    }
  }, [isOpen]);

  const sendMessage = useCallback(async () => {
    const text = input.trim();
    if (!text || isLoading) return;

    const userMessage: ChatMessage = {
      role: 'user',
      content: text,
      timestamp: Date.now(),
    };
    setMessages(prev => [...prev, userMessage]);
    setInput('');
    setIsLoading(true);

    try {
      const projectContext: Record<string, unknown> = {};
      if (project) {
        projectContext.template_id = project.template_id;
        projectContext.theme = project.theme;
        projectContext.status = project.status;
        projectContext.phase = phase;
      }
      if (scenes.length > 0) {
        projectContext.scene_count = scenes.length;
        projectContext.scenes_preview = scenes.slice(0, 3).map(s => s.desc);
      }

      const result = await projectApi.aiChat(text, projectContext);

      const assistantMessage: ChatMessage = {
        role: 'assistant',
        content: result.reply || '抱歉，我暂时无法回答这个问题。',
        timestamp: Date.now(),
      };
      setMessages(prev => [...prev, assistantMessage]);
    } catch (e) {
      const errorMessage: ChatMessage = {
        role: 'assistant',
        content: `出错了：${e instanceof Error ? e.message : '网络异常，请稍后重试'}`,
        timestamp: Date.now(),
      };
      setMessages(prev => [...prev, errorMessage]);
    } finally {
      setIsLoading(false);
    }
  }, [input, isLoading, project, scenes, phase]);

  if (!isOpen) {
    return (
      <button
        onClick={() => setIsOpen(true)}
        className="fixed bottom-6 right-6 z-40 group"
      >
        <div className="relative">
          <div className="absolute inset-0 rounded-full bg-gradient-to-r from-[#E11D48] to-[#9333EA] blur-lg opacity-50 group-hover:opacity-75 transition-opacity animate-pulse-glow" />
          <div className="relative w-14 h-14 rounded-full bg-gradient-to-br from-[#E11D48] to-[#9333EA] flex items-center justify-center shadow-lg shadow-[#E11D48]/30 group-hover:shadow-[#E11D48]/50 group-hover:scale-110 transition-all duration-300">
            <MessageCircle className="w-6 h-6 text-white" />
          </div>
          <div className="absolute -top-1 -right-1 w-4 h-4 bg-emerald-500 rounded-full border-2 border-[#050508] animate-pulse" />
        </div>
      </button>
    );
  }

  return (
    <div className="fixed bottom-6 right-6 z-50 w-[400px] h-[560px] bg-[#0a0a12]/95 backdrop-blur-xl border border-white/[0.08] rounded-3xl shadow-2xl shadow-black/60 flex flex-col overflow-hidden animate-fade-in-up">
      <div className="absolute inset-0 bg-gradient-to-br from-[#E11D48]/5 via-transparent to-purple-500/5 pointer-events-none" />
      
      <div className="flex items-center justify-between px-5 py-4 border-b border-white/[0.06] bg-gradient-to-r from-[#E11D48]/10 to-transparent relative">
        <div className="flex items-center gap-3">
          <div className="relative">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-[#E11D48] to-[#9333EA] flex items-center justify-center shadow-lg shadow-[#E11D48]/30">
              <Wand2 className="w-5 h-5 text-white" />
            </div>
            <div className="absolute -bottom-0.5 -right-0.5 w-3 h-3 bg-emerald-500 rounded-full border-2 border-[#0a0a12]" />
          </div>
          <div>
            <span className="text-sm font-bold text-white">AI 创意助手</span>
            <div className="flex items-center gap-1.5 text-xs text-emerald-400">
              <span className="w-1.5 h-1.5 bg-emerald-400 rounded-full animate-pulse" />
              在线
            </div>
          </div>
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={() => setIsOpen(false)}
            className="p-2 rounded-xl hover:bg-white/[0.05] text-gray-500 hover:text-white transition-all duration-200 cursor-pointer"
          >
            <Minimize2 className="w-4 h-4" />
          </button>
          <button
            onClick={() => setIsOpen(false)}
            className="p-2 rounded-xl hover:bg-white/[0.05] text-gray-500 hover:text-white transition-all duration-200 cursor-pointer"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-5 space-y-4 relative">
        {messages.map((msg, idx) => (
          <div
            key={idx}
            className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'} animate-fade-in-up`}
            style={{ animationDelay: `${idx * 0.05}s` }}
          >
            <div
              className={`max-w-[85%] px-4 py-3 text-sm leading-relaxed ${
                msg.role === 'user'
                  ? 'bg-gradient-to-r from-[#E11D48] to-[#BE123C] text-white rounded-2xl rounded-br-md shadow-lg shadow-[#E11D48]/20'
                  : 'bg-white/[0.05] border border-white/[0.06] text-gray-200 rounded-2xl rounded-bl-md'
              }`}
            >
              {msg.content}
            </div>
          </div>
        ))}
        {isLoading && (
          <div className="flex justify-start animate-fade-in-up">
            <div className="bg-white/[0.05] border border-white/[0.06] rounded-2xl rounded-bl-md px-5 py-4">
              <div className="flex items-center gap-2">
                <div className="w-2 h-2 bg-[#E11D48] rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                <div className="w-2 h-2 bg-[#E11D48] rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                <div className="w-2 h-2 bg-[#E11D48] rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
              </div>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {messages.length <= 2 && (
        <div className="px-5 pb-3 flex flex-wrap gap-2 relative">
          {['优化分镜描述', '推荐风格搭配', '提高视频质量'].map(action => (
            <button
              key={action}
              onClick={() => {
                setInput(action);
                setTimeout(() => sendMessage(), 0);
              }}
              className="text-xs px-3.5 py-2 rounded-xl bg-white/[0.03] border border-white/[0.06] text-gray-400 hover:text-[#E11D48] hover:bg-[#E11D48]/5 hover:border-[#E11D48]/20 transition-all duration-200 cursor-pointer"
            >
              <Sparkles className="w-3 h-3 inline mr-1.5" />
              {action}
            </button>
          ))}
        </div>
      )}

      <div className="px-5 py-4 border-t border-white/[0.06] bg-[#0a0a12]/50 relative">
        <div className="flex items-center gap-2">
          <input
            ref={inputRef}
            type="text"
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && sendMessage()}
            placeholder="输入你的问题..."
            className="flex-1 bg-white/[0.03] border border-white/[0.06] rounded-xl px-4 py-3 text-sm text-gray-200 placeholder-gray-600 focus:border-[#E11D48]/50 focus:ring-2 focus:ring-[#E11D48]/10 focus:outline-none transition-all duration-300"
            disabled={isLoading}
          />
          <button
            onClick={sendMessage}
            disabled={!input.trim() || isLoading}
            className="p-3 rounded-xl bg-gradient-to-r from-[#E11D48] to-[#9333EA] hover:from-[#F43F5E] hover:to-[#A855F7] disabled:opacity-40 disabled:cursor-not-allowed text-white transition-all duration-300 cursor-pointer shadow-lg shadow-[#E11D48]/20 hover:shadow-[#E11D48]/40"
          >
            {isLoading ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Send className="w-4 h-4" />
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
