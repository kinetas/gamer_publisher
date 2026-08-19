import type { WeeklyReport, GameEntry } from "../types";
import { PageSheet } from "./PageSheet";
import { GameGrid } from "./GameGrid";
import { GameDetailRow } from "./GameDetailRow";
import { chunkBalanced } from "../utils/chunk";

const DETAIL_ITEMS_PER_PAGE = 4;

interface DetailSectionSpec {
  title: string;
  games: GameEntry[];
}

interface ReportDocumentProps {
  report: WeeklyReport;
  startPage?: number;
}

/** 인쇄용 순수 함수: "명작 아카이브" 섹션(ReportDocument)이 차지할 총 페이지 수. */
export function countReportPages(report: WeeklyReport): number {
  return 1 + chunkBalanced(report.oldIntroductions, DETAIL_ITEMS_PER_PAGE).length;
}

export function ReportDocument({ report, startPage }: ReportDocumentProps) {
  const sections: DetailSectionSpec[] = [
    { title: "명작 아카이브", games: report.oldIntroductions },
  ];

  let pageNumber = startPage ?? 1;

  return (
    <div>
      <PageSheet pageLabel={`PAGE ${pageNumber++}`}>
        <div style={{ marginBottom: 40 }}>
          <div style={{ fontSize: 28, fontWeight: 700, fontFamily: "var(--font-mono)" }}>
            {report.date}
          </div>
          <div
            style={{
              fontSize: 44,
              fontWeight: 800,
              letterSpacing: "0.04em",
              color: "var(--color-accent)",
            }}
          >
            REPORT
          </div>
        </div>

        {sections.map((section) => (
          <GameGrid key={section.title} title={section.title} games={section.games} />
        ))}
      </PageSheet>

      {sections.map((section) => {
        const pages = chunkBalanced(section.games, DETAIL_ITEMS_PER_PAGE);
        return pages.map((pageGames, pageIndex) => (
          <PageSheet key={`${section.title}-${pageIndex}`} pageLabel={`PAGE ${pageNumber++}`}>
            <h2
              style={{
                fontSize: 20,
                fontWeight: 700,
                margin: "0 0 24px",
                paddingBottom: 12,
                borderBottom: "2px solid var(--color-accent)",
              }}
            >
              {section.title}
              {pageIndex > 0 ? " (계속)" : ""}
            </h2>
            {pageGames.map((game) => (
              <GameDetailRow key={game.appid} game={game} />
            ))}
          </PageSheet>
        ));
      })}
    </div>
  );
}
