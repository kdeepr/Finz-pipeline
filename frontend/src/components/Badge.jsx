export function Badge({ value }) {
  if (!value) return null;
  return <span className={`badge ${value}`}>{value.replace(/_/g, " ")}</span>;
}

export function money(n) {
  if (n === null || n === undefined) return "-";
  const sign = n < 0 ? "-" : "";
  return `${sign}$${Math.abs(n).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}
