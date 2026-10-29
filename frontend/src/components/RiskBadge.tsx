import type { RiskLevel } from "../api";
import { COLOR, LABEL } from "../risk";

export function RiskBadge({ level }: { level: RiskLevel }) {
  return (
    <span className="badge">
      <span className="dot" style={{ background: COLOR[level] }} aria-hidden />
      {LABEL[level]}
    </span>
  );
}
