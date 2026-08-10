import { Header } from "./components/Header";
import { Footer } from "./components/Footer";
import { Sidebar } from "./components/Sidebar";
import { ReportDocument } from "./components/ReportDocument";
import { mockReport, mockReportList } from "./data/mockReport";

export default function App() {
  return (
    <div style={{ minHeight: "100%", display: "flex", flexDirection: "column" }}>
      <Header />

      <div style={{ flex: 1, display: "flex" }}>
        <main style={{ flex: 1, padding: "40px 24px" }}>
          <ReportDocument report={mockReport} />
        </main>
        <Sidebar reports={mockReportList} />
      </div>

      <Footer />
    </div>
  );
}
