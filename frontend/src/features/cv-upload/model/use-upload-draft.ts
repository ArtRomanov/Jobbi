import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { readUploadDraft, type UploadDraft } from "./upload-draft-state";

/**
 * The upload draft handed to `/cvs/new` in router state, or `null`.
 *
 * Read once into component state, then the router state is cleared at once
 * (same URL, `replace`). Browsers keep `history.state` across a reload, so
 * without the clear a reload would bring the draft back; with it, a reload
 * (after the browser's leave prompt) opens an empty new CV. The draft itself
 * lives on in this hook's state (and in the editor), so the replace does not
 * lose it; the unsaved-changes guard lets `REPLACE` through.
 */
export function useUploadDraft(): UploadDraft | null {
  const location = useLocation();
  const navigate = useNavigate();
  const [draft] = useState(() => readUploadDraft(location.state));
  const hasRouterDraft = readUploadDraft(location.state) !== null;

  useEffect(() => {
    if (!hasRouterDraft) return;
    void navigate(
      { pathname: location.pathname, search: location.search, hash: location.hash },
      { replace: true, state: null },
    );
  }, [hasRouterDraft, location.pathname, location.search, location.hash, navigate]);

  return draft;
}
