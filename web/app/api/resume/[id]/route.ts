import { one } from "@/lib/db";

export const dynamic = "force-dynamic";

export async function GET(_: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const r = await one<{ pdf_b64: string; version: number; company: string }>(
    "select r.pdf_b64, r.version, j.company from resumes r join jobs j on j.id = r.job_id where r.id = ?", [id]);
  if (!r?.pdf_b64) return new Response("Not found", { status: 404 });
  const name = `Deepanshu_Agarwal_Resume_${r.company.replace(/[^A-Za-z0-9]+/g, "_")}_v${r.version}.pdf`;
  return new Response(Buffer.from(r.pdf_b64, "base64"), {
    headers: { "Content-Type": "application/pdf", "Content-Disposition": `inline; filename="${name}"`, "Cache-Control": "private, no-store" },
  });
}
