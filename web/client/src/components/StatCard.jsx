export default function StatCard({ label, value, detail, tone = "frost" }) {
  return <article className={`stat-card ${tone}`}>
    <span>{label}</span>
    <strong>{value ?? "—"}</strong>
    {detail && <small>{detail}</small>}
  </article>;
}
