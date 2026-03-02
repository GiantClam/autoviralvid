import type { Metadata } from "next";
import { Plus_Jakarta_Sans } from "next/font/google";
import { Providers } from "@/components/Providers";
import "./globals.css";

const plusJakarta = Plus_Jakarta_Sans({
  subsets: ["latin"],
  weight: ["300", "400", "500", "600", "700", "800"],
  variable: "--font-plus-jakarta",
  display: "swap",
});

const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL || "https://autoviralvid.com";

export const metadata: Metadata = {
  title: "AutoViralVid - AI 短视频创作平台",
  description: "AI驱动的智能短视频生成工具，多Agent协作，从脚本到成片，一键生成高转化营销视频",
  metadataBase: new URL(SITE_URL),
  openGraph: {
    title: "AutoViralVid - AI 短视频创作平台",
    description: "AI驱动的智能短视频生成工具，多Agent协作，一键生成高转化营销视频。支持数字人口播、产品广告、品牌故事等多种模板。",
    url: SITE_URL,
    siteName: "AutoViralVid",
    locale: "zh_CN",
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "AutoViralVid - AI 短视频创作平台",
    description: "AI驱动的智能短视频生成工具，多Agent协作，一键生成高转化营销视频",
  },
  robots: {
    index: true,
    follow: true,
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN" className="dark">
      <body className={`${plusJakarta.className} antialiased bg-black text-white`}>
        <Providers>
          {children}
        </Providers>
      </body>
    </html>
  );
}
