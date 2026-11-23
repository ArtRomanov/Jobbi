import type { ChangeCard } from "@/entities/chat";
import { CvChangeCard } from "./cv-change-card";

interface CardListProps {
  applicationId: string;
  cards: ChangeCard[] | undefined;
  onCardUpdated: (card: ChangeCard) => void;
}

/** The change cards of one assistant message, in order, under its bubble. */
export function CardList({ applicationId, cards, onCardUpdated }: CardListProps) {
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
      {cards.map((card) => (
        <CvChangeCard
          key={card.id}
          applicationId={applicationId}
          card={card}
          onCardUpdated={onCardUpdated}
        />
      ))}
    </div>
  );
}
