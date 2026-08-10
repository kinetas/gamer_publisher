import type { GameEntry, ReportListItem, WeeklyReport } from "../types";

// TODO: langgraph-server의 /reports/weekly 구현 후 실제 API로 교체.
// 지금은 이미지가 전부 없어서 GameEntry에 이미지 URL 필드를 아예 안 두고,
// 렌더링 쪽에서 항상 회색 placeholder를 그린다.

function makeEntry(
  appid: number,
  name: string,
  developer: string,
  ccu: number,
  positive: number,
  negative: number,
  description: string
): GameEntry {
  return { appid, name, developer, publisher: developer, positive, negative, ccu, description };
}

export const mockReport: WeeklyReport = {
  date: "2026-08-10",
  oldIntroductions: [
    makeEntry(220, "Half-Life 2", "Valve", 4200, 145000, 2100, "출시된 지 오래됐지만 지금 다시 봐도 레벨 디자인이 압도적입니다. 물리 퍼즐과 스토리텔링의 결합이 여전히 독보적이에요."),
    makeEntry(4000, "Garry's Mod", "Facepunch", 8900, 98000, 3200, "샌드박스 게임의 원형 같은 작품. 커뮤니티 콘텐츠가 아직도 활발하게 올라오고 있습니다."),
    makeEntry(2870, "Tomb Raider: Legend", "Crystal Dynamics", 12, 8200, 410, "동접자는 거의 없지만 평가는 꾸준히 좋은 숨은 명작. 클래식 액션 어드벤처를 좋아한다면 추천."),
    makeEntry(6910, "Deus Ex: Game of the Year Edition", "Ion Storm", 34, 11200, 380, "선택의 자유도가 여전히 놀라운 임멀시브 심. 스텔스/전투 어느 쪽으로도 클리어 가능합니다."),
    makeEntry(1250, "Killing Floor", "Tripwire Interactive", 210, 15400, 900, "협동 좀비 슈터의 원조격. 지금 기준으로도 텐션 있는 웨이브 디펜스를 즐길 수 있어요."),
  ],
  recentReplays: [
    makeEntry(2379780, "Dome Keeper", "Bippinbits", 320, 18900, 650, "지난주에도 소개했지만 여전히 평가가 좋아서 다시 올립니다. 자원 채굴 + 타워디펜스 조합이 중독적이에요."),
    makeEntry(1568590, "Dread Hunger", "Digital Confectioners", 180, 6200, 1100, "선원 vs 배신자 서바이벌. 소규모지만 재밌다는 평이 꾸준합니다."),
  ],
  recentNew: [
    makeEntry(3340780, "Kungfu Card", "Indie Studio", 12, 340, 28, "카드 로그라이크 + 무술 테마 조합. 출시 한 달 지났는데 아직 발견 못 한 사람이 많아 보입니다."),
    makeEntry(4418470, "CHEATED", "Solo Dev", 8, 210, 15, "짧지만 밀도 높은 내러티브 게임. 반전이 좋다는 평이 많아요."),
    makeEntry(1435790, "Escape Simulator", "Pine Studio", 674, 16281, 1027, "방탈출 시뮬레이터. 친구랑 같이 하기 좋다는 후기가 많습니다."),
  ],
};

export const mockReportList: ReportListItem[] = [
  { id: "2026-08-10", date: "2026-08-10", title: "2026-08-10 Report", pdfUrl: "#" },
  { id: "2026-08-03", date: "2026-08-03", title: "2026-08-03 Report", pdfUrl: "#" },
  { id: "2026-07-27", date: "2026-07-27", title: "2026-07-27 Report", pdfUrl: "#" },
  { id: "2026-07-20", date: "2026-07-20", title: "2026-07-20 Report", pdfUrl: "#" },
];
