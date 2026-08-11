import type { GameEntry } from "../types";
import { PlaceholderImage } from "./PlaceholderImage";

interface GameDetailRowProps {
  game: GameEntry;
}

export function GameDetailRow({ game }: GameDetailRowProps) {
  return (
    <div style={{ display: "flex", gap: 20, marginBottom: 24 }}>
      <div style={{ width: 140, flexShrink: 0, aspectRatio: "3 / 4" }}>
        <PlaceholderImage src={game.image} alt={game.name} />
      </div>
      <div>
        <h4 style={{ margin: "0 0 6px", fontSize: 16, fontWeight: 700 }}>{game.name}</h4>
        <p style={{ margin: "0 0 8px", fontSize: 12, color: "var(--color-text-muted)" }}>
          {game.developer} · CCU {game.ccu.toLocaleString()} · 👍 {game.positive.toLocaleString()} / 👎{" "}
          {game.negative.toLocaleString()}
        </p>
        <p style={{ margin: 0, fontSize: 13, lineHeight: 1.6, color: "var(--color-text)" }}>
          {game.description}
        </p>
      </div>
    </div>
  );
}
