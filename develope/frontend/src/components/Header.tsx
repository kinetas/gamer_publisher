import type { CSSProperties } from "react";
import { NavLink } from "react-router-dom";
import { PlaceholderImage } from "./PlaceholderImage";

const navLinkStyle = ({ isActive }: { isActive: boolean }): CSSProperties => ({
  fontSize: 14,
  fontWeight: 600,
  textDecoration: "none",
  padding: "6px 12px",
  borderRadius: 6,
  color: isActive ? "var(--color-text)" : "var(--color-text-muted)",
  background: isActive ? "var(--color-surface-raised)" : "transparent",
});

export function Header() {
  return (
    <header
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: 12,
        padding: "16px 32px",
        borderBottom: "1px solid var(--color-border)",
        background: "var(--color-surface)",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <PlaceholderImage width="36px" height="36px" />
        <span style={{ fontSize: 18, fontWeight: 700, letterSpacing: "0.02em" }}>
          gamer_publisher
        </span>
      </div>
      <nav style={{ display: "flex", alignItems: "center", gap: 4 }}>
        <NavLink to="/" end style={navLinkStyle}>
          명작 아카이브
        </NavLink>
        <NavLink to="/news" style={navLinkStyle}>
          RSS 뉴스
        </NavLink>
        <NavLink to="/sentiment" style={navLinkStyle}>
          감성분석
        </NavLink>
      </nav>
    </header>
  );
}
