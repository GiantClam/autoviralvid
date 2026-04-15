import fs from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";

const repoRoot = process.cwd();
const lockPath = path.join(repoRoot, ".next", "dev", "lock");

function hasLockFile() {
  return fs.existsSync(lockPath);
}

function normalizeWindowsPath(input) {
  return input.replace(/\//g, "\\").toLowerCase();
}

function queryWindowsNodeProcesses() {
  const psCommand = [
    "$rows = Get-CimInstance Win32_Process -Filter \"name='node.exe'\" | Select-Object ProcessId, CommandLine",
    "$rows | ConvertTo-Json -Compress",
  ].join("; ");

  const result = spawnSync(
    "powershell",
    ["-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", psCommand],
    { encoding: "utf8" },
  );

  if (result.status !== 0 || !result.stdout?.trim()) {
    return [];
  }

  const parsed = JSON.parse(result.stdout);
  const list = Array.isArray(parsed) ? parsed : [parsed];
  return list
    .map((row) => ({
      pid: Number(row.ProcessId),
      commandLine: String(row.CommandLine || ""),
    }))
    .filter((row) => Number.isFinite(row.pid) && row.pid > 0 && row.commandLine);
}

function isRepoNextDevProcess(commandLine) {
  const cmd = normalizeWindowsPath(commandLine);
  const cwd = normalizeWindowsPath(repoRoot);
  if (!cmd.includes(cwd)) return false;

  const markers = [
    `${cwd}\\node_modules\\.bin\\..\\next\\dist\\bin\\next\" dev`,
    `${cwd}\\node_modules\\next\\dist\\server\\lib\\start-server.js`,
    `${cwd}\\.next\\dev\\`,
  ];

  return markers.some((marker) => cmd.includes(marker));
}

function terminateWindowsProcessTree(pid) {
  const result = spawnSync("taskkill", ["/PID", String(pid), "/T", "/F"], {
    encoding: "utf8",
  });
  return result.status === 0;
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function removeLockWithRetry() {
  for (let i = 0; i < 10; i += 1) {
    if (!hasLockFile()) return true;
    try {
      fs.rmSync(lockPath, { force: true });
      return true;
    } catch {
      // lock is still held by a process, retry shortly
    }
    // eslint-disable-next-line no-await-in-loop
    await sleep(250);
  }
  return !hasLockFile();
}

async function main() {
  if (!hasLockFile()) return;

  if (process.platform === "win32") {
    const candidates = queryWindowsNodeProcesses().filter((proc) =>
      isRepoNextDevProcess(proc.commandLine),
    );

    if (candidates.length > 0) {
      for (const proc of candidates) {
        terminateWindowsProcessTree(proc.pid);
      }
      await sleep(300);
    }
  }

  const removed = await removeLockWithRetry();
  if (!removed) {
    console.error(
      `[cleanup-next-dev-lock] Cannot clear ${lockPath}. Another Next dev process is still holding the lock.`,
    );
    process.exit(1);
  }

  console.log("[cleanup-next-dev-lock] Cleared stale .next/dev lock.");
}

main().catch((error) => {
  console.error("[cleanup-next-dev-lock] Unexpected error:", error);
  process.exit(1);
});
