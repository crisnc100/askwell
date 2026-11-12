// How the numbers in an answer are built, read from the intent the model returned: each
// ratio's formula and each series' date field. The intent is untrusted model output, so
// every field is checked before it is used, and anything unexpected is skipped.

type Json = Record<string, unknown>;

function isObject(value: unknown): value is Json {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function text(value: unknown): string | null {
  return typeof value === "string" && value ? value : null;
}

export function formulaLines(intent: unknown): string[] {
  if (!isObject(intent)) return [];
  const lines: string[] = [];
  const metrics = Array.isArray(intent.metrics) ? intent.metrics : [];
  for (const metric of metrics) {
    if (!isObject(metric) || metric.agg !== "ratio") continue;
    const numerator = text(metric.numerator);
    const denominator = text(metric.denominator);
    if (!numerator || !denominator) continue;
    const name = text(metric.alias) ?? "ratio";
    const scale = metric.as_percent === true ? " × 100" : "";
    lines.push(`${name} = ${numerator} ÷ ${denominator}${scale} (empty when ${denominator} is 0)`);
  }
  const series = Array.isArray(intent.series) ? intent.series : [];
  for (const item of series) {
    if (!isObject(item)) continue;
    const dateField = text(item.date_field);
    const metric = isObject(item.metric) ? item.metric : {};
    const agg = text(metric.agg);
    if (!dateField || !agg) continue;
    const name = text(item.alias) ?? "series";
    const field = text(metric.field);
    const what = field ? `${agg} of ${field}` : `${agg} of rows`;
    const own = Array.isArray(item.where) && item.where.length ? ", with its own conditions" : "";
    lines.push(`${name}: ${what}, by ${dateField}${own}`);
  }
  return lines;
}
