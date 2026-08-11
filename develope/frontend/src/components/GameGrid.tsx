import type { GameEntry } from "../types";
import { PlaceholderImage } from "./PlaceholderImage";

const GRID_COLUMNS = 5;

interface GameGridProps {
  title: string;
  games: GameEntry[];
}

export function GameGrid({ title, games }: GameGridProps) {
  return (
    <div style={{ marginBottom: 32 }}>
      <h3
        style={{
          fontSize: 15,
          fontWeight: 700,
          margin: "0 0 14px",
          paddingBottom: 8,
          borderBottom: "1px solid var(--color-border)",
        }}
      >
        {title}
      </h3>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: `repeat(${GRID_COLUMNS}, 1fr)`,
          gap: 12,
        }}
      >
        {games.map((game) => (
          <div key={game.appid}>
            <div style={{ aspectRatio: "3 / 4" }}>
              <PlaceholderImage src={game.image} alt={game.name} />
            </div>
            <p
              style={{
                margin: "6px 0 0",
                fontSize: 12,
                lineHeight: 1.35,
                textAlign: "center",
              }}
            >
              {game.name}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}
