import { useEffect, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { fetchNews, fetchReport, fetchSentimentList } from "../api";
import { ReportDocument } from "../components/ReportDocument";
import { NewsPrintSection } from "../components/NewsPrintSection";
import { SentimentPrintSection } from "../components/SentimentPrintSection";
import type { NewsArticle, SentimentReport, WeeklyReport } from "../types";

/** 헤더/사이드바/푸터 없는 순수 리포트 페이지. 두 가지 용도로 쓰인다:
 * 1) fastapi-server의 /reports/archive-current가 헤드리스 브라우저로 이 페이지를
 *    열어 page.pdf()로 캡처 -> MinIO 보관용 PDF.
 * 2) 아직 archive 안 된(=MinIO에 파일이 없는) 리포트를 사용자가 바로 받고 싶을 때,
 *    ?print=1로 열면 로드 후 브라우저 인쇄 다이얼로그(다른 이름으로 저장 -> PDF)를
 *    띄운다 (Sidebar.tsx 참고).
 *
 * 주간 PDF 아카이브 정책: 명작 아카이브 / RSS 뉴스 / 감성분석 3섹션을 섹션 단위로
 * 새 물리 페이지에서 시작시키고, 섹션 내부의 실제 페이지 분할(몇 장이 될지)과
 * 쪽 번호는 각 섹션이 몇 개씩 들어가는지 미리 추측하지 않고 Chromium의
 * page.pdf({ displayHeaderFooter, footerTemplate }) 쪽 번호 기능에 맡긴다
 * (fastapi-server/app/main.py 참고) — 내용 길이가 달라져도 깨지지 않는다.
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

  // fastapi-server가 networkidle 같은 간접 신호 대신 이 속성 하나만 보고
  // "캡처해도 되는지/실패했는지"를 바로 판단한다 (아래 main.py 참고).
  const printStatus = error ? "error" : allLoaded ? "ready" : "loading";

  return (
    <div data-print-status={printStatus}>
      {error && <p style={{ padding: 40 }}>{error}</p>}
      {!error && !allLoaded && <p style={{ padding: 40 }}>불러오는 중...</p>}
      {!error && allLoaded && (
        <div style={{ padding: "40px 0" }}>
          <ReportDocument report={report} />
          <NewsPrintSection articles={news} />
          <SentimentPrintSection reports={sentiment} />
        </div>
      )}
    </div>
  );
}
