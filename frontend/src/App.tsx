import { lazy, Suspense } from "react";
import { Route, Routes } from "react-router-dom";

import { AppShell } from "@/components/AppShell";
import { Skeleton } from "@/components/ui/feedback";
import AssessmentWorkspace from "@/pages/AssessmentWorkspace";
import Assessments from "@/pages/Assessments";
import CircularDetail from "@/pages/CircularDetail";
import Circulars from "@/pages/Circulars";
import NotFound from "@/pages/NotFound";
import Overview from "@/pages/Overview";
import PointInTime from "@/pages/PointInTime";
import Search from "@/pages/Search";

// The charts library is only needed on the evaluation page.
const Evaluation = lazy(() => import("@/pages/Evaluation"));

export default function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<Overview />} />
        <Route path="circulars" element={<Circulars />} />
        <Route path="circulars/:circularId" element={<CircularDetail />} />
        <Route path="search" element={<Search />} />
        <Route path="assessments" element={<Assessments />} />
        <Route path="assessments/:runId" element={<AssessmentWorkspace />} />
        <Route path="point-in-time" element={<PointInTime />} />
        <Route
          path="evaluation"
          element={
            <Suspense fallback={<Skeleton lines={6} label="the evaluation page" />}>
              <Evaluation />
            </Suspense>
          }
        />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}
