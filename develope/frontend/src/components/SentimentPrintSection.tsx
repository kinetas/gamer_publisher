import type { SentimentReport } from "../types";
import { PageSheet } from "./PageSheet";
import { chunkBalanced } from "../utils/chunk";

const SENTIMENT_ITEMS_PER_PAGE = 3;

interface SentimentPrintSectionProps {
  reports: SentimentReport[];
  startPage: number;
}

function formatGeneratedAt(generatedAt: string): string {
  const parsed = new Date(generatedAt);
  if (Number.isNaN(parsed.getTime())) return generatedAt;
  return parsed.toLocaleString("ko-KR", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** 인쇄용 순수 함수: 이 섹션이 차지할 총 페이지 수 (빈 배열이어도 최소 1장). */
export function countSentimentPages(
  reports: SentimentReport[],
  itemsPerPage: number = SENTIMENT_ITEMS_PER_PAGE
): number {
  if (reports.length === 0) return 1;
  return chunkBalanced(reports, itemsPerPage).length;
}

function SentimentPrintRow({ report }: { report: SentimentReport }) {
  const total = report.positiveCount + report.negativeCount + report.neutralCount;
  const positivePct = total > 0 ? (report.positiveCount / total) * 100 : 0;
  const negativePct = total > 0 ? (report.negativeCount / total) * 100 : 0;
  const neutralPct = total > 0 ? (report.neutralCount / total) * 100 : 0;

  return (
    <div style={{ marginBottom: 24 }}>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "baseline",
          gap: 12,
          marginBottom: 8,
        }}
      >
        <h4 style={{ margin: 0, fontSize: 16, fontWeight: 700 }}>{report.name}</h4>
        <span style={{ fontSize: 12, color: "var(--color-text-muted)" }}>
          리뷰 {report.reviewCount.toLocaleString("ko-KR")}건
        </span>
      </div>

      <div
        style={{
          display: "flex",
          height: 8,
          width: "100%",
          overflow: "hidden",
          background: "var(--color-surface-raised)",
          marginBottom: 8,
        }}
      >
        {total > 0 ? (
          <>
            <div style={{ width: `${positivePct}%`, background: "var(--color-positive)" }} />
            <div style={{ width: `${neutralPct}%`, background: "var(--color-text-muted)" }} />
            <div style={{ width: `${negativePct}%`, background: "var(--color-negative)" }} />
          </>
        ) : null}
      </div>

      <div
        style={{
          display: "flex",
          gap: 16,
          fontSize: 12,
          color: "var(--color-text-muted)",
          marginBottom: 8,
        }}
      >
        <span style={{ color: "var(--color-positive)" }}>긍정 {report.positiveCount.toLocaleString("ko-KR")}</span>
        <span>중립 {report.neutralCount.toLocaleString("ko-KR")}</span>
        <span style={{ color: "var(--color-negative)" }}>부정 {report.negativeCount.toLocaleString("ko-KR")}</span>
      </div>

      <p style={{ margin: "0 0 6px", fontSize: 13, lineHeight: 1.6, color: "var(--color-text)" }}>
        {report.summary ?? "아직 요약이 생성되지 않았습니다."}
      </p>

      <p style={{ margin: 0, fontSize: 11, color: "var(--color-text-muted)" }}>
        분석 생성 시각: {formatGeneratedAt(report.generatedAt)}
      </p>
    </div>
  );
}

export function SentimentPrintSection({ reports, startPage }: SentimentPrintSectionProps) {
  const pages = reports.length > 0 ? chunkBalanced(reports, SENTIMENT_ITEMS_PER_PAGE) : [[]];
  let pageNumber = startPage;

  return (
    <div>
      {pages.map((pageReports, pageIndex) => (
        <PageSheet key={`sentiment-${pageIndex}`} pageLabel={`PAGE ${pageNumber++}`}>
          <h2
            style={{
              fontSize: 20,
              fontWeight: 700,
              margin: "0 0 24px",
              paddingBottom: 12,
              borderBottom: "2px solid var(--color-accent)",
            }}
          >
            감성분석
            {pageIndex > 0 ? " (계속)" : ""}
          </h2>
          {pageReports.length > 0 ? (
            pageReports.map((report) => <SentimentPrintRow key={report.appid} report={report} />)
          ) : (
            <p style={{ fontSize: 13, color: "var(--color-text-muted)" }}>표시할 감성분석 결과가 없습니다.</p>
          )}
        </PageSheet>
      ))}
    </div>
  );
}
