"use client";
/* eslint-disable @next/next/no-img-element */

import React, { Suspense, useCallback, useEffect, useRef, useState } from 'react';
import { SessionProvider, useSession } from 'next-auth/react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { ProjectProvider, useProject } from '@/contexts/ProjectContext';
import { TemplateGallery } from '@/components/TemplateGallery';
import { Sidebar } from '@/components/Sidebar';
import ProjectForm, { type PptV7PanelState } from '@/components/ProjectForm';
import StoryboardPanel from '@/components/StoryboardPanel';
import ClipManager from '@/components/ClipManager';
import RemotionPreview from '@/components/RemotionPreview';
import AIAssistant from '@/components/AIAssistant';
import ProgressPanel from '@/components/ProgressPanel';
import LandingPage from '@/components/LandingPage';
import LanguageSwitcher from '@/components/LanguageSwitcher';
import { useT } from '@/lib/i18n';
import { AlertTriangle, CheckCircle2, FileDown, Loader2, Play, RefreshCw } from 'lucide-react';

type ViewState = 'gallery' | 'project';

type PptV7HistoryItem = {
  id: string;
  status: 'success' | 'failed';
  runId: string;
  requirement: string;
  slideCount: number;
  createdAt: string;
  pptxUrl?: string;
  error?: string;
};

const PPT_V7_HISTORY_KEY = 'autoviralvid-ppt-v7-history';

const EMPTY_PPT_V7_STATE: PptV7PanelState = {
  enabled: false,
  busy: false,
  step: 'idle',
  error: '',
  result: null,
  requirement: '',
  slideCount: 10,
};

function loadPptV7History(): PptV7HistoryItem[] {
  if (typeof window === 'undefined') {
    return [];
  }

  try {
    const raw = window.localStorage.getItem(PPT_V7_HISTORY_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.slice(0, 20) as PptV7HistoryItem[];
  } catch {
    return [];
  }
}

function PptV7ResultPanel({
  state,
  history,
  onRetry,
}: {
  state: PptV7PanelState;
  history: PptV7HistoryItem[];
  onRetry: () => void;
}) {
  const t = useT();
  const steps: Array<{ key: PptV7PanelState['step']; label: string }> = [
    { key: 'generating', label: t("pptV7.stepGenerate") },
    { key: 'tts', label: t("pptV7.stepTts") },
    { key: 'exporting', label: t("pptV7.stepExport") },
    { key: 'done', label: t("pptV7.stepDone") },
  ];

  const currentOrder = state.step === 'idle' ? 0 : steps.findIndex((s) => s.key === state.step) + 1;

  return (
    <div className="h-full overflow-y-auto p-5">
      <div className="mx-auto max-w-4xl space-y-4">
        <div className="rounded-2xl border border-white/[0.06] bg-white/[0.02] p-5">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h3 className="text-lg font-semibold text-white">{t("pptV7.resultPanelTitle")}</h3>
              <p className="mt-1 text-sm text-gray-500">{t("pptV7.resultPanelDesc")}</p>
            </div>

            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={onRetry}
                disabled={state.busy || !state.requirement.trim()}
                className="inline-flex items-center gap-1.5 rounded-full border border-white/[0.12] bg-white/[0.04] px-3 py-1 text-xs text-gray-200 transition hover:bg-white/[0.08] disabled:opacity-40"
              >
                <RefreshCw className="h-3.5 w-3.5" />
                {t("pptV7.retry")}
              </button>

              {state.busy ? (
                <span className="inline-flex items-center gap-2 rounded-full border border-[#E11D48]/25 bg-[#E11D48]/10 px-3 py-1 text-xs text-[#E11D48]">
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  {t("pptV7.running")}
                </span>
              ) : state.result ? (
                <span className="inline-flex items-center gap-2 rounded-full border border-emerald-500/25 bg-emerald-500/10 px-3 py-1 text-xs text-emerald-300">
                  <CheckCircle2 className="h-3.5 w-3.5" />
                  {t("pptV7.completed")}
                </span>
              ) : (
                <span className="inline-flex items-center gap-2 rounded-full border border-white/[0.12] bg-white/[0.03] px-3 py-1 text-xs text-gray-400">
                  {t("pptV7.idle")}
                </span>
              )}
            </div>
          </div>

          <div className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-2">
            <div className="rounded-xl border border-white/[0.06] bg-white/[0.03] p-3">
              <p className="text-xs text-gray-500">{t("pptV7.requirement")}</p>
              <p className="mt-1 text-sm text-gray-200">
                {state.requirement || t("pptV7.requirementPlaceholder")}
              </p>
            </div>
            <div className="rounded-xl border border-white/[0.06] bg-white/[0.03] p-3">
              <p className="text-xs text-gray-500">{t("pptV7.targetSlides")}</p>
              <p className="mt-1 text-sm text-gray-200">{state.slideCount}</p>
            </div>
          </div>
        </div>

        <div className="rounded-2xl border border-white/[0.06] bg-white/[0.02] p-5">
          <h4 className="text-sm font-semibold text-gray-200">{t("pptV7.progress")}</h4>
          <div className="mt-3 grid grid-cols-1 gap-2 md:grid-cols-4">
            {steps.map((step, idx) => {
              const order = idx + 1;
              const done = currentOrder > order;
              const active = currentOrder === order && state.busy;
              return (
                <div
                  key={step.key}
                  className={`rounded-xl border px-3 py-2 text-xs ${
                    done
                      ? 'border-emerald-500/25 bg-emerald-500/[0.08] text-emerald-300'
                      : active
                        ? 'border-[#E11D48]/30 bg-[#E11D48]/10 text-[#E11D48]'
                        : 'border-white/[0.08] bg-white/[0.03] text-gray-400'
                  }`}
                >
                  <div className="font-medium">{step.label}</div>
                  <div className="mt-1 text-[11px]">
                    {done ? t("pptV7.done") : active ? t("pptV7.running") : t("pptV7.waiting")}
                  </div>
                </div>
              );
            })}
          </div>

          {state.error && (
            <div className="mt-4 rounded-xl border border-red-500/20 bg-red-500/[0.08] px-3 py-2 text-sm text-red-300">
              <div className="flex items-center gap-2">
                <AlertTriangle className="h-4 w-4" />
                <span>{state.error}</span>
              </div>
            </div>
          )}
        </div>

        {state.result && (
          <div className="rounded-2xl border border-white/[0.06] bg-white/[0.02] p-5">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h4 className="text-sm font-semibold text-gray-200">{t("pptV7.latestResult")}</h4>
                <p className="mt-1 text-xs text-gray-500">
                  {t("pptV7.resultSummary", {
                    runId: state.result.run_id,
                    slideCount: state.result.slide_count,
                  })}
                </p>
              </div>
              <a
                href={state.result.pptx_url}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-[#E11D48] to-[#9333EA] px-4 py-2 text-sm font-medium text-white transition hover:from-[#F43F5E] hover:to-[#A855F7]"
              >
                <FileDown className="h-4 w-4" />
                {t("pptV7.downloadPptx")}
              </a>
            </div>

            {state.result.slide_image_urls?.length > 0 && (
              <div className="mt-4">
                <p className="mb-2 text-xs text-gray-500">{t("pptV7.slidePreviews")}</p>
                <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
                  {state.result.slide_image_urls.slice(0, 8).map((url, idx) => (
                    <div key={`${url}-${idx}`} className="overflow-hidden rounded-lg border border-white/[0.08] bg-white/[0.03]">
                      <img src={url} alt={`Slide ${idx + 1}`} className="h-24 w-full object-cover" />
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        <div className="rounded-2xl border border-white/[0.06] bg-white/[0.02] p-5">
          <h4 className="text-sm font-semibold text-gray-200">{t("pptV7.recentRuns")}</h4>
          <div className="mt-3 space-y-2">
            {history.length === 0 ? (
              <p className="text-xs text-gray-500">{t("pptV7.noHistory")}</p>
            ) : (
              history.map((item) => (
                <div key={item.id} className="flex items-center justify-between gap-3 rounded-xl border border-white/[0.08] bg-white/[0.03] px-3 py-2">
                  <div className="min-w-0">
                    <p className="truncate text-xs font-medium text-gray-200">{item.runId}</p>
                    <p className="truncate text-[11px] text-gray-500">{item.requirement || '-'}</p>
                    <p className="text-[11px] text-gray-500">{item.slideCount} slides · {new Date(item.createdAt).toLocaleString()}</p>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    <span
                      className={`rounded-full px-2 py-0.5 text-[10px] ${
                        item.status === 'success'
                          ? 'border border-emerald-500/25 bg-emerald-500/10 text-emerald-300'
                          : 'border border-red-500/25 bg-red-500/10 text-red-300'
                      }`}
                    >
                      {item.status}
                    </span>
                    {item.pptxUrl && (
                      <a
                        href={item.pptxUrl}
                        target="_blank"
                        rel="noreferrer"
                        className="text-[11px] text-[#E11D48] hover:underline"
                      >
                        {t("pptV7.open")}
                      </a>
                    )}
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function ProjectWorkspace({
  initialTemplateId,
  activeRunId,
  onActiveRunChange,
}: {
  initialTemplateId?: string;
  activeRunId: string | null;
  onActiveRunChange: (runId: string | null) => void;
}) {
  const { phase, project, loadProject } = useProject();
  const t = useT();
  const [workspaceTemplateId, setWorkspaceTemplateId] = useState<string>(initialTemplateId || 'product-ad');
  const [pptV7RetryToken, setPptV7RetryToken] = useState(0);
  const [pptV7PanelState, setPptV7PanelState] = useState<PptV7PanelState>(() => ({
    ...EMPTY_PPT_V7_STATE,
    enabled: (initialTemplateId || 'product-ad') === 'ppt-v7',
  }));
  const [pptV7History, setPptV7History] = useState<PptV7HistoryItem[]>(() => loadPptV7History());

  const lastSuccessRunRef = useRef<string>('');
  const lastErrorRef = useRef<string>('');

  useEffect(() => {
    if (!activeRunId) {
      return;
    }
    void loadProject(activeRunId);
  }, [activeRunId, loadProject]);

  useEffect(() => {
    if (project?.run_id) {
      onActiveRunChange(project.run_id);
    }
  }, [onActiveRunChange, project?.run_id]);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    window.localStorage.setItem(PPT_V7_HISTORY_KEY, JSON.stringify(pptV7History.slice(0, 20)));
  }, [pptV7History]);

  const appendHistory = useCallback((item: PptV7HistoryItem) => {
    setPptV7History((prev) => [item, ...prev].slice(0, 20));
  }, []);

  const handlePptV7StateChange = useCallback(
    (state: PptV7PanelState) => {
      setPptV7PanelState(state);

      if (state.result?.run_id && state.result.run_id !== lastSuccessRunRef.current) {
        lastSuccessRunRef.current = state.result.run_id;
        appendHistory({
          id: `success-${state.result.run_id}`,
          status: 'success',
          runId: state.result.run_id,
          requirement: state.requirement,
          slideCount: state.result.slide_count,
          createdAt: new Date().toISOString(),
          pptxUrl: state.result.pptx_url,
        });
      }

      if (!state.error) {
        lastErrorRef.current = '';
        return;
      }

      const errorKey = `${state.requirement}:${state.error}`;
      if (errorKey === lastErrorRef.current) {
        return;
      }

      lastErrorRef.current = errorKey;
      appendHistory({
        id: `failed-${Date.now()}`,
        status: 'failed',
        runId: state.result?.run_id || 'N/A',
        requirement: state.requirement,
        slideCount: state.slideCount,
        createdAt: new Date().toISOString(),
        error: state.error,
      });
    },
    [appendHistory],
  );

  const isPptV7Mode = workspaceTemplateId === 'ppt-v7' || pptV7PanelState.enabled;
  const showStoryboard = ['generating_storyboard', 'storyboard_ready', 'generating_images', 'images_ready'].includes(phase);
  const showClips = ['generating_videos', 'stitching', 'videos_ready', 'rendering', 'completed'].includes(phase);

  return (
    <div className="flex flex-1 h-full overflow-hidden">
      <div className="w-full md:w-[380px] shrink-0 overflow-y-auto">
        <ProjectForm
          initialTemplateId={initialTemplateId}
          onTemplateChange={setWorkspaceTemplateId}
          onPptV7StateChange={handlePptV7StateChange}
          pptV7RetryToken={pptV7RetryToken}
        />
      </div>

      <div className="flex-1 hidden md:flex flex-col overflow-hidden border-l border-white/[0.06]">
        {isPptV7Mode ? (
          <div className="shrink-0 border-b border-white/[0.06] bg-black/30 px-4 py-3">
            <p className="text-sm font-semibold text-gray-200">{t("workspace.pptV7WorkspaceTitle")}</p>
            <p className="mt-0.5 text-xs text-gray-500">{t("workspace.pptV7WorkspaceDesc")}</p>
          </div>
        ) : (
          <ProgressPanel />
        )}

        <div className="flex-1 overflow-y-auto">
          {isPptV7Mode ? (
            <PptV7ResultPanel
              state={pptV7PanelState}
              history={pptV7History}
              onRetry={() => setPptV7RetryToken((n) => n + 1)}
            />
          ) : phase === 'idle' || phase === 'configuring' ? (
            <div className="flex items-center justify-center h-full">
              <div className="text-center space-y-5 max-w-xs">
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
                  <p className="text-sm font-medium text-gray-400">{t('workspace.idleTitle')}</p>
                  <p className="text-xs text-gray-600 leading-relaxed">
                    {t('workspace.idleDesc')}
                  </p>
                </div>
                <div className="flex items-center justify-center gap-6 pt-2">
                  {[
                    { step: '01', label: t('workspace.step01') },
                    { step: '02', label: t('workspace.step02') },
                    { step: '03', label: t('workspace.step03') },
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
              <div className="flex-1 overflow-y-auto p-4">
                <ClipManager />
              </div>
              <div className="shrink-0 border-t border-white/[0.06] p-4" style={{ maxHeight: '45%' }}>
                <RemotionPreview />
              </div>
            </div>
          ) : phase === 'error' ? (
            <div className="flex items-center justify-center h-full">
              <div className="text-center space-y-3">
                <div className="w-14 h-14 mx-auto rounded-2xl bg-red-500/[0.08] border border-red-500/20 flex items-center justify-center">
                  <span className="text-red-400 text-xl">!</span>
                </div>
                <p className="text-base font-medium text-red-400">{t('workspace.errorTitle')}</p>
                <p className="text-sm text-gray-500">{t('workspace.errorDesc')}</p>
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
  const userEmail = session?.user?.email || '';
  const router = useRouter();
  const searchParams = useSearchParams();
  const routeRunId = searchParams.get('runId');
  const t = useT();

  const [view, setView] = useState<ViewState>('gallery');
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [selectedTemplateId, setSelectedTemplateId] = useState<string>('product-ad');
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  const handleSelectTemplate = useCallback((templateId: string) => {
    router.replace('/');
    setSelectedTemplateId(templateId);
    setView('project');
    setActiveRunId(null);
  }, [router]);

  const handleNewProject = useCallback(() => {
    router.replace('/');
    setActiveRunId(null);
    setView('gallery');
  }, [router]);

  const handleSelectRun = useCallback((runId: string) => {
    router.replace(`/?runId=${encodeURIComponent(runId)}`);
    setActiveRunId(runId);
    setView('project');
  }, [router]);

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

  const resolvedView: ViewState = routeRunId ? 'project' : view;
  const resolvedActiveRunId = routeRunId || activeRunId;

  if (resolvedView === 'gallery') {
    return (
      <div className="flex flex-col h-screen bg-[#050508]">
        <div className="h-16 border-b border-white/[0.06] flex items-center px-4 md:px-8 justify-between bg-black/40 backdrop-blur-xl relative z-20">
          <div className="flex items-center gap-2.5 group cursor-pointer">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-[#E11D48] to-[#9333EA] flex items-center justify-center shadow-lg shadow-[#E11D48]/30 group-hover:shadow-[#E11D48]/50 transition-all duration-300">
              <Play className="w-3.5 h-3.5 text-white fill-white ml-px" />
            </div>
            <span className="font-bold tracking-tight bg-gradient-to-r from-white to-gray-300 bg-clip-text text-transparent">AutoViralVid</span>
            <div className="hidden sm:flex items-center gap-2 ml-3">
              <span className="px-2 py-0.5 rounded-full bg-[#E11D48]/10 border border-[#E11D48]/20 text-[10px] text-[#E11D48] font-medium">{t("home.aiPowered")}</span>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <Link
              href="/projects"
              className="hidden rounded-xl border border-white/[0.08] bg-white/[0.03] px-3 py-2 text-sm text-gray-300 transition-colors hover:bg-white/[0.06] md:inline-flex"
            >
              {t("home.historyLink")}
            </Link>
            <LanguageSwitcher />
            <div className="text-sm text-gray-400 hidden sm:flex items-center gap-2">
              <div className="w-7 h-7 rounded-full bg-gradient-to-br from-[#E11D48] to-purple-600 flex items-center justify-center text-xs font-bold">
                {userEmail?.[0]?.toUpperCase() || t("home.userFallback").slice(0, 1)}
              </div>
              <span className="max-w-[120px] truncate">{userEmail?.split('@')[0] || t("home.userFallback")}</span>
            </div>
          </div>
        </div>
        <TemplateGallery onSelect={handleSelectTemplate} />
      </div>
    );
  }

  return (
    <ProjectProvider>
      <div className="flex flex-col md:flex-row h-screen w-full bg-[#050508] overflow-hidden font-sans text-gray-100">
        <Sidebar
          activeRunId={resolvedActiveRunId}
          onSelectRun={handleSelectRun}
          onNewProject={handleNewProject}
          onBack={() => setView('gallery')}
          userEmail={userEmail}
          isCollapsed={sidebarCollapsed}
          toggleCollapse={() => setSidebarCollapsed(!sidebarCollapsed)}
          onToggleGuide={() => {}}
          className="hidden md:flex shrink-0 z-20"
        />

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

        <ProjectWorkspace
          initialTemplateId={selectedTemplateId}
          activeRunId={resolvedActiveRunId}
          onActiveRunChange={setActiveRunId}
        />

        <AIAssistant />
      </div>
    </ProjectProvider>
  );
}

export default function Home() {
  return (
    <SessionProvider>
      <Suspense
        fallback={
          <div className="flex items-center justify-center h-screen bg-[#060610]">
            <div className="w-8 h-8 border-2 border-[#E11D48] border-t-transparent rounded-full animate-spin" />
          </div>
        }
      >
        <HomeContent />
      </Suspense>
    </SessionProvider>
  );
}
