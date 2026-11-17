// The committed reports the value calculator reads. Its own file, not value.ts, so the
// unit test can import it without loading the page. web/e2e/value-formula.spec.ts checks
// both ids name complete live reports with an Askwell row for the default model.
export const SOURCE = {
  seen: "v03-seen",
  holdout: "v03-holdout",
  model: "anthropic:claude-haiku-5-5",
  // The report files carry no date; this is the day the commit that added them landed on
  // main (82e0ec8).
  date: "2026-11-16",
} as const;
