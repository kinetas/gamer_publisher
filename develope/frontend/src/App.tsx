import { BrowserRouter, Route, Routes } from "react-router-dom";
import Dashboard from "./pages/Dashboard";
import PrintReport from "./pages/PrintReport";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/print/:id" element={<PrintReport />} />
      </Routes>
    </BrowserRouter>
  );
}
