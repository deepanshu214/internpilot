import type { Metadata } from "next";
import Link from "next/link";
import { Nav } from "@/components/client";
import { timeAgo } from "@/components/ui";
import { cookies } from "next/headers";
import { COOKIE, authEnabled, safeEqual, sessionToken } from "@/lib/auth";
import { workerStatus } from "@/lib/data";
import { logout } from "./actions";
import "./globals.css";

export const metadata: Metadata = { title: "InternPilot", description: "Internship radar, applications and outreach" };
export const dynamic = "force-dynamic";

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const authed = !authEnabled() || safeEqual((await cookies()).get(COOKIE)?.value ?? "", await sessionToken());
  if (!authed) {
    return (
      <html lang="en">
        <body className="min-h-screen px-4">{children}</body>
      </html>
    );
  }
  let worker: Awaited<ReturnType<typeof workerStatus>> | null = null;
  try {
    worker = await workerStatus();
  } catch {
    worker = null; // DB not reachable (e.g. login page before setup)
  }
  return (
    <html lang="en">
      <body className="min-h-screen">
        <div className="mx-auto flex max-w-7xl flex-col gap-4 px-4 py-4 md:flex-row md:gap-8 md:py-6">
          <aside className="flex shrink-0 flex-col gap-4 md:sticky md:top-6 md:h-[calc(100vh-3rem)] md:w-48">
            <div className="flex items-center justify-between md:block">
              <Link href="/" className="flex items-center gap-2 font-semibold tracking-tight">
                <span className="grid h-7 w-7 place-items-center rounded-lg bg-accent text-sm text-white" aria-hidden>IP</span>
                InternPilot
              </Link>
            </div>
            <Nav />
            <div className="mt-auto hidden space-y-2 text-xs text-ink-3 md:block">
              {worker && (
                <p className="flex items-start gap-2" title={worker.heartbeat ?? "never"}>
                  <span className={`mt-1 h-2 w-2 shrink-0 rounded-full ${worker.online ? "bg-good" : "bg-line-strong"}`} aria-hidden />
                  <span>
                    {worker.online ? "Worker online" : "Worker offline"}
                    {worker.queued > 0 && ` · ${worker.queued} queued`}
                    <br />
                    {worker.online ? `heartbeat ${timeAgo(worker.heartbeat)}` : "Start it on your Mac"}
                  </span>
                </p>
              )}
              {authEnabled() && (
                <form action={logout}>
                  <button className="hover:text-ink">Log out</button>
                </form>
              )}
            </div>
          </aside>
          <main className="min-w-0 flex-1">{children}</main>
        </div>
      </body>
    </html>
  );
}
