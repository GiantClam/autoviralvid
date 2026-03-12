import React, { useCallback, useEffect, useState } from 'react';
import { Plus, MessageSquare, ArrowLeft, PanelLeftClose, PanelLeftOpen, HelpCircle, Play, LogOut, RefreshCw, CheckCircle2, Loader2, Clock3, AlertCircle } from 'lucide-react';
import { projectApi, type Project } from '@/lib/project-client';
import { useT } from '@/lib/i18n';
import LanguageSwitcher from './LanguageSwitcher';
import QuotaBar from './QuotaBar';

interface SidebarProps {
    activeRunId: string | null;
    onSelectRun: (runId: string) => void;
    onNewProject: () => void;
    onBack: () => void;
    onLogout?: () => void;
    userEmail?: string;
    className?: string;
    isCollapsed?: boolean;
    toggleCollapse?: () => void;
    onToggleGuide?: () => void;
}

export function Sidebar({
    activeRunId,
    onSelectRun,
    onNewProject,
    onBack,
    onLogout,
    userEmail = "User",
    className = '',
    isCollapsed = false,
    toggleCollapse,
    onToggleGuide
}: SidebarProps) {
    const t = useT();
    const [history, setHistory] = useState<Project[]>([]);
    const [loading, setLoading] = useState(false);
    const [showUserMenu, setShowUserMenu] = useState(false);

    const loadHistory = useCallback(async () => {
        setLoading(true);
        try {
            const data = await projectApi.list(30);
            setHistory(data.projects || []);
        } catch (err) {
            console.error("Failed to load project history", err);
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        let cancelled = false;
        let intervalId: ReturnType<typeof setInterval> | null = null;

        async function refreshHistory() {
            if (cancelled) {
                return;
            }
            try {
                const data = await projectApi.list(30);
                if (!cancelled) {
                    setHistory(data.projects || []);
                }
            } catch (err) {
                if (!cancelled) {
                    console.error("Failed to load project history", err);
                }
            } finally {
                if (!cancelled) {
                    setLoading(false);
                }
            }
        }

        setLoading(true);
        void refreshHistory();
        intervalId = setInterval(() => {
            void refreshHistory();
        }, 15000);

        return () => {
            cancelled = true;
            if (intervalId) {
                clearInterval(intervalId);
            }
        };
    }, [userEmail, activeRunId]);

    const getHistoryLabel = (run: Project) => {
        if (typeof run.theme === "string" && run.theme.trim()) {
            return run.theme;
        }
        if (typeof run.slogan === "string" && run.slogan.trim()) {
            return run.slogan;
        }
        return run.run_id.slice(0, 12);
    };

    const getStatusBadge = (run: Project) => {
        const taskSummary = run.task_summary;
        if (run.video_url || run.final_video_url || run.result_video_url) {
            return {
                label: 'Ready',
                icon: CheckCircle2,
                className: 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20',
            };
        }

        if (taskSummary?.total) {
            const running = (taskSummary.processing ?? 0) + (taskSummary.submitted ?? 0);
            const queued = (taskSummary.pending ?? 0) + (taskSummary.queued ?? 0);
            if (taskSummary.failed > 0) {
                return {
                    label: `Failed ${taskSummary.failed}`,
                    icon: AlertCircle,
                    className: 'text-red-400 bg-red-500/10 border-red-500/20',
                };
            }
            if (running > 0 || queued > 0) {
                return {
                    label: `${taskSummary.succeeded}/${taskSummary.total}`,
                    icon: Loader2,
                    className: 'text-amber-400 bg-amber-500/10 border-amber-500/20',
                };
            }
        }

        if (run.status === 'completed') {
            return {
                label: 'Completed',
                icon: CheckCircle2,
                className: 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20',
            };
        }

        return {
            label: run.status || 'Pending',
            icon: Clock3,
            className: 'text-gray-400 bg-white/[0.04] border-white/[0.08]',
        };
    };

    return (
        <div className={`flex flex-col h-full bg-[#0a0a12]/80 backdrop-blur-xl border-r border-white/[0.06] transition-all duration-300 ${isCollapsed ? 'w-[80px]' : 'w-[280px]'} ${className}`}>
            {/* Brand header */}
            <div className={`p-4 flex items-center justify-between border-b border-white/[0.06] ${isCollapsed ? 'flex-col gap-4' : ''}`}>
                <div className="flex items-center gap-2.5">
                    <button
                        onClick={onBack}
                        className="p-2 hover:bg-white/5 rounded-xl text-gray-400 hover:text-[#E11D48] transition-all duration-200 cursor-pointer group"
                        title={t("sidebar.backToTemplates")}
                    >
                        <ArrowLeft size={18} className="group-hover:-translate-x-0.5 transition-transform" />
                    </button>
                    {!isCollapsed && (
                        <div className="flex items-center gap-2">
                            <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-[#E11D48] to-[#9333EA] flex items-center justify-center shadow-lg shadow-[#E11D48]/20">
                                <Play className="w-3 h-3 text-white fill-white ml-px" />
                            </div>
                            <span className="text-sm font-bold text-gray-200 bg-gradient-to-r from-white to-gray-300 bg-clip-text text-transparent">AutoViralVid</span>
                        </div>
                    )}
                </div>

                <button
                    onClick={toggleCollapse}
                    className="p-2 hover:bg-white/5 rounded-xl text-gray-400 hover:text-white transition-all duration-200 cursor-pointer"
                >
                    {isCollapsed ? <PanelLeftOpen size={18} /> : <PanelLeftClose size={18} />}
                </button>
            </div>

            {/* New project button */}
            <div className="p-4">
                <button
                    onClick={onNewProject}
                    className={`flex items-center gap-2 w-full px-4 py-3 rounded-xl bg-gradient-to-r from-[#E11D48]/10 to-purple-500/10 border border-[#E11D48]/20 hover:from-[#E11D48]/20 hover:to-purple-500/20 hover:border-[#E11D48]/40 text-[#E11D48] transition-all duration-300 text-sm font-semibold cursor-pointer group ${isCollapsed ? 'justify-center px-0' : ''}`}
                >
                    <Plus size={18} className="group-hover:rotate-90 transition-transform duration-300" />
                    {!isCollapsed && <span>{t("sidebar.newProject")}</span>}
                </button>
            </div>

            {/* History list */}
            <div className="flex-1 overflow-y-auto px-2 py-2 space-y-1">
                {!isCollapsed && (
                    <div className="px-3 py-2 text-[10px] font-bold text-gray-500 uppercase tracking-widest flex items-center justify-between gap-2">
                        <span className="flex items-center gap-2">
                            <MessageSquare size={10} />
                            {t("sidebar.historyProjects")}
                        </span>
                        <button
                            type="button"
                            onClick={() => void loadHistory()}
                            className="p-1 rounded-md text-gray-500 hover:text-gray-200 hover:bg-white/[0.04] transition-colors cursor-pointer"
                            title={t("common.retry")}
                        >
                            <RefreshCw size={12} />
                        </button>
                    </div>
                )}

                {history.map((run, index) => (
                    <button
                        key={run.run_id}
                        onClick={() => onSelectRun(run.run_id)}
                        className={`
                            flex items-center gap-3 w-full p-3 rounded-xl transition-all duration-300 group cursor-pointer relative overflow-hidden
                            ${activeRunId === run.run_id
                                ? 'bg-gradient-to-r from-[#E11D48]/15 to-purple-500/10 text-white border border-[#E11D48]/20'
                                : 'text-gray-400 hover:bg-white/[0.03] hover:text-gray-200 border border-transparent'}
                            ${isCollapsed ? 'justify-center px-0' : ''}
                        `}
                        style={{ animationDelay: `${index * 0.05}s` }}
                    >
                        {activeRunId === run.run_id && (
                            <div className="absolute left-0 top-1/2 -translate-y-1/2 w-1 h-6 bg-gradient-to-b from-[#E11D48] to-purple-500 rounded-r-full" />
                        )}
                        <MessageSquare size={16} className={activeRunId === run.run_id ? 'text-[#E11D48]' : 'text-gray-500 group-hover:text-gray-300 transition-colors'} />
                        {!isCollapsed && (
                            <div className="flex-1 min-w-0 text-left">
                                <div className="truncate text-sm">
                                    {getHistoryLabel(run)}
                                </div>
                                <div className="mt-1 flex items-center gap-2">
                                    {(() => {
                                        const badge = getStatusBadge(run);
                                        const Icon = badge.icon;
                                        return (
                                            <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] ${badge.className}`}>
                                                <Icon size={10} className={badge.icon === Loader2 ? 'animate-spin' : ''} />
                                                {badge.label}
                                            </span>
                                        );
                                    })()}
                                    {run.task_summary?.total ? (
                                        <span className="text-[10px] text-gray-500">
                                            {run.task_summary.succeeded}/{run.task_summary.total}
                                        </span>
                                    ) : null}
                                </div>
                            </div>
                        )}
                    </button>
                ))}

                {loading && !isCollapsed && (
                    <div className="p-4 text-center text-xs text-gray-500">
                        <div className="w-4 h-4 border-2 border-[#E11D48]/30 border-t-[#E11D48] rounded-full animate-spin mx-auto" />
                    </div>
                )}

                {!loading && history.length === 0 && !isCollapsed && (
                    <div className="p-8 text-center">
                        <div className="w-12 h-12 rounded-xl bg-white/[0.03] border border-white/[0.06] flex items-center justify-center mx-auto mb-3">
                            <MessageSquare size={20} className="text-gray-600" />
                        </div>
                        <p className="text-xs text-gray-500">{t("sidebar.noHistory")}</p>
                    </div>
                )}
            </div>

            {/* Bottom section */}
            <div className="p-4 border-t border-white/[0.06] relative space-y-3">
                {/* Quota usage */}
                {!isCollapsed && <QuotaBar />}

                {/* Language switcher */}
                {!isCollapsed && <LanguageSwitcher className="w-full" />}

                <div>
                    <button
                        onClick={onToggleGuide}
                        className={`flex items-center gap-3 w-full px-3 py-2.5 relative group rounded-xl text-gray-400 hover:text-white hover:bg-white/[0.03] transition-all duration-200 text-sm cursor-pointer ${isCollapsed ? 'justify-center px-0' : ''}`}
                    >
                        <HelpCircle size={18} className="group-hover:text-[#E11D48] transition-colors" />
                        {!isCollapsed && <span>{t("sidebar.guide")}</span>}
                    </button>
                </div>

                <div
                    className={`flex items-center gap-3 w-full hover:bg-white/[0.03] p-2 rounded-xl transition-all duration-200 cursor-pointer group ${isCollapsed ? 'justify-center px-0' : ''}`}
                    onClick={() => setShowUserMenu(!showUserMenu)}
                >
                    <div className="w-9 h-9 shrink-0 rounded-xl bg-gradient-to-br from-[#E11D48] to-[#9333EA] flex items-center justify-center text-white text-sm font-bold shadow-lg shadow-[#E11D48]/20 group-hover:shadow-[#E11D48]/40 transition-all">
                        {(userEmail || "U")[0].toUpperCase()}
                    </div>

                    {!isCollapsed && (
                        <div className="flex-1 min-w-0 text-left">
                            <div className="text-sm font-semibold text-gray-200 truncate">{(userEmail || "User").split('@')[0]}</div>
                            <div className="text-[10px] text-gray-500 truncate">{userEmail || "Dev Mode"}</div>
                        </div>
                    )}
                </div>

                {/* User menu popup */}
                {showUserMenu && !isCollapsed && onLogout && (
                    <div className="absolute bottom-full left-4 right-4 mb-2 bg-[#0c0c18]/95 backdrop-blur-xl border border-white/[0.08] rounded-xl shadow-2xl overflow-hidden animate-fade-in-up">
                        <button
                            onClick={() => { onLogout(); setShowUserMenu(false); }}
                            className="flex items-center gap-3 w-full px-4 py-3 text-sm text-gray-400 hover:text-[#E11D48] hover:bg-[#E11D48]/5 transition-all duration-200 cursor-pointer"
                        >
                            <LogOut size={16} />
                            <span>{t("sidebar.signOut")}</span>
                        </button>
                    </div>
                )}
            </div>
        </div>
    );
}
