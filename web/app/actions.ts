"use server";

import { revalidatePath } from "next/cache";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { COOKIE, safeEqual, sessionToken } from "@/lib/auth";
import { enqueue, logEvent, now, run } from "@/lib/db";
import { STATUSES, type Status } from "@/lib/data";

const TASKS = new Set(["discover", "tailor", "find_contacts", "draft_outreach", "autofill", "prep", "cover_letter", "referral", "prepare"]);

function refresh(jobId?: string) {
  revalidatePath("/", "layout");
  if (jobId) revalidatePath(`/jobs/${jobId}`);
}

async function setStatus(jobId: string, status: Status, extra: Record<string, string> = {}) {
  if (!STATUSES.includes(status)) throw new Error("bad status");
  const cols = Object.keys(extra);
  await run(`update matches set status = ?, updated_at = ?${cols.map((c) => `, ${c} = ?`).join("")} where job_id = ?`,
    [status, now(), ...cols.map((c) => extra[c]), jobId]);
  await logEvent("status", status, jobId);
}

export async function shortlist(jobId: string) {
  await setStatus(jobId, "shortlisted");
  await enqueue("prepare", jobId);
  refresh(jobId);
}

export async function skip(jobId: string) {
  await setStatus(jobId, "skipped");
  refresh(jobId);
}

export async function moveStatus(jobId: string, status: string) {
  await setStatus(jobId, status as Status, status === "applied" ? { applied_at: now() } : {});
  refresh(jobId);
}

export async function runTask(kind: string, jobId: string | null, payload: object = {}) {
  if (!TASKS.has(kind)) throw new Error("unknown task");
  await enqueue(kind, jobId, payload);
  refresh(jobId ?? undefined);
}

export async function saveNotes(jobId: string, form: FormData) {
  await run("update matches set notes = ?, deadline = ?, updated_at = ? where job_id = ?",
    [String(form.get("notes") ?? ""), String(form.get("deadline") ?? "") || null, now(), jobId]);
  refresh(jobId);
}

export async function setDomain(jobId: string, company: string, form: FormData) {
  const domain = String(form.get("domain") ?? "").trim().toLowerCase().replace(/^https?:\/\//, "").replace(/\/.*$/, "");
  if (!domain) return;
  await run("update jobs set company_domain = ? where id = ?", [domain, jobId]);
  const key = company.toLowerCase().replace(/[^a-z0-9 ]+/g, " ").replace(/\s+/g, " ").trim();
  await run(`insert into companies (name, domain, fetched_at) values (?, ?, ?)
    on conflict (name) do update set domain = excluded.domain, brief = null`, [key, domain, now()]);
  await enqueue("find_contacts", jobId);
  refresh(jobId);
}

export async function addContact(jobId: string, form: FormData) {
  const name = String(form.get("name") ?? "").trim();
  if (!name) return;
  await enqueue("find_contacts", jobId, {
    name, title: String(form.get("title") ?? "").trim(), email: String(form.get("email") ?? "").trim(),
  });
  refresh(jobId);
}

export async function saveDraft(id: string, jobId: string | null, form: FormData) {
  await run("update outreach set subject = ?, body = ?, to_email = ?, updated_at = ? where id = ? and status = 'draft'", [
    String(form.get("subject") ?? ""), String(form.get("body") ?? ""), String(form.get("to_email") ?? "").trim() || null,
    now(), id,
  ]);
  refresh(jobId ?? undefined);
  revalidatePath("/outreach");
}

/** The only path to sending an email: you click Approve on a specific draft. */
export async function approveAndSend(id: string, jobId: string | null, form: FormData) {
  await saveDraft(id, jobId, form);
  await run("update outreach set status = 'approved', updated_at = ? where id = ? and status = 'draft'", [now(), id]);
  await enqueue("send_outreach", jobId, { outreach_id: id });
  refresh(jobId ?? undefined);
  revalidatePath("/outreach");
}

export async function discardDraft(id: string, jobId: string | null) {
  await run("update outreach set status = 'skipped', updated_at = ? where id = ? and status = 'draft'", [now(), id]);
  refresh(jobId ?? undefined);
  revalidatePath("/outreach");
}

export async function login(_: string | null, form: FormData): Promise<string | null> {
  const pw = String(form.get("password") ?? "");
  const expected = process.env.DASHBOARD_PASSWORD ?? "";
  if (!expected || !safeEqual(pw, expected)) {
    await new Promise((r) => setTimeout(r, 1500)); // slows down password guessing
    return "Wrong password";
  }
  (await cookies()).set(COOKIE, await sessionToken(), {
    httpOnly: true, secure: process.env.NODE_ENV === "production", sameSite: "lax", maxAge: 60 * 60 * 24 * 30, path: "/",
  });
  redirect("/");
}

export async function logout() {
  (await cookies()).delete(COOKIE);
  redirect("/login");
}
