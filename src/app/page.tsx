"use client";

import React, { useState, useCallback } from 'react';
import { SessionProvider, useSession } from 'next-auth/react';
import { ProjectProvider, useProject } from '@/contexts/ProjectContext';
import { TemplateGallery } from '@/components/TemplateGallery';
import { Sidebar } from '@/components/Sidebar';
import ProjectForm from '@/components/ProjectForm';
import StoryboardPanel from '@/components/StoryboardPanel';
import ClipManager from '@/components/ClipManager';
import RemotionPreview from '@/components/RemotionPreview';
import AIAssistant from '@/components/AIAssistant';
import ProgressPanel from '@/components/ProgressPanel';
import LandingPage from '@/components/LandingPage';
import LanguageSwitcher from '@/components/LanguageSwitcher';
import { useT } from '@/lib/i18n';
import { Play } from 'lucide-react';

type ViewState = 'gallery' | 'project';

function ProjectWorkspace({ initialTemplateId }: { initialTemplateId?: string }) {
  const { phase, project } = useProject();
  const t = useT();

  // Determine which panel to show on the right
  const showStoryboard = ['generating_storyboard', 'storyboard_ready', 'generating_images', 'images_ready'].includes(phase);
  const showClips = ['generating_videos', 'stitching', 'videos_ready', 'rendering', 'completed'].includes(phase);

  return (
    <div className="flex flex-1 h-full overflow-hidden">
      {/* Left: Configuration Form */}
      <div className="w-full md:w-[380px] shrink-0 overflow-y-auto">
        <ProjectForm initialTemplateId={initialTemplateId} />
      </div>

      {/* Right: Dynamic Content Area */}
      <div className="flex-1 hidden md:flex flex-col overflow-hidden border-l border-white/[0.06]">
        <ProgressPanel />
        <div className="flex-1 overflow-y-auto">
          {phase === 'idle' || phase === 'configuring' ? (
            /* ── Empty / idle state with refined visual ── */
            <div className="flex items-center justify-center h-full">
              <div className="text-center space-y-5 max-w-xs">
                {/* Decorative glow */}
                <div className="relative mx-auto w-20 h-20">
                  <div className="absolute inset-0 rounded-3xl bg-[#E11D48]/[0.06] blur-xl" />
                  <div className="relative w-20 h-20 rounded-3xl bg-gradient-to-br from-white/[0.04] to-white/[0.01]
                                  border border-white/[0.06] flex items-center justify-center
                                  shadow-[inset_0_1px_0_rgba(255,255,255,0.04)]">
                    <svg className="w-9 h-9 text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.2} d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
                    </svg>
                  </div>
                </div>
                <div className="space-y-2">
                  <p className="text-sm font-medium text-gray-400">{t("workspace.idleTitle")}</p>
                  <p className="text-xs text-gray-600 leading-relaxed">
                    {t("workspace.idleDesc")}
                  </p>
                </div>
                {/* Step indicators */}
                <div className="flex items-center justify-center gap-6 pt-2">
                  {[
                    { step: "01", label: t("workspace.step01") },
                    { step: "02", label: t("workspace.step02") },
                    { step: "03", label: t("workspace.step03") },
                  ].map((s, i) => (
                    <div key={s.step} className="flex items-center gap-2">
                      <div className="w-6 h-6 rounded-lg bg-white/[0.04] border border-white/[0.06]
                                      flex items-center justify-center text-[10px] text-gray-500 font-semibold tabular-nums">
                        {s.step}
                      </div>
                      <span className="text-[11px] text-gray-600">{s.label}</span>
                      {i < 2 && <div className="w-4 h-px bg-white/[0.06] ml-2" />}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          ) : showStoryboard ? (
            <StoryboardPanel />
          ) : showClips ? (
            <div className="flex flex-col h-full">
              {/* Clip manager + Remotion preview split */}
              <div className="flex-1 overflow-y-auto p-4">
                <ClipManager />
              </div>
              {/* Remotion preview panel */}
              <div className="shrink-0 border-t border-white/[0.06] p-4" style={{ maxHeight: '45%' }}>
                <RemotionPreview />
              </div>
            </div>
          ) : phase === 'error' ? (
            <div className="flex items-center justify-center h-full">
              <div className="text-center space-y-3">
                <div className="w-14 h-14 mx-auto rounded-2xl bg-red-500/[0.08] border border-red-500/20
                                flex items-center justify-center">
                  <span className="text-red-400 text-xl">!</span>
                </div>
                <p className="text-base font-medium text-red-400">{t("workspace.errorTitle")}</p>
                <p className="text-sm text-gray-500">{t("workspace.errorDesc")}</p>
              </div>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}

function HomeContent() {
  const { data: session, status } = useSession();
  const t = useT();
  const userEmail = session?.user?.email || '';

  const [view, setView] = useState<ViewState>('gallery');
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [selectedTemplateId, setSelectedTemplateId] = useState<string>('product-ad');
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  const handleSelectTemplate = useCallback((templateId: string) => {
    setSelectedTemplateId(templateId);
    setView('project');
  }, []);

  const handleNewProject = useCallback(() => {
    setActiveRunId(null);
    setView('gallery');
  }, []);

  const handleSelectRun = useCallback((runId: string) => {
    setActiveRunId(runId);
    setView('project');
  }, []);

  // Dev mode: skip auth gate when NEXTAUTH_SECRET is not configured
  const isDevMode = !process.env.NEXT_PUBLIC_AUTH_ENABLED;

  if (!isDevMode && status === 'loading') {
    return (
      <div className="flex items-center justify-center h-screen bg-[#060610]">
        <div className="w-8 h-8 border-2 border-[#E11D48] border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  if (!isDevMode && status === 'unauthenticated') {
    return <LandingPage />;
  }

  if (view === 'gallery') {
    return (
      <div className="flex flex-col h-screen bg-[#050508]">
        <div className="h-16 border-b border-white/[0.06] flex items-center px-4 md:px-8 justify-between bg-black/40 backdrop-blur-xl relative z-20">
          <div className="flex items-center gap-2.5 group cursor-pointer">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-[#E11D48] to-[#9333EA] flex items-center justify-center shadow-lg shadow-[#E11D48]/30 group-hover:shadow-[#E11D48]/50 transition-all duration-300">
              <Play className="w-3.5 h-3.5 text-white fill-white ml-px" />
            </div>
            <span className="font-bold tracking-tight bg-gradient-to-r from-white to-gray-300 bg-clip-text text-transparent">AutoViralVid</span>
            <div className="hidden sm:flex items-center gap-2 ml-3">
              <span className="px-2 py-0.5 rounded-full bg-[#E11D48]/10 border border-[#E11D48]/20 text-[10px] text-[#E11D48] font-medium">AI Powered</span>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <LanguageSwitcher />
            <div className="text-sm text-gray-400 hidden sm:flex items-center gap-2">
              <div className="w-7 h-7 rounded-full bg-gradient-to-br from-[#E11D48] to-purple-600 flex items-center justify-center text-xs font-bold">
                {userEmail?.[0]?.toUpperCase() || 'U'}
              </div>
              <span className="max-w-[120px] truncate">{userEmail?.split('@')[0] || 'User'}</span>
            </div>
          </div>
        </div>
        <TemplateGallery onSelect={handleSelectTemplate} />
      </div>
    );
  }

  // Project view

  return (
    <ProjectProvider>
      <div className="flex flex-col md:flex-row h-screen w-full bg-[#050508] overflow-hidden font-sans text-gray-100">
        {/* Sidebar — hidden on mobile, shown on md+ */}
        <Sidebar
          activeRunId={activeRunId}
          onSelectRun={handleSelectRun}
          onNewProject={handleNewProject}
          onBack={() => setView('gallery')}
          userEmail={userEmail}
          isCollapsed={sidebarCollapsed}
          toggleCollapse={() => setSidebarCollapsed(!sidebarCollapsed)}
          onToggleGuide={() => {}}
          className="hidden md:flex shrink-0 z-20"
        />

        {/* Mobile top bar */}
        <div className="md:hidden shrink-0 border-b border-white/[0.06] bg-black/40 backdrop-blur-xl">
          <div className="flex items-center gap-3 px-4 py-3">
          <button
            onClick={() => setView('gallery')}
            className="p-2.5 rounded-xl bg-gradient-to-br from-[#E11D48] to-[#9333EA] text-white cursor-pointer shadow-lg shadow-[#E11D48]/20"
          >
            <Play className="w-4 h-4 fill-current" />
          </button>
          <span className="text-sm font-bold text-gray-200 flex-1 bg-gradient-to-r from-white to-gray-300 bg-clip-text text-transparent">AutoViralVid</span>
          <LanguageSwitcher />
          </div>
          <ProgressPanel compact />
        </div>

        {/* Main workspace */}
        <ProjectWorkspace initialTemplateId={selectedTemplateId} />

        {/* AI Assistant floating panel */}
        <AIAssistant />
      </div>
    </ProjectProvider>
  );
}

export default function Home() {
  return (
    <SessionProvider>
      <HomeContent />
    </SessionProvider>
  );
}
