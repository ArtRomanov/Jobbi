import type { Cv } from "@/entities/cv";
import { Button } from "@/shared/ui";
import { MAKE_BASE_LABEL } from "../lib/constants";
import { useMakeBase } from "../model/use-make-base";

interface MakeBaseButtonProps {
  cv: Pick<Cv, "id" | "name">;
  /** Called with the updated CV after a successful make-base (refresh the list). */
  onMadeBase: (cv: Cv) => void;
}

/** "Make base" action for a CV that is not the base (own or tailored). */
export function MakeBaseButton({ cv, onMadeBase }: MakeBaseButtonProps) {
  const { isPending, makeBase } = useMakeBase(cv.id, onMadeBase);
  return (
    <Button
      type="button"
      variant="secondary"
      loading={isPending}
      aria-label={`${MAKE_BASE_LABEL}: ${cv.name}`}
      onClick={() => void makeBase()}
    >
      {MAKE_BASE_LABEL}
    </Button>
  );
}
