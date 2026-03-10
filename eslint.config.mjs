import nextCoreWebVitals from "eslint-config-next/core-web-vitals";
import nextTypescript from "eslint-config-next/typescript";

const eslintConfig = [
  ...nextCoreWebVitals,
  ...nextTypescript,
  {
    ignores: [
      "node_modules/**",
      ".next/**",
      "out/**",
      "build/**",
      "next-env.d.ts",
      ".agent/**",
      ".claude/**",
      ".cursor/**",
      ".opencode/**",
      ".playwright-mcp/**",
      ".tmp-*/**",
      "__pycache__/**",
      "agent/**",
      "design-system/**",
      "docs/**",
      "src/**/*.test.ts",
      "src/**/*.test.tsx",
      "src/**/__tests__/**",
      "src/integration/**",
      "test_outputs/**",
      "test_reports/**",
      "lint-report.json",
    ],
  },
];

export default eslintConfig;
