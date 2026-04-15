export type GenerationChargeRule = {
  id: string;
  method: "POST" | "PUT" | "PATCH" | "DELETE" | "GET";
  pattern: RegExp;
  units: number;
};

const GENERATION_CHARGE_RULES: readonly GenerationChargeRule[] = [
  {
    id: "storyboard-generate",
    method: "POST",
    pattern: /^\/projects\/[^/]+\/storyboard$/,
    units: 1,
  },
  {
    id: "image-generate",
    method: "POST",
    pattern: /^\/projects\/[^/]+\/images$/,
    units: 1,
  },
  {
    id: "image-regenerate",
    method: "POST",
    pattern: /^\/projects\/[^/]+\/images\/[^/]+\/regenerate$/,
    units: 1,
  },
  {
    id: "video-submit",
    method: "POST",
    pattern: /^\/projects\/[^/]+\/videos$/,
    units: 1,
  },
  {
    id: "video-regenerate",
    method: "POST",
    pattern: /^\/projects\/[^/]+\/videos\/[^/]+\/regenerate$/,
    units: 1,
  },
  {
    id: "digital-human-submit",
    method: "POST",
    pattern: /^\/projects\/[^/]+\/digital-human$/,
    units: 2,
  },
  {
    id: "final-render",
    method: "POST",
    pattern: /^\/projects\/[^/]+\/render$/,
    units: 1,
  },
  {
    id: "ppt-prompt-generate",
    method: "POST",
    pattern: /^\/ppt\/generate-from-prompt$/,
    units: 1,
  },
  {
    id: "ppt-v7-export",
    method: "POST",
    pattern: /^\/v7\/export$/,
    units: 1,
  },
  {
    id: "ppt-v7-export-submit",
    method: "POST",
    pattern: /^\/v7\/export\/submit$/,
    units: 1,
  },
  {
    id: "ppt-video-render",
    method: "POST",
    pattern: /^\/ppt\/render$/,
    units: 1,
  },
];

function normalizePath(path: string): string {
  if (!path) return "/";
  return path.startsWith("/") ? path : `/${path}`;
}

export function resolveGenerationChargeRule(
  method: string,
  normalizedPath: string,
): GenerationChargeRule | null {
  const normalizedMethod = method.toUpperCase();
  const path = normalizePath(normalizedPath);
  return (
    GENERATION_CHARGE_RULES.find(
      (rule) => rule.method === normalizedMethod && rule.pattern.test(path),
    ) ?? null
  );
}

export function buildNormalizedProxyPath(
  pathSegments: string[],
  prefixSegments: readonly string[] = [],
): string {
  const joined = [...prefixSegments, ...(pathSegments || [])]
    .filter((segment) => segment && segment.trim().length > 0)
    .join("/");
  return normalizePath(joined);
}

export function getGenerationChargeRules(): readonly GenerationChargeRule[] {
  return GENERATION_CHARGE_RULES;
}
