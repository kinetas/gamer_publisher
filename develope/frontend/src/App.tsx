import { BrowserRouter, Route, Routes } from "react-router-dom";
import Dashboard from "./pages/Dashboard";
import PrintReport from "./pages/PrintReport";
import News from "./pages/News";
import Sentiment from "./pages/Sentiment";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/print/:id" element={<PrintReport />} />
        <Route path="/news" element={<News />} />
        <Route path="/sentiment" element={<Sentiment />} />
      </Routes>
    </BrowserRouter>
  );
}
