import type { MetadataRoute } from "next";

export default function sitemap(): MetadataRoute.Sitemap {
    const siteUrl = process.env.NEXT_PUBLIC_SITE_URL || "https://autoviralvid.com";
    const now = new Date().toISOString();

    return [
        {
            url: siteUrl,
            lastModified: now,
            changeFrequency: "weekly",
            priority: 1,
        },
        {
            url: `${siteUrl}/legal/terms`,
            lastModified: now,
            changeFrequency: "monthly",
            priority: 0.3,
        },
        {
            url: `${siteUrl}/legal/privacy`,
            lastModified: now,
            changeFrequency: "monthly",
            priority: 0.3,
        },
    ];
}
