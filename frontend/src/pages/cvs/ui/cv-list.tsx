import type { Cv } from "@/entities/cv";
import type { CvRowActions } from "../model/types";
import { CvRow } from "./cv-row";

interface CvListProps extends CvRowActions {
  cvs: readonly Cv[];
  duplicatingId: string | null;
  downloadingId: string | null;
  deletingId: string | null;
}

/** The rows of one CVs-page section. */
export function CvList({ cvs, duplicatingId, downloadingId, deletingId, ...actions }: CvListProps) {
  return (
    <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
      {cvs.map((cv) => (
        <CvRow
          key={cv.id}
          cv={cv}
          isDuplicating={duplicatingId === cv.id}
          isDownloading={downloadingId === cv.id}
          isDeleting={deletingId === cv.id}
          {...actions}
        />
      ))}
    </ul>
  );
}
