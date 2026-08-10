const DATA_SOURCES = [
  { name: "Steam Web API", url: "https://steamcommunity.com/dev" },
  { name: "SteamSpy API", url: "https://steamspy.com/api.php" },
  { name: "Steam Store", url: "https://store.steampowered.com" },
];

export function Footer() {
  return (
    <footer
      style={{
        borderTop: "1px solid var(--color-border)",
        background: "var(--color-surface)",
        padding: "20px 32px",
        color: "var(--color-text-muted)",
        fontSize: 13,
      }}
    >
      <div style={{ marginBottom: 8 }}>Data sources</div>
      <ul style={{ display: "flex", gap: 20, listStyle: "none", padding: 0, margin: 0, flexWrap: "wrap" }}>
        {DATA_SOURCES.map((source) => (
          <li key={source.name}>
            <a href={source.url} target="_blank" rel="noreferrer">
              {source.name}
            </a>
          </li>
        ))}
      </ul>
    </footer>
  );
}
