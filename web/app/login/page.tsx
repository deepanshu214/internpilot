"use client";

import { useActionState } from "react";
import { BTN } from "@/components/client";
import { login } from "../actions";

export default function Login() {
  const [error, action, pending] = useActionState(login, null);
  return (
    <div className="mx-auto mt-20 max-w-sm rounded-xl border border-line bg-surface p-6">
      <h1 className="text-lg font-semibold">InternPilot</h1>
      <p className="mt-1 text-sm text-ink-2">Private dashboard. Enter your password.</p>
      <form action={action} className="mt-4 space-y-3">
        <input type="password" name="password" autoFocus required aria-label="Password"
          className="w-full rounded-lg border border-line bg-surface px-3 py-2" />
        {error && <p className="text-sm text-critical" role="alert">{error}</p>}
        <button className={`${BTN.primary} w-full`} disabled={pending}>{pending ? "Checking…" : "Sign in"}</button>
      </form>
    </div>
  );
}
