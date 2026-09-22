import { HashRouter, Navigate, Route, Routes } from "react-router-dom";
import { AppLayout } from "./components/AppLayout";
import { ChallengeDetailPage } from "./pages/ChallengeDetailPage";
import { ChallengeListPage } from "./pages/ChallengeListPage";
import { NewChallengePage } from "./pages/NewChallengePage";
import { SettingsPage } from "./pages/SettingsPage";

export default function App() {
  return (
    <HashRouter>
      <Routes>
        <Route element={<AppLayout />}>
          <Route index element={<ChallengeListPage />} />
          <Route path="new" element={<NewChallengePage />} />
          <Route path="challenges/:challengeId" element={<ChallengeDetailPage />} />
          <Route path="settings" element={<SettingsPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </HashRouter>
  );
}
