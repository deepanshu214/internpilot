// Single-series charts (one hue → no legend; the title names the series). Thin marks, rounded data-ends,
// hairline baseline, per-mark hover tooltip, and a table view for every chart.
type Datum = { label: string; value: number; hint?: string };

function TableView({ data, unit }: { data: Datum[]; unit: string }) {
  return (
    <details className="mt-2 text-xs text-ink-2">
      <summary className="cursor-pointer text-ink-3 hover:text-ink">Show as table</summary>
      <table className="tabular mt-1 w-full">
        <tbody>{data.map((d) => (
          <tr key={d.label} className="border-t border-line"><td className="py-1">{d.label}</td><td className="py-1 text-right">{d.value} {unit}</td></tr>
        ))}</tbody>
      </table>
    </details>
  );
}

export function BarList({ data, unit = "", empty = "No data yet." }: { data: Datum[]; unit?: string; empty?: string }) {
  if (!data.length) return <p className="py-6 text-center text-sm text-ink-3">{empty}</p>;
  const max = Math.max(...data.map((d) => d.value), 1);
  return (
    <div>
      <ul className="space-y-1.5">
        {data.map((d) => (
          <li key={d.label} className="group relative grid grid-cols-[minmax(0,9rem)_1fr_auto] items-center gap-2 text-sm">
            <span className="truncate text-ink-2" title={d.label}>{d.label}</span>
            <span className="relative h-3 rounded-r-[4px] bg-transparent" aria-hidden>
              <span className="absolute inset-y-0 left-0 rounded-r-[4px] bg-[var(--series-1)] transition-opacity group-hover:opacity-80"
                style={{ width: `${d.value ? Math.max(2, (100 * d.value) / max) : 0}%` }} />
            </span>
            <span className="tabular text-right text-xs text-ink-2">{d.value}</span>
            <span role="tooltip" className="pointer-events-none absolute -top-8 left-36 z-10 hidden whitespace-nowrap rounded-md border border-line bg-surface px-2 py-1 text-xs text-ink shadow-sm group-hover:block">
              {d.label}: <b className="tabular">{d.value}</b> {unit}{d.hint ? ` · ${d.hint}` : ""}
            </span>
          </li>
        ))}
      </ul>
      <TableView data={data} unit={unit} />
    </div>
  );
}

export function Columns({ data, unit = "" }: { data: Datum[]; unit?: string }) {
  const max = Math.max(...data.map((d) => d.value), 1);
  return (
    <div>
      <div className="flex h-36 items-end gap-[2px] border-b border-line-strong">
        {data.map((d) => (
          <div key={d.label} className="group relative flex h-full flex-1 flex-col justify-end">
            <div className="mx-auto w-full max-w-8 rounded-t-[4px] bg-[var(--series-1)] group-hover:opacity-80"
              style={{ height: `${d.value ? Math.max(3, (100 * d.value) / max) : 0}%` }} />
            <span role="tooltip" className="pointer-events-none absolute -top-7 left-1/2 z-10 hidden -translate-x-1/2 whitespace-nowrap rounded-md border border-line bg-surface px-2 py-1 text-xs shadow-sm group-hover:block">
              {d.label}: <b className="tabular">{d.value}</b> {unit}
            </span>
          </div>
        ))}
      </div>
      <div className="mt-1 flex gap-[2px] text-[10px] text-ink-3">
        {data.map((d, i) => <span key={d.label} className="flex-1 truncate text-center">{i % 2 === 0 ? d.label : ""}</span>)}
      </div>
      <TableView data={data} unit={unit} />
    </div>
  );
}
