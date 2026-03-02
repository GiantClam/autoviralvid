import type { MetadataRoute } from "next";

export default function robots(): MetadataRoute.Robots {
    const siteUrl = process.env.NEXT_PUBLIC_SITE_URL || "https://autoviralvid.com";
    return {
        rules: [
            {
                userAgent: "*",
                allow: "/",
                disallow: ["/api/", "/settings", "/reset-password"],
            },
        ],
        sitemap: `${siteUrl}/sitemap.xml`,
    };
}
