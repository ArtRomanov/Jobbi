import type { ChangeCard } from "@/entities/chat";
import { CvChangeCard } from "./cv-change-card";

interface CardListProps {
  applicationId: string;
  cards: ChangeCard[] | undefined;
  /** The message is not the newest one: its cards cannot be decided. */
  outdated: boolean;
  onCardUpdated: (card: ChangeCard) => void;
}

/** The change cards of one assistant message, in order, under its bubble. */
export function CardList({
  applicationId,
  cards,
  outdated,
  onCardUpdated,
}: CardListProps) {
  if (!cards || cards.length === 0) return null;
  return (
    <div
      style={{
        alignSelf: "flex-start",
        width: "80%",
        display: "flex",
        flexDirection: "column",
        gap: "0.5rem",
      }}
    >
      {cards.map((card, index) => (
        <CvChangeCard
          key={card.id}
          applicationId={applicationId}
          card={card}
          number={index + 1}
          outdated={outdated}
          onCardUpdated={onCardUpdated}
        />
      ))}
    </div>
  );
}
