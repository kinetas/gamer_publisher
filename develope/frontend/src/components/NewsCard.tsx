import type { NewsArticle } from "../types";
import { PlaceholderImage } from "./PlaceholderImage";

interface NewsCardProps {
  article: NewsArticle;
}

function formatPubDate(pubDate: string | null): string | null {
  if (!pubDate) return null;
  const parsed = new Date(pubDate);
  if (Number.isNaN(parsed.getTime())) return pubDate;
  return parsed.toLocaleDateString("ko-KR", { year: "numeric", month: "2-digit", day: "2-digit" });
}

export function NewsCard({ article }: NewsCardProps) {
  const displayDate = formatPubDate(article.pubDate);

  return (
    <div
      style={{
        display: "flex",
        gap: 16,
        padding: 16,
        border: "1px solid var(--color-border)",
        background: "var(--color-surface)",
      }}
    >
      <div style={{ width: 160, flexShrink: 0, aspectRatio: "16 / 9" }}>
        <PlaceholderImage src={article.imageUrl ?? undefined} alt={article.title} />
      </div>
      <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column" }}>
        <p
          style={{
            margin: "0 0 6px",
            fontSize: 12,
            color: "var(--color-text-muted)",
            display: "flex",
            gap: 8,
          }}
        >
          <span>{article.source}</span>
          {displayDate && <span>· {displayDate}</span>}
        </p>
        <h4 style={{ margin: "0 0 8px", fontSize: 16, fontWeight: 700, lineHeight: 1.4 }}>
          {article.title}
        </h4>
        <p
          style={{
            margin: "0 0 12px",
            fontSize: 13,
            lineHeight: 1.6,
            color: "var(--color-text)",
            flex: 1,
          }}
        >
          {article.excerpt ?? "요약이 제공되지 않았습니다."}
        </p>
        {article.link ? (
          <a
            href={article.link}
            target="_blank"
            rel="noreferrer"
            style={{
              alignSelf: "flex-start",
              fontSize: 13,
              fontWeight: 600,
              color: "var(--color-accent)",
              textDecoration: "none",
            }}
          >
            원문 보기 →
          </a>
        ) : (
          <span style={{ fontSize: 13, color: "var(--color-text-muted)" }}>원문 링크 없음</span>
        )}
      </div>
    </div>
  );
}
