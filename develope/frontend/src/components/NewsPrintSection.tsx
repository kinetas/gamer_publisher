import type { NewsArticle } from "../types";
import { PageSheet } from "./PageSheet";
import { PlaceholderImage } from "./PlaceholderImage";

interface NewsPrintSectionProps {
  articles: NewsArticle[];
}

function formatPubDate(pubDate: string | null): string | null {
  if (!pubDate) return null;
  const parsed = new Date(pubDate);
  if (Number.isNaN(parsed.getTime())) return pubDate;
  return parsed.toLocaleDateString("ko-KR", { year: "numeric", month: "2-digit", day: "2-digit" });
}

function NewsPrintRow({ article }: { article: NewsArticle }) {
  const displayDate = formatPubDate(article.pubDate);
  return (
    <div className="print-row" style={{ display: "flex", gap: 20, marginBottom: 24 }}>
      <div style={{ width: 140, flexShrink: 0, aspectRatio: "16 / 9" }}>
        <PlaceholderImage src={article.imageUrl ?? undefined} alt={article.title} />
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
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
        <h4 style={{ margin: "0 0 6px", fontSize: 16, fontWeight: 700, lineHeight: 1.4 }}>
          {article.title}
        </h4>
        <p style={{ margin: "0 0 6px", fontSize: 13, lineHeight: 1.6, color: "var(--color-text)" }}>
          {article.excerpt ?? "요약이 제공되지 않았습니다."}
        </p>
        <span style={{ fontSize: 11, color: "var(--color-text-muted)", wordBreak: "break-all" }}>
          {article.link ?? "원문 링크 없음"}
        </span>
      </div>
    </div>
  );
}

export function NewsPrintSection({ articles }: NewsPrintSectionProps) {
  return (
    <PageSheet breakBefore>
      <h2
        style={{
          fontSize: 20,
          fontWeight: 700,
          margin: "0 0 24px",
          paddingBottom: 12,
          borderBottom: "2px solid var(--color-accent)",
        }}
      >
        RSS 뉴스
      </h2>
      {articles.length > 0 ? (
        articles.map((article) => <NewsPrintRow key={article.id} article={article} />)
      ) : (
        <p style={{ fontSize: 13, color: "var(--color-text-muted)" }}>표시할 뉴스가 없습니다.</p>
      )}
    </PageSheet>
  );
}
