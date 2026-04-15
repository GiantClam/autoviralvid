export const dynamic = "force-dynamic";

import { NextResponse } from "next/server";
import { getErrorMessage } from "@/lib/errors";
import { getBillingSnapshot } from "@/lib/billing/account";

export async function GET() {
  try {
    const { auth } = await import("@/lib/auth");
    const session = await auth();

    if (!session?.user?.id) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    const snapshot = await getBillingSnapshot(session.user.id);
    return NextResponse.json(snapshot);
  } catch (error) {
    return NextResponse.json(
      { error: getErrorMessage(error, "Failed to fetch billing snapshot") },
      { status: 500 },
    );
  }
}

