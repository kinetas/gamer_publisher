import { useEffect, useState } from "react";
import { Header } from "../components/Header";
import { Footer } from "../components/Footer";
import { Sidebar } from "../components/Sidebar";
import { ReportDocument } from "../components/ReportDocument";
import { NewsCard } from "../components/NewsCard";
import { SentimentCard } from "../components/SentimentCard";
import { fetchLatestReport, fetchNews, fetchReportList, fetchSentimentList } from "../api";
import type { NewsArticle, ReportListItem, SentimentReport, WeeklyReport } from "../types";

const sectionHeadingStyle = {
  margin: "0 0 20px",
  fontSize: 20,
  fontWeight: 700,
  paddingBottom: 12,
  borderBottom: "2px solid var(--color-accent)",
} as const;

export default function Dashboard() {
  const [report, setReport] = useState<WeeklyReport | null>(null);
  const [reportList, setReportList] = useState<ReportListItem[]>([]);
  const [reportError, setReportError] = useState<string | null>(null);
  const [news, setNews] = useState<NewsArticle[] | null>(null);
  const [newsError, setNewsError] = useState<string | null>(null);
  const [sentiment, setSentiment] = useState<SentimentReport[] | null>(null);
  const [sentimentError, setSentimentError] = useState<string | null>(null);

  useEffect(() => {
    fetchLatestReport()
      .then(setReport)
      .catch(() => setReportError("아직 생성된 리포트가 없습니다."));
    fetchReportList()
      .then(setReportList)
      .catch(() => {
        /* 사이드바는 비어있어도 페이지 전체를 막을 이유가 없음 */
      });
    fetchNews()
      .then(setNews)
      .catch(() => setNewsError("뉴스를 불러오지 못했습니다."));
    fetchSentimentList()
      .then(setSentiment)
      .catch(() => setSentimentError("감성분석 리포트를 불러오지 못했습니다."));
  }, []);

  return (
    <div style={{ minHeight: "100%", display: "flex", flexDirection: "column" }}>
      <Header />

      <div style={{ flex: 1, display: "flex" }}>
        <main style={{ flex: 1, padding: "40px 24px", display: "flex", flexDirection: "column", gap: 56 }}>
          <section>
            {reportError && <p style={{ color: "var(--color-text-muted)" }}>{reportError}</p>}
            {!reportError && !report && <p style={{ color: "var(--color-text-muted)" }}>불러오는 중...</p>}
            {report && <ReportDocument report={report} />}
          </section>

          <section>
            <h2 style={sectionHeadingStyle}>RSS 뉴스</h2>
            <p style={{ margin: "0 0 24px", fontSize: 13, color: "var(--color-text-muted)" }}>
              저작권 정책에 따라 요약만 제공합니다. 전문은 원문 링크에서 확인하세요.
            </p>
            {newsError && <p style={{ color: "var(--color-text-muted)" }}>{newsError}</p>}
            {!newsError && !news && <p style={{ color: "var(--color-text-muted)" }}>불러오는 중...</p>}
            {!newsError && news && news.length === 0 && (
              <p style={{ color: "var(--color-text-muted)" }}>표시할 뉴스가 없습니다.</p>
            )}
            {news && news.length > 0 && (
              <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                {news.map((article) => (
                  <NewsCard key={article.id} article={article} />
                ))}
              </div>
            )}
          </section>

          <section>
            <h2 style={sectionHeadingStyle}>감성분석</h2>
            <p style={{ margin: "0 0 24px", fontSize: 13, color: "var(--color-text-muted)" }}>
              Steam 리뷰를 긍정/부정/중립으로 1차 분류한 뒤, LLM이 평가 배경을 요약합니다.
            </p>
            {sentimentError && <p style={{ color: "var(--color-text-muted)" }}>{sentimentError}</p>}
            {!sentimentError && !sentiment && <p style={{ color: "var(--color-text-muted)" }}>불러오는 중...</p>}
            {!sentimentError && sentiment && sentiment.length === 0 && (
              <p style={{ color: "var(--color-text-muted)" }}>표시할 감성분석 리포트가 없습니다.</p>
            )}
            {sentiment && sentiment.length > 0 && (
              <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                {sentiment.map((item) => (
                  <SentimentCard key={item.appid} report={item} />
                ))}
              </div>
            )}
          </section>
        </main>
        <Sidebar reports={reportList} />
      </div>

      <Footer />
    </div>
  );
}
