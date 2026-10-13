"use client";

import { useState } from "react";
import { useFormStatus } from "react-dom";
import { BTN } from "./client";

function Btn({ formAction, children, variant, pending }: {
  formAction: (f: FormData) => Promise<void>; children: React.ReactNode; variant: keyof typeof BTN; pending: string;
}) {
  const { pending: busy } = useFormStatus();
  return <button formAction={formAction} disabled={busy} className={BTN[variant]}>{busy ? pending : children}</button>;
}

export function DraftEditor({ draft, save, approve, discard }: {
  draft: { subject: string; body: string; to_email: string | null; kind: string; variant: string | null; project_pitched: string | null };
  save: (f: FormData) => Promise<void>; approve: (f: FormData) => Promise<void>; discard: () => Promise<void>;
}) {
  const [confirming, setConfirming] = useState(false);
  const words = draft.body.split("Best,")[0].trim().split(/\s+/).length;
  return (
    <form className="space-y-2">
      <div className="flex flex-wrap items-center gap-2 text-xs text-ink-3">
        <span className="rounded bg-surface-2 px-1.5 py-0.5">{draft.kind === "followup" ? "Follow-up" : `Template ${draft.variant ?? "–"}`}</span>
        {draft.project_pitched && <span>Pitching {draft.project_pitched.split(" — ")[0]}</span>}
        <span className="tabular">· {words} words</span>
      </div>
      <label className="block text-xs text-ink-2">To
        <input name="to_email" defaultValue={draft.to_email ?? ""} placeholder="recruiter@company.com" required
          className="mt-1 w-full rounded-lg border border-line bg-surface px-3 py-1.5 text-sm text-ink" />
      </label>
      <label className="block text-xs text-ink-2">Subject
        <input name="subject" defaultValue={draft.subject}
          className="mt-1 w-full rounded-lg border border-line bg-surface px-3 py-1.5 text-sm text-ink" />
      </label>
      <label className="block text-xs text-ink-2">Body
        <textarea name="body" defaultValue={draft.body} rows={13}
          className="mt-1 w-full rounded-lg border border-line bg-surface px-3 py-2 font-mono text-[13px] leading-relaxed text-ink" />
      </label>
      <div className="flex flex-wrap items-center gap-2">
        <Btn formAction={save} variant="secondary" pending="Saving…">Save draft</Btn>
        {confirming ? (
          <>
            <Btn formAction={approve} variant="primary" pending="Queued…">Yes, send it</Btn>
            <button type="button" onClick={() => setConfirming(false)} className={BTN.ghost}>Cancel</button>
            <span className="text-xs text-ink-3">Sends from your Gmail with your tailored resume attached.</span>
          </>
        ) : (
          <button type="button" onClick={() => setConfirming(true)} className={BTN.primary}>Approve & send…</button>
        )}
        <button formAction={discard} className={`${BTN.ghost} ml-auto`}>Discard</button>
      </div>
    </form>
  );
}

export function CopyButton({ text }: { text: string }) {
  const [done, setDone] = useState(false);
  return (
    <button type="button" className={BTN.ghost}
      onClick={() => navigator.clipboard.writeText(text).then(() => { setDone(true); setTimeout(() => setDone(false), 1500); })}>
      {done ? "Copied" : "Copy"}
    </button>
  );
}
