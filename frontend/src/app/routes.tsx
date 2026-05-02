import { createBrowserRouter } from "react-router-dom";

import { AppShell } from "./AppShell";
import { ComparePage } from "../features/compare/ComparePage";
import { ExecutionPage } from "../features/execution/ExecutionPage";
import { HistoryPage } from "../features/history/HistoryPage";
import { RunDetailPage } from "../features/run-detail/RunDetailPage";

export const router = createBrowserRouter([
  {
    path: "/",
    element: <AppShell />,
    children: [
      {
        index: true,
        element: <ExecutionPage />
      },
      {
        path: "history",
        element: <HistoryPage />
      },
      {
        path: "compare",
        element: <ComparePage />
      },
      {
        path: "runs/:runId",
        element: <RunDetailPage />
      }
    ]
  }
]);
