import Link from "next/link";
import { ArrowLeft } from "lucide-react";

export default function TermsOfService() {
    return (
        <div className="min-h-screen bg-[#060610] text-white">
            <div className="h-16 border-b border-white/[0.08] flex items-center px-8 gap-4">
                <Link href="/" className="p-2 rounded-lg hover:bg-white/[0.04] transition-colors">
                    <ArrowLeft className="w-4 h-4 text-gray-400" />
                </Link>
                <h1 className="font-semibold text-lg">服务条款</h1>
            </div>

            <article className="max-w-2xl mx-auto px-6 py-10 prose prose-invert prose-sm prose-gray">
                <p className="text-gray-500 text-xs">最后更新: 2025 年 1 月</p>

                <h2 className="text-base font-semibold text-gray-200 mt-8">1. 服务说明</h2>
                <p className="text-sm text-gray-400 leading-relaxed">
                    AutoViralVid（以下简称"本平台"）是一款 AI 驱动的短视频生成 SaaS 服务。用户可通过本平台上传素材、
                    配置参数，由 AI 自动生成视频内容。
                </p>

                <h2 className="text-base font-semibold text-gray-200 mt-8">2. 用户义务</h2>
                <p className="text-sm text-gray-400 leading-relaxed">
                    用户承诺所上传的素材（图片、音频、文本等）不侵犯任何第三方的知识产权、肖像权或其他合法权益。
                    用户对生成内容的合规性承担最终责任。
                </p>

                <h2 className="text-base font-semibold text-gray-200 mt-8">3. 付费与退款</h2>
                <p className="text-sm text-gray-400 leading-relaxed">
                    本平台采用订阅制收费，具体方案详见定价页面。已消耗的 AI 生成配额不予退款。
                    未使用部分的退款按照所在地区消费者保护法规处理。
                </p>

                <h2 className="text-base font-semibold text-gray-200 mt-8">4. 免责声明</h2>
                <p className="text-sm text-gray-400 leading-relaxed">
                    AI 生成内容可能存在不准确或不完美的情况。本平台不对生成内容的准确性、完整性或适用性作任何保证。
                    用户应在发布前审核所有生成内容。
                </p>

                <h2 className="text-base font-semibold text-gray-200 mt-8">5. 联系方式</h2>
                <p className="text-sm text-gray-400 leading-relaxed">
                    如有疑问，请发送邮件至 support@autoviralvid.com。
                </p>
            </article>
        </div>
    );
}
