import { spawnSync } from "node:child_process";

function run(command, args, options = {}) {
  const result = spawnSync(command, args, {
    stdio: "inherit",
    shell: process.platform === "win32",
    ...options,
  });

  if (result.error) {
    throw result.error;
  }
  if (typeof result.status === "number" && result.status !== 0) {
    process.exit(result.status);
  }
}

function hasUv() {
  const probe = spawnSync("uv", ["--version"], {
    stdio: "ignore",
    shell: process.platform === "win32",
  });
  return probe.status === 0;
}

const skipAgentInstall = process.env.SKIP_AGENT_INSTALL === "1";

if (skipAgentInstall) {
  console.log("[postinstall] SKIP_AGENT_INSTALL=1, skipping agent dependency install.");
} else if (hasUv()) {
  console.log("[postinstall] uv detected, installing agent dependencies.");
  run("npm", ["run", "install:agent"]);
} else {
  console.log("[postinstall] uv not found, skipping agent dependency install.");
}

console.log("[postinstall] Generating Prisma client.");
run("npx", ["prisma", "generate"]);
