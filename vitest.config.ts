import { defineConfig } from 'vitest/config';
import path from 'path';

const integrationOnlyTests = [
  'src/lib/render/render-api.test.ts',
  'src/lib/render/remotion-full-render.test.ts',
  'src/lib/render/remotion-integration.test.ts',
  'src/lib/render/remotion-perf.test.ts',
  'src/integration/deployed-environment.test.ts',
];

const includeIntegrationTests = process.env.RUN_INTEGRATION_TESTS === '1';
const includeDeployedIntegrationTests = process.env.RUN_DEPLOYED_INTEGRATION_TESTS === '1';

export default defineConfig({
  test: {
    environment: 'node',
    include: ['src/**/*.test.ts'],
    exclude: includeIntegrationTests || includeDeployedIntegrationTests
      ? ['node_modules', '.next', 'agent']
      : ['node_modules', '.next', 'agent', ...integrationOnlyTests],
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
});
