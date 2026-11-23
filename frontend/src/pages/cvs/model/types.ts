import type { Cv } from "@/entities/cv";

/** Row actions the page hands to every CV row (stable callbacks). */
export interface CvRowActions {
  onDuplicate: (cv: Cv) => void;
  onDownload: (cv: Cv) => void;
  onDelete: (cv: Cv) => void;
  onMadeBase: (cv: Cv) => void;
}
