"use client";

import React from "react";
import { Heart, MessageCircle, Share2, Sparkles, TrendingUp } from "lucide-react";

const WORKS = [
  { id: "w1", title: "夏日饮品广告", likes: "2.1k", comments: 82, badge: "热门" },
  { id: "w2", title: "美妆口播短片", likes: "1.6k", comments: 54, badge: "精选" },
  { id: "w3", title: "科技开箱脚本", likes: "980", comments: 31, badge: "趋势" },
];

export default function SocialPanel() {
  return (
    <section className="space-y-5 pt-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-[#E11D48]/20 to-purple-500/20">
            <TrendingUp className="h-4 w-4 text-[#E11D48]" />
          </div>
          <div>
            <h3 className="text-lg font-bold text-gray-100">热门作品</h3>
            <p className="text-xs text-gray-500">看看社区里正在流行的创意风格</p>
          </div>
        </div>
      </div>

      <div className="flex gap-4 overflow-x-auto pb-1 md:grid md:grid-cols-3 md:overflow-visible [scrollbar-width:none] [-ms-overflow-style:none] [&::-webkit-scrollbar]:hidden">
        {WORKS.map((work) => (
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
                  分享
                </button>
              </div>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
