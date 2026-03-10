import Link from "next/link";
import { ArrowLeft } from "lucide-react";

export default function TermsOfService() {
  return (
    <div className="min-h-screen bg-[#060610] text-white">
      <div className="flex h-16 items-center gap-4 border-b border-white/[0.08] px-8">
        <Link href="/" className="rounded-lg p-2 transition-colors hover:bg-white/[0.04]">
          <ArrowLeft className="h-4 w-4 text-gray-400" />
        </Link>
        <h1 className="text-lg font-semibold">Terms of Service</h1>
      </div>

      <article className="prose prose-invert prose-sm prose-gray mx-auto max-w-2xl px-6 py-10">
        <p className="text-xs text-gray-500">Last updated: January 1, 2025</p>

        <h2 className="mt-8 text-base font-semibold text-gray-200">1. Service Overview</h2>
        <p className="text-sm leading-relaxed text-gray-400">
          AutoViralVid is an AI-assisted short-video creation platform. Users can upload
          media, configure generation parameters, and create publishable marketing videos.
        </p>

        <h2 className="mt-8 text-base font-semibold text-gray-200">2. User Responsibilities</h2>
        <p className="text-sm leading-relaxed text-gray-400">
          You are responsible for the legality of uploaded media, prompts, and generated
          outputs. Do not upload content that infringes intellectual property, portrait
          rights, privacy rights, or any other third-party rights.
        </p>

        <h2 className="mt-8 text-base font-semibold text-gray-200">3. Billing and Refunds</h2>
        <p className="text-sm leading-relaxed text-gray-400">
          Paid plans are billed as subscriptions unless stated otherwise. Consumed AI
          generation quota is generally non-refundable. Any mandatory refund rights are
          handled under the consumer protection rules applicable to your jurisdiction.
        </p>

        <h2 className="mt-8 text-base font-semibold text-gray-200">4. Disclaimer</h2>
        <p className="text-sm leading-relaxed text-gray-400">
          AI-generated content may contain factual, stylistic, or compliance defects. You
          must review all generated outputs before publishing or using them commercially.
        </p>

        <h2 className="mt-8 text-base font-semibold text-gray-200">5. Contact</h2>
        <p className="text-sm leading-relaxed text-gray-400">
          For legal or support questions, contact support@autoviralvid.com.
        </p>
      </article>
    </div>
  );
}
