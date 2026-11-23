import { Link } from "react-router-dom";
import { ROUTES } from "@/shared/config";
import { colors } from "@/shared/ui";
import type { Cv } from "../model/types";
import { APPLICATION_DELETED_TEXT, formatTailoredFor } from "../lib/tailored-for";

interface CvTailoredForProps {
  cv: Pick<Cv, "tailored_for" | "tailored_application_deleted">;
}

/**
 * The application a tailored copy was made for: "<Company> — <Role>" linking
 * to the dashboard with that application's panel open, or "Application deleted".
 */
export function CvTailoredFor({ cv }: CvTailoredForProps) {
  const target = cv.tailored_application_deleted ? null : cv.tailored_for;
  if (!target) {
    return <span style={{ color: colors.textMuted }}>{APPLICATION_DELETED_TEXT}</span>;
  }
  return (
    <Link
      to={ROUTES.dashboardApplication(target.application_id)}
      style={{ color: colors.primary, textDecoration: "none" }}
    >
      {formatTailoredFor(target)}
    </Link>
  );
}
