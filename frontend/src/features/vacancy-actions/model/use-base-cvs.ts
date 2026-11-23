import { useEffect, useMemo, useState } from "react";
import { listCvs } from "@/entities/cv";
import type { Cv } from "@/entities/cv";
import type { BaseCvsResult, BaseCvsStatus } from "./types";

const NO_CVS: readonly Cv[] = [];

/** The user's CVs for the dialog's CV select, loaded once per dialog. Default: the base CV, or none. */
export function useBaseCvs(): BaseCvsResult {
  const [cvs, setCvs] = useState<readonly Cv[]>(NO_CVS);
  const [status, setStatus] = useState<BaseCvsStatus>("loading");

  useEffect(() => {
    let isCancelled = false;
    listCvs()
      .then((data) => {
        if (isCancelled) return;
        setCvs(data);
        setStatus("ready");
      })
      .catch(() => {
        if (!isCancelled) setStatus("error");
      });
    return () => {
      isCancelled = true;
    };
  }, []);

  const defaultCvId = useMemo(() => cvs.find((cv) => cv.is_base)?.id ?? null, [cvs]);
  return { cvs, status, defaultCvId };
}
