import { useEffect, useState } from "react";
import { Header } from "../components/Header";
import { Footer } from "../components/Footer";
import { Sidebar } from "../components/Sidebar";
import { ReportDocument } from "../components/ReportDocument";
import { fetchLatestReport, fetchReportList } from "../api";
import type { ReportListItem, WeeklyReport } from "../types";

export default function Dashboard() {
  const [report, setReport] = useState<WeeklyReport | null>(null);
  const [reportList, setReportList] = useState<ReportListItem[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchLatestReport()
      .then(setReport)
      .catch(() => setError("아직 생성된 리포트가 없습니다."));
    fetchReportList()
      .then(setReportList)
      .catch(() => {
        /* 사이드바는 비어있어도 페이지 전체를 막을 이유가 없음 */
      });
  }, []);

  return (
    <div style={{ minHeight: "100%", display: "flex", flexDirection: "column" }}>
      <Header />

      <div style={{ flex: 1, display: "flex" }}>
        <main style={{ flex: 1, padding: "40px 24px" }}>
          {error && <p style={{ color: "var(--color-text-muted)" }}>{error}</p>}
          {!error && !report && <p style={{ color: "var(--color-text-muted)" }}>불러오는 중...</p>}
          {report && <ReportDocument report={report} />}
        </main>
        <Sidebar reports={reportList} />
      </div>

      <Footer />
    </div>
  );
}
