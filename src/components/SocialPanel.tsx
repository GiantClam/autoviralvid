"use client";

import React from "react";
import { Heart, MessageCircle, Share2, Sparkles, TrendingUp } from "lucide-react";
import { useT } from "@/lib/i18n";

export default function SocialPanel() {
  const t = useT();
  const works = [
    { id: "w1", title: t("social.work1Title"), likes: "2.1k", comments: 82, badge: t("social.work1Badge") },
    { id: "w2", title: t("social.work2Title"), likes: "1.6k", comments: 54, badge: t("social.work2Badge") },
    { id: "w3", title: t("social.work3Title"), likes: "980", comments: 31, badge: t("social.work3Badge") },
  ];

  return (
    <section className="space-y-5 pt-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-[#E11D48]/20 to-purple-500/20">
            <TrendingUp className="h-4 w-4 text-[#E11D48]" />
          </div>
          <div>
            <h3 className="text-lg font-bold text-gray-100">{t("social.title")}</h3>
            <p className="text-xs text-gray-500">{t("social.subtitle")}</p>
          </div>
        </div>
      </div>

      <div className="flex gap-4 overflow-x-auto pb-1 md:grid md:grid-cols-3 md:overflow-visible [scrollbar-width:none] [-ms-overflow-style:none] [&::-webkit-scrollbar]:hidden">
        {works.map((work) => (
          <article
            key={work.id}
            className="group relative min-w-[250px] md:min-w-0 overflow-hidden rounded-2xl border border-white/[0.06] bg-gradient-to-br from-white/[0.02] to-transparent p-4 transition-all duration-300 hover:border-white/[0.14]"
          >
            <div className="absolute inset-0 bg-gradient-to-br from-[#E11D48]/0 to-purple-500/0 opacity-0 transition-opacity duration-300 group-hover:opacity-100 group-hover:from-[#E11D48]/10 group-hover:to-purple-500/10" />
            <div className="relative z-10">
              <div className="mb-3 inline-flex items-center gap-1 rounded-full bg-white/[0.05] px-2 py-0.5 text-[11px] text-gray-300">
                <Sparkles className="h-3 w-3 text-[#E11D48]" />
                {work.badge}
              </div>
              <h4 className="mb-4 text-sm font-semibold text-gray-200">{work.title}</h4>
              <div className="flex items-center gap-3 text-xs text-gray-500">
                <span className="inline-flex items-center gap-1">
                  <Heart className="h-3.5 w-3.5" />
                  {work.likes}
                </span>
                <span className="inline-flex items-center gap-1">
                  <MessageCircle className="h-3.5 w-3.5" />
                  {work.comments}
                </span>
                <button className="ml-auto inline-flex items-center gap-1 text-gray-400 transition-colors hover:text-[#E11D48]">
                  <Share2 className="h-3.5 w-3.5" />
                  {t("social.share")}
                </button>
              </div>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
