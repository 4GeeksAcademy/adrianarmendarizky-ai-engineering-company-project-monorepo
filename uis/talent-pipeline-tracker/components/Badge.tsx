// A small pill for showing status/stage labels with a subtle color cue.
// Purely presentational.

interface BadgeProps {
  label: string;
  tone?: "neutral" | "blue" | "green" | "red" | "amber";
}

const TONES: Record<string, string> = {
  neutral: "bg-gray-100 text-gray-700",
  blue: "bg-blue-100 text-blue-800",
  green: "bg-green-100 text-green-800",
  red: "bg-red-100 text-red-800",
  amber: "bg-amber-100 text-amber-800",
};

export default function Badge({ label, tone = "neutral" }: BadgeProps) {
  return (
    <span className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-medium ${TONES[tone]}`}>
      {label}
    </span>
  );
}