import type { ReactNode } from "react";

interface PageSheetProps {
  pageLabel: string;
  children: ReactNode;
}

/** PDF의 한 페이지처럼 보이도록 만든 컨테이너. 실제 페이지 분할은 아니고,
 * 계속 스크롤되는 문서 안에서 "여기부터 한 페이지"라는 시각적 경계를 준다. */
export function PageSheet({ pageLabel, children }: PageSheetProps) {
  return (
    <section
      className="page-sheet"
      style={{
        width: "var(--page-width)",
        maxWidth: "100%",
        margin: "0 auto 32px",
        background: "var(--color-surface)",
        border: "1px solid var(--color-border)",
        padding: "40px 48px",
        position: "relative",
      }}
    >
      <span
        style={{
          position: "absolute",
          top: 16,
          right: 20,
          fontSize: 11,
          color: "var(--color-text-muted)",
          fontFamily: "var(--font-mono)",
          letterSpacing: "0.04em",
        }}
      >
        {pageLabel}
      </span>
      {children}
    </section>
  );
}
