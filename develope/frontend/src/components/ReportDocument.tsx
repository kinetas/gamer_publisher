import type { WeeklyReport, GameEntry } from "../types";
import { PageSheet } from "./PageSheet";
import { GameGrid } from "./GameGrid";
import { GameDetailRow } from "./GameDetailRow";
import { chunk } from "../utils/chunk";

const DETAIL_ITEMS_PER_PAGE = 4;

interface DetailSectionSpec {
  title: string;
  games: GameEntry[];
}

interface ReportDocumentProps {
  report: WeeklyReport;
}

export function ReportDocument({ report }: ReportDocumentProps) {
  const sections: DetailSectionSpec[] = [
    { title: "옛 게임 추천", games: report.oldIntroductions },
    { title: "다시 추천", games: report.recentReplays },
    { title: "신규 추천", games: report.recentNew },
  ];

  let pageNumber = 1;

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
        const pages = chunk(section.games, DETAIL_ITEMS_PER_PAGE);
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
