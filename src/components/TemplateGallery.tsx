"use client";

import React, { useMemo, useState } from 'react';
import {
    Sparkles, Zap, Star,
    Palette, Shirt, UtensilsCrossed, Cpu, Sofa,
    BookOpen, Laugh, Plane, Video, GraduationCap,
    ShoppingBag, Megaphone, Film, ArrowRight, Presentation,
    Wand2, Search, X,
} from 'lucide-react';
import { useT } from '@/lib/i18n';
import SocialPanel from '@/components/SocialPanel';

interface TemplateGalleryProps {
    onSelect: (templateId: string) => void;
}

export function TemplateGallery({ onSelect }: TemplateGalleryProps) {
    const t = useT();
    const [hoveredId, setHoveredId] = useState<string | null>(null);
    const [activeCategory, setActiveCategory] = useState<'all' | 'ecommerce' | 'content' | 'general'>('all');
    const [search, setSearch] = useState('');

    const templates = useMemo(() => [
        { id: 'product-ad', title: t("gallery.tplProductAd"), description: t("gallery.tplProductAdDesc"), icon: Zap, tag: t("gallery.tagHot"), tagType: 'hot' as const, gradient: 'from-orange-500 to-rose-600', category: 'ecommerce' as const },
        { id: 'beauty-review', title: t("gallery.tplBeautyReview"), description: t("gallery.tplBeautyReviewDesc"), icon: Palette, tag: t("gallery.tagEcommerce"), tagType: 'default' as const, gradient: 'from-pink-500 to-fuchsia-600', category: 'ecommerce' as const },
        { id: 'fashion-style', title: t("gallery.tplFashionStyle"), description: t("gallery.tplFashionStyleDesc"), icon: Shirt, tag: t("gallery.tagEcommerce"), tagType: 'default' as const, gradient: 'from-violet-500 to-purple-600', category: 'ecommerce' as const },
        { id: 'food-showcase', title: t("gallery.tplFoodShowcase"), description: t("gallery.tplFoodShowcaseDesc"), icon: UtensilsCrossed, tag: t("gallery.tagEcommerce"), tagType: 'default' as const, gradient: 'from-amber-500 to-orange-600', category: 'ecommerce' as const },
        { id: 'tech-unbox', title: t("gallery.tplTechUnbox"), description: t("gallery.tplTechUnboxDesc"), icon: Cpu, tag: t("gallery.tagEcommerce"), tagType: 'default' as const, gradient: 'from-cyan-500 to-blue-600', category: 'ecommerce' as const },
        { id: 'home-living', title: t("gallery.tplHomeLiving"), description: t("gallery.tplHomeLivingDesc"), icon: Sofa, tag: t("gallery.tagEcommerce"), tagType: 'default' as const, gradient: 'from-emerald-500 to-teal-600', category: 'ecommerce' as const },
        { id: 'brand-story', title: t("gallery.tplBrandStory"), description: t("gallery.tplBrandStoryDesc"), icon: Star, tag: t("gallery.tagPro"), tagType: 'pro' as const, gradient: 'from-blue-500 to-indigo-600', category: 'general' as const },
        { id: 'digital-human', title: t("gallery.tplDigitalHuman"), description: t("gallery.tplDigitalHumanDesc"), icon: Video, tag: t("gallery.tagDigitalHuman"), tagType: 'digital-human' as const, gradient: 'from-rose-500 to-purple-600', category: 'general' as const },
        { id: 'ppt-v7', title: t("gallery.tplPptV7"), description: t("gallery.tplPptV7Desc"), icon: Presentation, tag: t("gallery.tagPptV7"), tagType: 'pro' as const, gradient: 'from-cyan-500 to-indigo-600', category: 'general' as const },
        { id: 'knowledge-edu', title: t("gallery.tplKnowledgeEdu"), description: t("gallery.tplKnowledgeEduDesc"), icon: BookOpen, tag: t("gallery.tagContent"), tagType: 'default' as const, gradient: 'from-sky-500 to-blue-600', category: 'content' as const },
        { id: 'funny-skit', title: t("gallery.tplFunnySkit"), description: t("gallery.tplFunnySkitDesc"), icon: Laugh, tag: t("gallery.tagContent"), tagType: 'default' as const, gradient: 'from-lime-500 to-green-600', category: 'content' as const },
        { id: 'travel-vlog', title: t("gallery.tplTravelVlog"), description: t("gallery.tplTravelVlogDesc"), icon: Plane, tag: t("gallery.tagContent"), tagType: 'default' as const, gradient: 'from-rose-500 to-orange-600', category: 'content' as const },
        { id: 'tutorial', title: t("gallery.tplTutorial"), description: t("gallery.tplTutorialDesc"), icon: GraduationCap, tag: t("gallery.tagContent"), tagType: 'default' as const, gradient: 'from-blue-500 to-emerald-600', category: 'content' as const },
    ], [t]);

    const CATEGORIES: { key: 'ecommerce' | 'content' | 'general'; label: string; icon: React.ElementType; description: string }[] = [
        { key: 'ecommerce', label: t("gallery.catEcommerce"), icon: ShoppingBag, description: t("gallery.catDescEcommerce") },
        { key: 'general', label: t("gallery.catBrand"), icon: Megaphone, description: t("gallery.catDescBrand") },
        { key: 'content', label: t("gallery.catContent"), icon: Film, description: t("gallery.catDescContent") },
    ];

    const getTagStyles = (tagType: 'hot' | 'pro' | 'digital-human' | 'default') => {
        switch (tagType) {
            case 'hot':
                return 'tag-hot text-white';
            case 'pro':
                return 'tag-pro text-white';
            case 'digital-human':
                return 'tag-digital-human text-white';
            default:
                return 'bg-white/[0.08] border border-white/[0.1] text-gray-400';
        }
    };

    const visibleTemplates = useMemo(() => {
        const q = search.trim().toLowerCase();
        return templates.filter((tpl) => {
            const byCategory = activeCategory === 'all' || tpl.category === activeCategory;
            const bySearch =
                q.length === 0 ||
                tpl.title.toLowerCase().includes(q) ||
                tpl.description.toLowerCase().includes(q) ||
                tpl.tag.toLowerCase().includes(q);
            return byCategory && bySearch;
        });
    }, [activeCategory, search, templates]);

    return (
        <div className="flex-1 overflow-y-auto bg-[#050508] text-white relative">
            {/* Background effects */}
            <div className="fixed inset-0 bg-mesh-gradient pointer-events-none" />
            <div className="fixed top-1/4 left-1/4 w-96 h-96 bg-[#E11D48]/8 rounded-full blur-[100px] animate-float pointer-events-none" />
            <div className="fixed bottom-1/4 right-1/4 w-80 h-80 bg-purple-500/8 rounded-full blur-[80px] animate-float-delayed pointer-events-none" />
            
            <div className="relative z-10 p-4 sm:p-6 md:p-12 lg:p-16">
                <div className="max-w-7xl mx-auto space-y-12">
                    {/* Header */}
                    <div className="space-y-6">
                        <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-gradient-to-r from-[#E11D48]/10 to-purple-500/10 border border-[#E11D48]/20 animate-fade-in-up">
                            <Sparkles className="w-4 h-4 text-[#E11D48] animate-pulse" />
                            <span className="text-sm font-medium bg-gradient-to-r from-[#E11D48] to-purple-400 bg-clip-text text-transparent">{t("nav.platform")}</span>
                        </div>
                        
                        <h1 className="text-3xl sm:text-5xl md:text-6xl font-extrabold tracking-tight animate-fade-in-up" style={{ animationDelay: '0.1s' }}>
                            <span className="block text-white">{t("gallery.title")}</span>
                            <span className="block mt-2 text-gradient-primary">{t("gallery.professionalQuality")}</span>
                        </h1>
                        
                        <p className="text-gray-400 text-base md:text-xl max-w-2xl animate-fade-in-up" style={{ animationDelay: '0.2s' }}>
                            {t("gallery.subtitle")}
                        </p>
                    </div>

                    {/* Category + search controls */}
                    <div className="sticky top-2 z-20 rounded-2xl border border-white/[0.06] bg-black/50 p-3 backdrop-blur-xl">
                        <div className="mb-3 flex items-center gap-2 overflow-x-auto pb-1 [scrollbar-width:none] [-ms-overflow-style:none] [&::-webkit-scrollbar]:hidden">
                            {([
                                { key: 'all', label: t("gallery.allTemplates") },
                                { key: 'ecommerce', label: t("gallery.catEcommerce") },
                                { key: 'general', label: t("gallery.catBrand") },
                                { key: 'content', label: t("gallery.catContent") },
                            ] as const).map((tab) => (
                                <button
                                    key={tab.key}
                                    onClick={() => setActiveCategory(tab.key)}
                                    className={`whitespace-nowrap rounded-full px-3 py-1.5 text-xs font-medium transition-all ${
                                        activeCategory === tab.key
                                            ? 'bg-gradient-to-r from-[#E11D48]/20 to-purple-500/20 text-[#E11D48] border border-[#E11D48]/30'
                                            : 'bg-white/[0.03] text-gray-400 border border-white/[0.06] hover:text-gray-200'
                                    }`}
                                >
                                    {tab.label}
                                </button>
                            ))}
                        </div>
                        <div className="relative">
                            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-500" />
                            <input
                                value={search}
                                onChange={(e) => setSearch(e.target.value)}
                                placeholder={t("gallery.searchPlaceholder")}
                                className="w-full rounded-xl border border-white/[0.08] bg-white/[0.03] py-2.5 pl-9 pr-9 text-sm text-gray-200 outline-none transition-colors placeholder:text-gray-600 focus:border-[#E11D48]/50"
                            />
                            {search && (
                                <button
                                    onClick={() => setSearch('')}
                                    className="absolute right-2 top-1/2 -translate-y-1/2 rounded-md p-1 text-gray-500 hover:bg-white/[0.06] hover:text-gray-300"
                                >
                                    <X className="h-4 w-4" />
                                </button>
                            )}
                        </div>
                    </div>

                    {/* Template categories */}
                    {CATEGORIES.map((cat, catIndex) => {
                        const items = visibleTemplates.filter(tpl => tpl.category === cat.key);
                        if (items.length === 0) return null;
                        const CatIcon = cat.icon;
                        
                        return (
                            <div key={cat.key} className="space-y-6" style={{ animationDelay: `${(catIndex + 4) * 0.1}s` }}>
                                <div className="flex items-center justify-between">
                                    <div className="flex items-center gap-3">
                                        <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-[#E11D48]/20 to-purple-500/20 flex items-center justify-center">
                                            <CatIcon className="w-5 h-5 text-[#E11D48]" />
                                        </div>
                                        <div>
                                            <h2 className="text-xl font-bold text-gray-100">{cat.label}</h2>
                                            <p className="text-xs text-gray-500">{items.length} {t("gallery.templateCount")} · {cat.description}</p>
                                        </div>
                                    </div>
                                </div>
                                
                                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 sm:gap-5">
                                    {items.map((tpl, i) => {
                                        const IconComponent = tpl.icon;
                                        const isHovered = hoveredId === tpl.id;
                                        
                                        return (
                                            <button
                                                key={tpl.id}
                                                onClick={() => onSelect(tpl.id)}
                                                onMouseEnter={() => setHoveredId(tpl.id)}
                                                onMouseLeave={() => setHoveredId(null)}
                                                data-testid={`template-card-${tpl.id}`}
                                                className="group relative flex flex-col p-5 sm:p-6 rounded-2xl border border-white/[0.06] bg-gradient-to-br from-white/[0.02] to-transparent backdrop-blur-sm transition-all duration-500 text-left cursor-pointer overflow-hidden"
                                                style={{ animationDelay: `${i * 0.05}s` }}
                                            >
                                                {/* Animated gradient background */}
                                                <div className={`absolute inset-0 bg-gradient-to-br ${tpl.gradient} opacity-0 group-hover:opacity-10 transition-opacity duration-500`} />
                                                
                                                {/* Animated border glow */}
                                                <div className="absolute inset-0 rounded-2xl opacity-0 group-hover:opacity-100 transition-opacity duration-500">
                                                    <div className={`absolute inset-[-1px] rounded-2xl bg-gradient-to-r ${tpl.gradient} opacity-50`} style={{ filter: 'blur(1px)' }} />
                                                </div>
                                                
                                                {/* Content */}
                                                <div className="relative z-10">
                                                    <div className="flex items-center justify-between mb-5">
                                                        <div className={`w-12 h-12 rounded-xl bg-gradient-to-br ${tpl.gradient} flex items-center justify-center shadow-lg transition-all duration-300 ${isHovered ? 'scale-110 shadow-xl' : ''}`}>
                                                            <IconComponent className="w-6 h-6 text-white" />
                                                        </div>
                                                        <span className={`text-xs px-3 py-1 rounded-full font-medium ${getTagStyles(tpl.tagType)} transition-all duration-300`}>
                                                            {tpl.tag}
                                                        </span>
                                                    </div>
                                                    
                                                    <h3 className="text-base sm:text-lg font-bold mb-2 group-hover:text-white transition-colors">{tpl.title}</h3>
                                                    <p className="text-gray-500 text-sm leading-relaxed group-hover:text-gray-400 transition-colors line-clamp-2">{tpl.description}</p>
                                                    
                                                    {/* Action indicator */}
                                                    <div className="flex items-center gap-2 mt-4 text-gray-600 group-hover:text-[#E11D48] transition-colors">
                                                        <span className="text-xs font-medium">{t("gallery.useTemplate")}</span>
                                                        <ArrowRight className="w-3.5 h-3.5 group-hover:translate-x-1 transition-transform" />
                                                    </div>
                                                </div>
                                                
                                                {/* Shimmer effect */}
                                                <div className="absolute inset-0 translate-x-[-100%] group-hover:translate-x-[100%] transition-transform duration-1000 bg-gradient-to-r from-transparent via-white/5 to-transparent pointer-events-none" />
                                                
                                                {/* Corner accent */}
                                                <div className={`absolute top-0 right-0 w-20 h-20 bg-gradient-to-bl ${tpl.gradient} opacity-0 group-hover:opacity-20 rounded-bl-full transition-opacity duration-500`} />
                                            </button>
                                        );
                                    })}
                                </div>
                            </div>
                        );
                    })}

                    {visibleTemplates.length === 0 && (
                        <div className="rounded-2xl border border-white/[0.06] bg-white/[0.02] p-10 text-center">
                            <p className="text-sm text-gray-300">{t("gallery.noMatches")}</p>
                            <p className="mt-1 text-xs text-gray-500">{t("gallery.tryDifferentKeywords")}</p>
                        </div>
                    )}
                    
                    {/* Bottom CTA */}
                    <div className="pt-8 pb-4">
                        <div className="rounded-3xl border border-white/[0.06] bg-gradient-to-br from-[#E11D48]/5 to-purple-500/5 p-8 md:p-12 relative overflow-hidden">
                            <div className="absolute top-0 right-0 w-64 h-64 bg-[#E11D48]/10 rounded-full blur-[60px] pointer-events-none" />
                            
                            <div className="relative z-10 flex flex-col md:flex-row items-center justify-between gap-6">
                                <div className="flex items-center gap-4">
                                    <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-[#E11D48] to-purple-600 flex items-center justify-center shadow-lg shadow-[#E11D48]/30">
                                        <Wand2 className="w-7 h-7 text-white" />
                                    </div>
                                    <div>
                                        <h3 className="text-xl font-bold">{t("gallery.customTitle")}</h3>
                                        <p className="text-gray-400 text-sm">{t("gallery.customDesc")}</p>
                                    </div>
                                </div>
                                
                                <button
                                    onClick={() => onSelect('empty')}
                                    className="group px-6 py-3 bg-gradient-to-r from-[#E11D48] to-[#BE123C] text-white rounded-full font-semibold text-sm transition-all cursor-pointer flex items-center gap-2 shadow-lg shadow-[#E11D48]/30 hover:shadow-[#E11D48]/50 hover:scale-105"
                                >
                                    <Sparkles className="w-4 h-4" />
                                    {t("gallery.startFromScratch")}
                                    <ArrowRight className="w-4 h-4 group-hover:translate-x-1 transition-transform" />
                                </button>
                            </div>
                        </div>
                    </div>

                    <SocialPanel />
                </div>
            </div>
        </div>
    );
}
