import Link from "next/link";
import { ArrowLeft } from "lucide-react";

export default function PrivacyPolicy() {
    return (
        <div className="min-h-screen bg-[#060610] text-white">
            <div className="h-16 border-b border-white/[0.08] flex items-center px-8 gap-4">
                <Link href="/" className="p-2 rounded-lg hover:bg-white/[0.04] transition-colors">
                    <ArrowLeft className="w-4 h-4 text-gray-400" />
                </Link>
                <h1 className="font-semibold text-lg">隐私政策</h1>
            </div>

            <article className="max-w-2xl mx-auto px-6 py-10 prose prose-invert prose-sm prose-gray">
                <p className="text-gray-500 text-xs">最后更新: 2025 年 1 月</p>

                <h2 className="text-base font-semibold text-gray-200 mt-8">1. 信息收集</h2>
                <p className="text-sm text-gray-400 leading-relaxed">
                    我们收集以下类型的信息：注册邮箱、密码（加密存储）、上传的媒体文件、生成的视频内容，
                    以及基本的使用日志（访问时间、操作记录）。
                </p>

                <h2 className="text-base font-semibold text-gray-200 mt-8">2. 信息使用</h2>
                <p className="text-sm text-gray-400 leading-relaxed">
                    您的信息仅用于提供和改进服务。我们不会将您的个人信息出售给第三方。
                    上传的素材仅用于视频生成，处理完成后按照我们的数据保留政策进行清理。
                </p>

                <h2 className="text-base font-semibold text-gray-200 mt-8">3. 数据存储与安全</h2>
                <p className="text-sm text-gray-400 leading-relaxed">
                    用户数据存储于加密的云服务器中。我们采用行业标准的安全措施保护您的数据，
                    包括 HTTPS 传输加密、数据库加密存储、定期安全审计等。
                </p>

                <h2 className="text-base font-semibold text-gray-200 mt-8">4. Cookie 与追踪</h2>
                <p className="text-sm text-gray-400 leading-relaxed">
                    本平台使用必要的会话 Cookie 维持登录状态。我们可能使用匿名分析工具了解平台使用情况，
                    您可以通过浏览器设置管理 Cookie。
                </p>

                <h2 className="text-base font-semibold text-gray-200 mt-8">5. 用户权利</h2>
                <p className="text-sm text-gray-400 leading-relaxed">
                    您有权访问、更正或删除您的个人数据。如需行使这些权利，请联系 privacy@autoviralvid.com。
                </p>

                <h2 className="text-base font-semibold text-gray-200 mt-8">6. 联系方式</h2>
                <p className="text-sm text-gray-400 leading-relaxed">
                    隐私相关问题请发送邮件至 privacy@autoviralvid.com。
                </p>
            </article>
        </div>
    );
}
