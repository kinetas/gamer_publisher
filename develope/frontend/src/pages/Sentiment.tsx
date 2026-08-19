import { useEffect, useState } from "react";
import { Header } from "../components/Header";
import { Footer } from "../components/Footer";
import { SentimentCard } from "../components/SentimentCard";
import { fetchSentimentList } from "../api";
import type { SentimentReport } from "../types";

export default function Sentiment() {
  const [reports, setReports] = useState<SentimentReport[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchSentimentList()
      .then(setReports)
      .catch(() => setError("감성분석 리포트를 불러오지 못했습니다."));
  }, []);

  return (
    <div style={{ minHeight: "100%", display: "flex", flexDirection: "column" }}>
      <Header />

      <div style={{ flex: 1, display: "flex", justifyContent: "center" }}>
        <main style={{ width: "100%", maxWidth: "var(--page-width)", padding: "40px 24px" }}>
          <h2 style={{ margin: "0 0 20px", fontSize: 20, fontWeight: 700 }}>감성분석</h2>
          <p style={{ margin: "0 0 24px", fontSize: 13, color: "var(--color-text-muted)" }}>
            Steam 리뷰를 긍정/부정/중립으로 1차 분류한 뒤, LLM이 평가 배경을 요약합니다.
          </p>

          {error && <p style={{ color: "var(--color-text-muted)" }}>{error}</p>}
          {!error && !reports && <p style={{ color: "var(--color-text-muted)" }}>불러오는 중...</p>}
          {!error && reports && reports.length === 0 && (
            <p style={{ color: "var(--color-text-muted)" }}>표시할 감성분석 리포트가 없습니다.</p>
          )}

          {reports && reports.length > 0 && (
            <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
              {reports.map((report) => (
                <SentimentCard key={report.appid} report={report} />
              ))}
            </div>
          )}
        </main>
      </div>

      <Footer />
    </div>
  );
}
