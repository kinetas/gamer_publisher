import { useEffect, useState } from "react";
import { Header } from "../components/Header";
import { Footer } from "../components/Footer";
import { NewsCard } from "../components/NewsCard";
import { fetchNews } from "../api";
import type { NewsArticle } from "../types";

export default function News() {
  const [articles, setArticles] = useState<NewsArticle[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchNews()
      .then(setArticles)
      .catch(() => setError("뉴스를 불러오지 못했습니다."));
  }, []);

  return (
    <div style={{ minHeight: "100%", display: "flex", flexDirection: "column" }}>
      <Header />

      <div style={{ flex: 1, display: "flex", justifyContent: "center" }}>
        <main style={{ width: "100%", maxWidth: "var(--page-width)", padding: "40px 24px" }}>
          <h2 style={{ margin: "0 0 20px", fontSize: 20, fontWeight: 700 }}>RSS 뉴스</h2>
          <p style={{ margin: "0 0 24px", fontSize: 13, color: "var(--color-text-muted)" }}>
            저작권 정책에 따라 요약만 제공합니다. 전문은 원문 링크에서 확인하세요.
          </p>

          {error && <p style={{ color: "var(--color-text-muted)" }}>{error}</p>}
          {!error && !articles && <p style={{ color: "var(--color-text-muted)" }}>불러오는 중...</p>}
          {!error && articles && articles.length === 0 && (
            <p style={{ color: "var(--color-text-muted)" }}>표시할 뉴스가 없습니다.</p>
          )}

          {articles && articles.length > 0 && (
            <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
              {articles.map((article) => (
                <NewsCard key={article.id} article={article} />
              ))}
            </div>
          )}
        </main>
      </div>

      <Footer />
    </div>
  );
}
