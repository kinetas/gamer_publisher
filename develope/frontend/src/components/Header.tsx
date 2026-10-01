import { PlaceholderImage } from "./PlaceholderImage";

export function Header() {
  return (
    <header
      style={{
        display: "flex",
        alignItems: "center",
        gap: 12,
        padding: "16px 32px",
        borderBottom: "1px solid var(--color-border)",
        background: "var(--color-surface)",
      }}
    >
      <PlaceholderImage width="36px" height="36px" />
      <span style={{ fontSize: 18, fontWeight: 700, letterSpacing: "0.02em" }}>
        gamer_publisher
      </span>
    </header>
  );
}
