import type { NewsArticle } from "../types";
import { PageSheet } from "./PageSheet";
import { PlaceholderImage } from "./PlaceholderImage";
import { chunkBalanced } from "../utils/chunk";

const NEWS_ITEMS_PER_PAGE = 4;

interface NewsPrintSectionProps {
  articles: NewsArticle[];
  startPage: number;
}

function formatPubDate(pubDate: string | null): string | null {
  if (!pubDate) return null;
  const parsed = new Date(pubDate);
  if (Number.isNaN(parsed.getTime())) return pubDate;
  return parsed.toLocaleDateString("ko-KR", { year: "numeric", month: "2-digit", day: "2-digit" });
}

/** 인쇄용 순수 함수: 이 섹션이 차지할 총 페이지 수 (빈 배열이어도 최소 1장). */
export function countNewsPages(articles: NewsArticle[], itemsPerPage: number = NEWS_ITEMS_PER_PAGE): number {
  if (articles.length === 0) return 1;
  return chunkBalanced(articles, itemsPerPage).length;
}

function NewsPrintRow({ article }: { article: NewsArticle }) {
  const displayDate = formatPubDate(article.pubDate);
  return (
    <div style={{ display: "flex", gap: 20, marginBottom: 24 }}>
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

export function NewsPrintSection({ articles, startPage }: NewsPrintSectionProps) {
  const pages = articles.length > 0 ? chunkBalanced(articles, NEWS_ITEMS_PER_PAGE) : [[]];
  let pageNumber = startPage;

  return (
    <div>
      {pages.map((pageArticles, pageIndex) => (
        <PageSheet key={`news-${pageIndex}`} pageLabel={`PAGE ${pageNumber++}`}>
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
            {pageIndex > 0 ? " (계속)" : ""}
          </h2>
          {pageArticles.length > 0 ? (
            pageArticles.map((article) => <NewsPrintRow key={article.id} article={article} />)
          ) : (
            <p style={{ fontSize: 13, color: "var(--color-text-muted)" }}>표시할 뉴스가 없습니다.</p>
          )}
        </PageSheet>
      ))}
    </div>
  );
}
