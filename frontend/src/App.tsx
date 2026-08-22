import { Route, Routes } from "react-router-dom";

import { AppShell } from "@/components/AppShell";
import CircularDetail from "@/pages/CircularDetail";
import Circulars from "@/pages/Circulars";
import Dashboard from "@/pages/Dashboard";
import EvaluationDashboard from "@/pages/EvaluationDashboard";
import ImpactAssessment from "@/pages/ImpactAssessment";
import PointInTime from "@/pages/PointInTime";
import Search from "@/pages/Search";

export default function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<Dashboard />} />
        <Route path="circulars" element={<Circulars />} />
        <Route path="circulars/:circularId" element={<CircularDetail />} />
        <Route path="assessments" element={<ImpactAssessment />} />
        <Route path="assessments/:runId" element={<ImpactAssessment />} />
        <Route path="point-in-time" element={<PointInTime />} />
        <Route path="evaluation" element={<EvaluationDashboard />} />
        <Route path="search" element={<Search />} />
      </Route>
    </Routes>
  );
}
