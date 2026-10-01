import type { ReactNode } from "react";

interface PageSheetProps {
  children: ReactNode;
  /** 인쇄 시 이 섹션을 새 물리 페이지에서 시작시킬지 여부. 내용 길이에
   * 맞춰 몇 장이 될지는 브라우저/Chromium이 알아서 나누므로(global.css
   * 참고), 여기서는 "섹션 경계"만 지정하면 된다. */
  breakBefore?: boolean;
}

/** 화면에서 "PDF 페이지처럼" 보이게 하는 시각적 컨테이너.
 * 실제 PDF 물리 크기/여백은 fastapi-server의 page.pdf({ format: "A4", margin })가
 * 전담하고, 이 컴포넌트는 인쇄 시 margin: 0, width: 100%로 재정의된다(global.css). */
export function PageSheet({ children, breakBefore }: PageSheetProps) {
  return (
    <section
      className={`page-sheet${breakBefore ? " page-sheet--break-before" : ""}`}
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
      {children}
    </section>
  );
}
