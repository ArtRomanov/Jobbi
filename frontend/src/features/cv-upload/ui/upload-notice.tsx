import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { colors } from "@/shared/ui";
import { readUploadNotice } from "../model/upload-notice-state";

export const UPLOAD_NOTICE_TEXT =
  "Text extracted from your file. Check the line breaks and save.";
export const UPLOAD_CUT_TEXT =
  "The text was longer than 20 000 characters and was cut.";
export const UPLOAD_BASE_TEXT = "This CV is now your base CV.";

/**
 * Notice shown in the CV editor right after an upload. Renders nothing unless
 * the router state carries `uploadNotice` (set by `UploadCvButton`).
 *
 * Shown once: the notice is kept in component state and the router state is
 * cleared right away (replace, same URL), so a reload or coming back through
 * history does not show it again.
 */
export function UploadNotice() {
  const location = useLocation();
  const navigate = useNavigate();
  const [notice] = useState(() => readUploadNotice(location.state));
  const hasRouterNotice = readUploadNotice(location.state) !== null;

  useEffect(() => {
    if (!hasRouterNotice) return;
    void navigate(
      { pathname: location.pathname, search: location.search, hash: location.hash },
      { replace: true, state: null },
    );
  }, [hasRouterNotice, location.pathname, location.search, location.hash, navigate]);

  if (!notice) return null;

  return (
    <div
      role="status"
      style={{
        padding: "0.75rem 1rem",
        marginBottom: "1rem",
        borderRadius: "0.375rem",
        border: `1px solid ${colors.border}`,
        backgroundColor: colors.bgCard,
        color: colors.textPrimary,
        fontSize: "0.875rem",
      }}
    >
      <p style={{ margin: 0 }}>{UPLOAD_NOTICE_TEXT}</p>
      {notice.truncated && <p style={{ margin: "0.25rem 0 0" }}>{UPLOAD_CUT_TEXT}</p>}
      {notice.becameBase && (
        <p style={{ margin: "0.25rem 0 0" }}>{UPLOAD_BASE_TEXT}</p>
      )}
    </div>
  );
}
