import { runBillingReconcile } from "../../src/lib/billing/reconcile";

function parseNumberFlag(name: string, fallback: number): number {
  const arg = process.argv.find((item) => item.startsWith(`--${name}=`));
  if (!arg) return fallback;
  const value = Number(arg.split("=")[1]);
  if (!Number.isFinite(value)) return fallback;
  return value;
}

function hasFlag(name: string): boolean {
  return process.argv.includes(`--${name}`);
}

async function main() {
  const lookbackHours = parseNumberFlag("lookbackHours", 72);
  const staleMinutes = parseNumberFlag("staleMinutes", 30);
  const json = hasFlag("json");

  const report = await runBillingReconcile({ lookbackHours, staleMinutes });

  if (json) {
    console.log(JSON.stringify(report, null, 2));
    return;
  }

  console.log("[billing-reconcile] generatedAt:", report.generatedAt);
  console.log(
    "[billing-reconcile] summary:",
    JSON.stringify(report.summary, null, 2),
  );
  if (report.mismatches.length > 0) {
    console.log("[billing-reconcile] mismatches:");
    for (const row of report.mismatches) {
      console.log(
        `- [${row.severity}] ${row.code} user=${row.userId || "-"} ref=${row.referenceId || "-"} detail=${row.detail}`,
      );
    }
  }
}

main().catch((error) => {
  console.error("[billing-reconcile] failed:", error);
  process.exit(1);
});
