import { useEffect, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { fetchNews, fetchReport, fetchSentimentList } from "../api";
import { ReportDocument, countReportPages } from "../components/ReportDocument";
import { NewsPrintSection, countNewsPages } from "../components/NewsPrintSection";
import { SentimentPrintSection } from "../components/SentimentPrintSection";
import type { NewsArticle, SentimentReport, WeeklyReport } from "../types";

/** 헤더/사이드바/푸터 없는 순수 리포트 페이지. 두 가지 용도로 쓰인다:
 * 1) fastapi-server의 /reports/archive-current가 헤드리스 브라우저로 이 페이지를
 *    열어 page.pdf()로 캡처 -> MinIO 보관용 PDF.
 * 2) 아직 archive 안 된(=MinIO에 파일이 없는) 리포트를 사용자가 바로 받고 싶을 때,
 *    ?print=1로 열면 로드 후 브라우저 인쇄 다이얼로그(다른 이름으로 저장 -> PDF)를
 *    띄운다 (Sidebar.tsx 참고).
 *
 * 주간 PDF 아카이브 정책: 명작 아카이브 / RSS 뉴스 / 감성분석 3섹션을 하나로 묶어
 * 이어붙여 렌더링한다 (페이지 번호도 섹션을 넘어 계속 이어짐).
 */
export default function PrintReport() {
  const { id } = useParams<{ id: string }>();
  const [searchParams] = useSearchParams();
  const [report, setReport] = useState<WeeklyReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [news, setNews] = useState<NewsArticle[] | null>(null);
  const [sentiment, setSentiment] = useState<SentimentReport[] | null>(null);

  useEffect(() => {
    if (!id) return;
    fetchReport(id)
      .then(setReport)
      .catch(() => setError("리포트를 불러오지 못했습니다."));
  }, [id]);

  useEffect(() => {
    fetchNews()
      .then(setNews)
      .catch(() => setNews([]));
  }, []);

  useEffect(() => {
    fetchSentimentList()
      .then(setSentiment)
      .catch(() => setSentiment([]));
  }, []);

  const allLoaded = report !== null && news !== null && sentiment !== null;

  useEffect(() => {
    if (allLoaded && searchParams.get("print") === "1") {
      window.print();
    }
  }, [allLoaded, searchParams]);

  if (error) return <p style={{ padding: 40 }}>{error}</p>;
  if (!allLoaded) return <p style={{ padding: 40 }}>불러오는 중...</p>;

  const newsStartPage = countReportPages(report) + 1;
  const sentimentStartPage = newsStartPage + countNewsPages(news);

  return (
    <div style={{ padding: "40px 0" }}>
      <ReportDocument report={report} />
      <NewsPrintSection articles={news} startPage={newsStartPage} />
      <SentimentPrintSection reports={sentiment} startPage={sentimentStartPage} />
    </div>
  );
}
