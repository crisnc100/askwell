// The value calculator's arithmetic, kept free of the DOM so the unit tests can import it
// (web/e2e/value-formula.spec.ts).

export interface ReaderInputs {
  questions: number;
  minutesByHand: number;
  minutesToCheck: number;
  costPerHour: number;
  wrongCost: number;
  hosting: number;
}

export interface Measured {
  costPerQuestion: number;
  answeredShare: number;
  wrongRate: number;
}

export interface Monthly {
  runningCost: number;
  answered: number;
  hoursSaved: number;
  valueOfTime: number;
  risk: number;
  net: number;
}

export interface InputSpec {
  key: keyof ReaderInputs;
  label: string;
  unit: "count" | "minutes" | "usd";
  min: number;
  max: number;
  step: number;
  example: number;
}

export const INPUTS: InputSpec[] = [
  { key: "questions", label: "Questions a month", unit: "count", min: 0, max: 10000, step: 10, example: 500 },
  { key: "minutesByHand", label: "Minutes a person takes to answer one question by hand", unit: "minutes", min: 0, max: 240, step: 1, example: 20 },
  { key: "minutesToCheck", label: "Minutes to check an answer Askwell gives", unit: "minutes", min: 0, max: 240, step: 1, example: 2 },
  { key: "costPerHour", label: "That person's cost per hour", unit: "usd", min: 0, max: 500, step: 1, example: 60 },
  { key: "wrongCost", label: "What one wrong answer costs when someone acts on it", unit: "usd", min: 0, max: 10000, step: 10, example: 200 },
  { key: "hosting", label: "Hosting per month", unit: "usd", min: 0, max: 1000, step: 1, example: 10 },
];

// Infinity clamps to a bound like any other out-of-range number; the caller rejects NaN.
export function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

// A refused question goes back to a person, so it saves nothing; its model cost is
// already inside cost per question.
export function monthly(reader: ReaderInputs, measured: Measured): Monthly {
  const runningCost = reader.questions * measured.costPerQuestion + reader.hosting;
  const answered = reader.questions * measured.answeredShare;
  const hoursSaved = (answered * (reader.minutesByHand - reader.minutesToCheck)) / 60;
  const valueOfTime = hoursSaved * reader.costPerHour;
  const risk = answered * measured.wrongRate * reader.wrongCost;
  return { runningCost, answered, hoursSaved, valueOfTime, risk, net: valueOfTime - risk - runningCost };
}

// Net value at the low and the high end of the wrong-answer rate's 95% interval.
export function range(
  reader: ReaderInputs,
  measured: { costPerQuestion: number; answeredShare: number; wrongInterval: [number, number] },
): [number, number] {
  const at = (wrongRate: number) =>
    monthly(reader, { costPerQuestion: measured.costPerQuestion, answeredShare: measured.answeredShare, wrongRate }).net;
  return [at(measured.wrongInterval[0]), at(measured.wrongInterval[1])];
}
