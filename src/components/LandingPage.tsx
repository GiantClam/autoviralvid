"use client";

import React, { useState, useEffect } from 'react';
import {
    Play, ArrowRight, Menu, X, Sparkles,
    Layers, Zap, MonitorPlay, UserCircle,
    Film, Wand2, Mic2, ChevronRight,
    Star, TrendingUp, Users, Clock,
} from 'lucide-react';
import { signIn } from 'next-auth/react';
import { registerUser } from '@/lib/actions';
import { useT } from '@/lib/i18n';
import LanguageSwitcher from './LanguageSwitcher';

const LandingPage: React.FC = () => {
    const t = useT();
    const [isModalOpen, setIsModalOpen] = useState(false);
    const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [isSignUpMode, setIsSignUpMode] = useState(false);
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState('');
    const [mousePosition, setMousePosition] = useState({ x: 0, y: 0 });

    useEffect(() => {
        const handleMouseMove = (e: MouseEvent) => {
            setMousePosition({ x: e.clientX, y: e.clientY });
        };
        window.addEventListener('mousemove', handleMouseMove);
        return () => window.removeEventListener('mousemove', handleMouseMove);
    }, []);

    const FEATURES = [
        { icon: Layers, title: t("landing.featMultiAgent"), desc: t("landing.featMultiAgentDesc"), color: "from-orange-500 to-rose-500" },
        { icon: Zap, title: t("landing.featOneClick"), desc: t("landing.featOneClickDesc"), color: "from-yellow-500 to-amber-500" },
        { icon: MonitorPlay, title: t("landing.featRealtime"), desc: t("landing.featRealtimeDesc"), color: "from-blue-500 to-cyan-500" },
        { icon: UserCircle, title: t("landing.featDigitalHuman"), desc: t("landing.featDigitalHumanDesc"), color: "from-purple-500 to-violet-500" },
    ];

    const SHOWCASE = [
        { title: t("landing.showcaseEcommerce"), tag: t("landing.showcaseTagHot"), gradient: "from-orange-500 to-rose-600", icon: TrendingUp },
        { title: t("landing.showcaseBrand"), tag: t("landing.showcaseTagPro"), gradient: "from-violet-500 to-purple-600", icon: Star },
        { title: t("landing.showcaseKnowledge"), tag: t("landing.showcaseTagEdu"), gradient: "from-cyan-500 to-blue-600", icon: Users },
    ];

    const STATS = [
        { value: "10K+", label: "Active Users" },
        { value: "1M+", label: "Videos Created" },
        { value: "50+", label: "Templates" },
        { value: "<30s", label: "Generation Time" },
    ];

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setError('');
        setIsLoading(true);

        try {
            if (isSignUpMode) {
                const result = await registerUser(email, password);
                if (result.error) {
                    setError(result.error);
                    setIsLoading(false);
                    return;
                }
            }

            const res = await signIn('credentials', {
                email,
                password,
                redirect: false,
            });

            if (res?.error) {
                setError(isSignUpMode ? t("landing.authSignUpSuccessLoginFailed") : t("landing.authInvalidCredentials"));
            } else {
                setIsModalOpen(false);
            }
        } catch {
            setError(t("landing.authUnexpectedError"));
        } finally {
            setIsLoading(false);
        }
    };

    const handleGoogleLogin = () => {
        signIn('google', { callbackUrl: '/' });
    };

    const scrollToSection = (id: string) => {
        setIsMobileMenuOpen(false);
        document.getElementById(id)?.scrollIntoView({ behavior: 'smooth' });
    };

    return (
        <div className="min-h-screen bg-[#050508] text-white selection:bg-[#E11D48]/30 overflow-x-hidden">
            {/* Animated background mesh */}
            <div className="fixed inset-0 bg-mesh-gradient pointer-events-none" />
            
            {/* Floating orbs */}
            <div className="fixed top-1/4 left-1/4 w-96 h-96 bg-[#E11D48]/10 rounded-full blur-[100px] animate-float pointer-events-none" />
            <div className="fixed bottom-1/4 right-1/4 w-80 h-80 bg-purple-500/10 rounded-full blur-[80px] animate-float-delayed pointer-events-none" />
            <div className="fixed top-1/2 right-1/3 w-64 h-64 bg-blue-500/10 rounded-full blur-[60px] animate-float pointer-events-none" style={{ animationDelay: '2s' }} />
            
            {/* Interactive spotlight following mouse */}
            <div 
                className="fixed w-[600px] h-[600px] pointer-events-none transition-all duration-1000 ease-out"
                style={{
                    left: mousePosition.x - 300,
                    top: mousePosition.y - 300,
                    background: 'radial-gradient(circle, rgba(225, 29, 72, 0.06) 0%, transparent 70%)',
                }}
            />

            {/* ── Floating Glassmorphism Navbar ── */}
            <nav className="fixed top-4 left-4 right-4 z-50 rounded-2xl border border-white/[0.08] bg-black/40 backdrop-blur-xl shadow-2xl shadow-black/20">
                <div className="max-w-7xl mx-auto px-4 md:px-6 h-16 flex items-center justify-between">
                    <div className="flex items-center gap-2.5 cursor-pointer group">
                        <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-[#E11D48] to-[#9333EA] flex items-center justify-center shadow-lg shadow-[#E11D48]/30 group-hover:shadow-[#E11D48]/50 transition-all duration-300 relative overflow-hidden">
                            <div className="absolute inset-0 bg-gradient-to-br from-white/20 to-transparent opacity-0 group-hover:opacity-100 transition-opacity" />
                            <Play className="w-3.5 h-3.5 text-white fill-white ml-0.5 relative z-10" />
                        </div>
                        <span className="font-bold text-lg tracking-tight bg-gradient-to-r from-white to-gray-300 bg-clip-text text-transparent">AutoViralVid</span>
                    </div>

                    <div className="hidden md:flex items-center gap-6 text-sm font-medium text-gray-400">
                        <button onClick={() => scrollToSection('features')} className="hover:text-white transition-colors cursor-pointer underline-animated">{t("nav.features")}</button>
                        <button onClick={() => scrollToSection('showcase')} className="hover:text-white transition-colors cursor-pointer underline-animated">{t("nav.showcase")}</button>
                        <LanguageSwitcher />
                        <button
                            onClick={() => setIsModalOpen(true)}
                            className="px-5 py-2.5 bg-gradient-to-r from-[#E11D48] to-[#BE123C] text-white rounded-full hover:shadow-[0_0_30px_rgba(225,29,72,0.4)] transition-all cursor-pointer font-semibold text-sm relative overflow-hidden group"
                        >
                            <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/20 to-transparent translate-x-[-100%] group-hover:translate-x-[100%] transition-transform duration-700" />
                            <span className="relative">{t("nav.getAccess")}</span>
                        </button>
                    </div>

                    <button className="md:hidden text-white cursor-pointer" onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}>
                        {isMobileMenuOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
                    </button>
                </div>

                {isMobileMenuOpen && (
                    <div className="md:hidden border-t border-white/[0.08] px-6 py-4 space-y-3 bg-black/60 backdrop-blur-xl rounded-b-2xl">
                        <button onClick={() => scrollToSection('features')} className="block text-sm text-gray-400 hover:text-white transition-colors cursor-pointer">{t("nav.features")}</button>
                        <button onClick={() => scrollToSection('showcase')} className="block text-sm text-gray-400 hover:text-white transition-colors cursor-pointer">{t("nav.showcase")}</button>
                        <LanguageSwitcher className="w-full justify-center" />
                        <button onClick={() => { setIsModalOpen(true); setIsMobileMenuOpen(false); }} className="w-full px-5 py-2.5 bg-gradient-to-r from-[#E11D48] to-[#BE123C] text-white rounded-full font-semibold text-sm">{t("nav.getAccess")}</button>
                    </div>
                )}
            </nav>

            {/* ── Hero Section ── */}
            <main className="pt-32 pb-16 px-6 relative">
                <div className="max-w-6xl mx-auto text-center relative z-10">
                    {/* Animated badge */}
                    <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-gradient-to-r from-[#E11D48]/10 to-purple-500/10 border border-[#E11D48]/20 mb-8 animate-fade-in-up">
                        <Sparkles className="w-4 h-4 text-[#E11D48] animate-pulse" />
                        <span className="text-sm font-medium bg-gradient-to-r from-[#E11D48] to-purple-400 bg-clip-text text-transparent">{t("landing.badge")}</span>
                        <ChevronRight className="w-4 h-4 text-[#E11D48]/60" />
                    </div>

                    {/* Main headline with gradient animation */}
                    <h1 className="text-5xl sm:text-6xl md:text-7xl lg:text-8xl font-extrabold tracking-tight mb-8 leading-[1.05] animate-fade-in-up" style={{ animationDelay: '0.1s' }}>
                        <span className="block text-white">{t("landing.heroTitle1")}</span>
                        <span className="block mt-2 text-gradient-shimmer">{t("landing.heroTitle2")}</span>
                        <span className="block mt-2 text-[#E11D48]">{t("landing.heroHighlight")}</span>
                    </h1>

                    <p className="text-lg sm:text-xl md:text-2xl text-gray-400 mb-12 max-w-3xl mx-auto leading-relaxed animate-fade-in-up" style={{ animationDelay: '0.2s' }}>
                        {t("landing.heroDesc")}
                    </p>

                    {/* CTA Buttons */}
                    <div className="flex flex-col sm:flex-row items-center justify-center gap-4 mb-16 animate-fade-in-up" style={{ animationDelay: '0.3s' }}>
                        <button
                            onClick={() => setIsModalOpen(true)}
                            className="group relative px-8 py-4 bg-gradient-to-r from-[#E11D48] to-[#BE123C] text-white rounded-full font-bold text-lg transition-all cursor-pointer overflow-hidden shadow-[0_0_40px_rgba(225,29,72,0.4)] hover:shadow-[0_0_60px_rgba(225,29,72,0.6)] hover:scale-105"
                        >
                            <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/30 to-transparent translate-x-[-100%] group-hover:translate-x-[100%] transition-transform duration-700" />
                            <span className="relative flex items-center gap-2.5">
                                <Play className="w-5 h-5 fill-white" />
                                {t("landing.startFree")}
                                <ArrowRight className="w-5 h-5 group-hover:translate-x-1 transition-transform" />
                            </span>
                        </button>
                        
                        <button
                            onClick={() => scrollToSection('showcase')}
                            className="group px-8 py-4 bg-white/[0.03] border border-white/[0.1] text-white rounded-full font-semibold text-lg hover:bg-white/[0.08] hover:border-white/[0.2] transition-all cursor-pointer flex items-center gap-2"
                        >
                            <Film className="w-5 h-5" />
                            View Examples
                            <ChevronRight className="w-4 h-4 group-hover:translate-x-1 transition-transform" />
                        </button>
                    </div>

                    {/* Stats */}
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-6 max-w-3xl mx-auto animate-fade-in-up" style={{ animationDelay: '0.4s' }}>
                        {STATS.map((stat, i) => (
                            <div key={i} className="text-center p-4 rounded-2xl bg-white/[0.02] border border-white/[0.05]">
                                <div className="text-2xl md:text-3xl font-bold text-gradient-primary">{stat.value}</div>
                                <div className="text-sm text-gray-500 mt-1">{stat.label}</div>
                            </div>
                        ))}
                    </div>
                </div>
            </main>

            {/* ── Features Section ── */}
            <section id="features" className="py-24 px-6 relative">
                <div className="max-w-6xl mx-auto">
                    <div className="text-center mb-16">
                        <h2 className="text-4xl md:text-5xl font-bold tracking-tight mb-4">
                            {t("landing.featSectionTitle").split(' ').map((word, i, arr) =>
                                i === arr.length - 1 ? <span key={i} className="text-gradient-primary">{word}</span> : word + ' '
                            )}
                        </h2>
                        <p className="text-gray-400 text-lg max-w-xl mx-auto">
                            {t("landing.featSectionDesc")}
                        </p>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                        {FEATURES.map((f, i) => (
                            <div
                                key={f.title}
                                className="group relative rounded-3xl border border-white/[0.06] bg-gradient-to-br from-white/[0.03] to-transparent p-8 transition-all duration-500 hover:border-[#E11D48]/30 hover:bg-white/[0.05] cursor-default overflow-hidden card-hover-lift"
                                style={{ animationDelay: `${i * 0.1}s` }}
                            >
                                {/* Gradient glow on hover */}
                                <div className={`absolute inset-0 bg-gradient-to-br ${f.color} opacity-0 group-hover:opacity-5 transition-opacity duration-500`} />
                                
                                {/* Animated border */}
                                <div className="absolute inset-0 rounded-3xl opacity-0 group-hover:opacity-100 transition-opacity duration-500">
                                    <div className="absolute inset-[-1px] rounded-3xl bg-gradient-to-r from-[#E11D48]/50 via-purple-500/50 to-[#E11D48]/50 animate-gradient-shift" style={{ backgroundSize: '200% 100%' }} />
                                    <div className="absolute inset-[1px] rounded-3xl bg-[#0a0a12]" />
                                </div>
                                
                                <div className="relative z-10">
                                    <div className={`w-14 h-14 rounded-2xl bg-gradient-to-br ${f.color} flex items-center justify-center mb-6 shadow-lg group-hover:scale-110 transition-transform duration-300`}>
                                        <f.icon className="w-6 h-6 text-white" />
                                    </div>
                                    <h3 className="text-xl font-bold mb-3 group-hover:text-white transition-colors">{f.title}</h3>
                                    <p className="text-gray-400 leading-relaxed group-hover:text-gray-300 transition-colors">{f.desc}</p>
                                </div>
                                
                                {/* Shimmer effect */}
                                <div className="absolute inset-0 translate-x-[-100%] group-hover:translate-x-[100%] transition-transform duration-1000 bg-gradient-to-r from-transparent via-white/5 to-transparent" />
                            </div>
                        ))}
                    </div>
                </div>
            </section>

            {/* ── Showcase Section ── */}
            <section id="showcase" className="py-24 px-6 relative">
                <div className="max-w-6xl mx-auto">
                    <div className="text-center mb-16">
                        <h2 className="text-4xl md:text-5xl font-bold tracking-tight mb-4">
                            {t("landing.showcaseSectionTitle")}
                        </h2>
                        <p className="text-gray-400 text-lg max-w-xl mx-auto">
                            {t("landing.showcaseSectionDesc")}
                        </p>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                        {SHOWCASE.map((s, i) => (
                            <div
                                key={s.title}
                                className="group relative rounded-3xl border border-white/[0.06] bg-gradient-to-br from-white/[0.02] to-transparent p-8 transition-all duration-500 hover:border-white/[0.15] hover:scale-[1.02] cursor-pointer overflow-hidden card-hover-glow"
                                style={{ animationDelay: `${i * 0.1}s` }}
                            >
                                {/* Animated gradient background */}
                                <div className={`absolute inset-0 bg-gradient-to-br ${s.gradient} opacity-0 group-hover:opacity-10 transition-opacity duration-500`} />
                                
                                {/* Mesh overlay */}
                                <div className="absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity duration-500">
                                    <div className="absolute inset-0 bg-gradient-to-br from-white/5 to-transparent" />
                                </div>
                                
                                <div className="relative z-10">
                                    <div className="flex items-center justify-between mb-16">
                                        <div className={`w-12 h-12 rounded-2xl bg-gradient-to-br ${s.gradient} flex items-center justify-center opacity-60 group-hover:opacity-100 transition-opacity`}>
                                            <s.icon className="w-6 h-6 text-white" />
                                        </div>
                                        <span className={`text-xs px-3 py-1 rounded-full bg-gradient-to-r ${s.gradient} text-white font-medium shadow-lg`}>
                                            {s.tag}
                                        </span>
                                    </div>
                                    
                                    <div className="absolute bottom-8 left-8 right-8">
                                        <h3 className="text-xl font-bold mb-2 group-hover:text-white transition-colors">{s.title}</h3>
                                        <div className="flex items-center gap-2 text-gray-500 group-hover:text-gray-400 transition-colors">
                                            <Clock className="w-4 h-4" />
                                            <span className="text-sm">{t("landing.showcaseAutoGenerated")}</span>
                                        </div>
                                    </div>
                                </div>
                                
                                {/* Play button on hover */}
                                <div className="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity duration-300">
                                    <div className="w-16 h-16 rounded-full bg-white/10 backdrop-blur-sm border border-white/20 flex items-center justify-center">
                                        <Play className="w-6 h-6 text-white fill-white ml-1" />
                                    </div>
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            </section>

            {/* ── Bottom CTA ── */}
            <section className="py-24 px-6 relative">
                <div className="max-w-4xl mx-auto text-center">
                    <div className="rounded-[32px] border border-white/[0.06] bg-gradient-to-br from-[#0a0a1a] to-black p-12 md:p-20 relative overflow-hidden">
                        {/* Animated gradient orbs */}
                        <div className="absolute top-0 left-1/4 w-64 h-64 bg-[#E11D48]/20 rounded-full blur-[80px] animate-float pointer-events-none" />
                        <div className="absolute bottom-0 right-1/4 w-48 h-48 bg-purple-500/20 rounded-full blur-[60px] animate-float-delayed pointer-events-none" />
                        
                        {/* Grid pattern */}
                        <div className="absolute inset-0 opacity-[0.03]" style={{ backgroundImage: 'linear-gradient(rgba(255,255,255,0.1) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.1) 1px, transparent 1px)', backgroundSize: '40px 40px' }} />
                        
                        <div className="relative z-10">
                            <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-[#E11D48] to-purple-600 flex items-center justify-center mx-auto mb-8 shadow-lg shadow-[#E11D48]/30 animate-pulse-glow">
                                <Wand2 className="w-8 h-8 text-white" />
                            </div>
                            <h2 className="text-4xl md:text-5xl font-bold tracking-tight mb-6">
                                {t("landing.ctaTitle")}
                            </h2>
                            <p className="text-gray-400 text-lg mb-10 max-w-lg mx-auto leading-relaxed">
                                {t("landing.ctaDesc")}
                            </p>
                            <button
                                onClick={() => setIsModalOpen(true)}
                                className="group relative px-10 py-5 bg-gradient-to-r from-[#E11D48] to-[#BE123C] text-white rounded-full font-bold text-lg transition-all cursor-pointer overflow-hidden shadow-[0_0_50px_rgba(225,29,72,0.4)] hover:shadow-[0_0_70px_rgba(225,29,72,0.6)] hover:scale-105"
                            >
                                <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/30 to-transparent translate-x-[-100%] group-hover:translate-x-[100%] transition-transform duration-700" />
                                <span className="relative flex items-center gap-3">
                                    <Mic2 className="w-5 h-5" />
                                    {t("landing.ctaButton")}
                                    <ArrowRight className="w-5 h-5 group-hover:translate-x-1 transition-transform" />
                                </span>
                            </button>
                        </div>
                    </div>
                </div>
            </section>

            {/* ── Footer ── */}
            <footer className="border-t border-white/[0.06] py-8 px-6 relative">
                <div className="max-w-6xl mx-auto flex flex-col md:flex-row items-center justify-between gap-4">
                    <div className="flex items-center gap-2">
                        <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-[#E11D48] to-[#9333EA] flex items-center justify-center shadow-lg shadow-[#E11D48]/20">
                            <Play className="w-3.5 h-3.5 text-white fill-white ml-px" />
                        </div>
                        <span className="font-bold text-gray-300">AutoViralVid</span>
                    </div>
                    <p className="text-sm text-gray-500">{t("landing.footerCopyright")}</p>
                </div>
            </footer>

            {/* ── Auth Modal ── */}
            {isModalOpen && (
                <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/80 backdrop-blur-xl animate-fade-in-up">
                    <div className="w-full max-w-md bg-gradient-to-br from-[#0a0a1a] to-[#050508] border border-white/[0.08] rounded-3xl p-8 relative shadow-2xl animate-stagger-in">
                        {/* Decorative gradient */}
                        <div className="absolute top-0 left-1/2 -translate-x-1/2 w-32 h-32 bg-[#E11D48]/20 rounded-full blur-[40px] pointer-events-none" />
                        
                        <button onClick={() => { setIsModalOpen(false); setError(''); }} className="absolute top-4 right-4 text-gray-500 hover:text-white transition-colors cursor-pointer w-8 h-8 rounded-full bg-white/5 flex items-center justify-center hover:bg-white/10">
                            <X className="w-4 h-4" />
                        </button>
                        
                        <div className="relative z-10">
                            <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-[#E11D48] to-purple-600 flex items-center justify-center mx-auto mb-6 shadow-lg shadow-[#E11D48]/30">
                                <Sparkles className="w-6 h-6 text-white" />
                            </div>
                            
                            <h3 className="text-2xl font-bold text-center mb-2">
                                {isSignUpMode ? t("landing.authCreateAccount") : t("landing.authWelcomeBack")}
                            </h3>
                            <p className="text-gray-400 text-center text-sm mb-8">
                                {isSignUpMode ? t("landing.authSignUpDesc") : t("landing.authSignInDesc")}
                            </p>

                            {error && (
                                <div className="mb-6 p-3 bg-red-500/10 border border-red-500/20 rounded-xl text-red-400 text-sm text-center">
                                    {error}
                                </div>
                            )}

                            <form onSubmit={handleSubmit} className="space-y-4">
                                <input
                                    type="email"
                                    placeholder={t("landing.authEmail")}
                                    value={email}
                                    onChange={(e) => setEmail(e.target.value)}
                                    required
                                    className="w-full bg-white/[0.03] border border-white/[0.08] rounded-xl px-4 py-3.5 text-white placeholder-gray-500 focus:outline-none focus:border-[#E11D48] focus:ring-2 focus:ring-[#E11D48]/20 transition-all"
                                />
                                <input
                                    type="password"
                                    placeholder={t("landing.authPassword")}
                                    value={password}
                                    onChange={(e) => setPassword(e.target.value)}
                                    required
                                    minLength={6}
                                    className="w-full bg-white/[0.03] border border-white/[0.08] rounded-xl px-4 py-3.5 text-white placeholder-gray-500 focus:outline-none focus:border-[#E11D48] focus:ring-2 focus:ring-[#E11D48]/20 transition-all"
                                />
                                <button
                                    type="submit"
                                    disabled={isLoading}
                                    className="w-full bg-gradient-to-r from-[#E11D48] to-[#BE123C] text-white font-bold py-3.5 rounded-xl transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2 cursor-pointer shadow-lg shadow-[#E11D48]/20 hover:shadow-[#E11D48]/40"
                                >
                                    {isLoading && <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />}
                                    {isSignUpMode ? t("landing.authSignUp") : t("landing.authSignIn")}
                                </button>
                            </form>

                            <div className="flex items-center gap-3 my-6">
                                <div className="flex-1 h-px bg-white/[0.08]" />
                                <span className="text-xs text-gray-500">{t("landing.authOrContinueWith")}</span>
                                <div className="flex-1 h-px bg-white/[0.08]" />
                            </div>

                            <button
                                type="button"
                                onClick={handleGoogleLogin}
                                className="w-full flex items-center justify-center gap-3 bg-white/[0.03] border border-white/[0.08] rounded-xl px-4 py-3.5 text-gray-300 hover:bg-white/[0.08] hover:text-white hover:border-white/[0.15] transition-all cursor-pointer"
                            >
                                <svg className="w-5 h-5" viewBox="0 0 24 24">
                                    <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 01-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z" fill="#4285F4"/>
                                    <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/>
                                    <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/>
                                    <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/>
                                </svg>
                                <span className="text-sm font-medium">{t("landing.authGoogleLogin")}</span>
                            </button>

                            <div className="mt-6 text-center">
                                <button
                                    onClick={() => { setIsSignUpMode(!isSignUpMode); setError(''); }}
                                    className="text-sm text-gray-400 hover:text-white transition-colors cursor-pointer underline-animated"
                                >
                                    {isSignUpMode ? t("landing.authSwitchToSignIn") : t("landing.authSwitchToSignUp")}
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

export default LandingPage;
