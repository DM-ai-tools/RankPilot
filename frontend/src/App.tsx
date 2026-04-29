import { Navigate, Route, Routes } from "react-router-dom";

import { AppShell } from "./components/layout/AppShell";
import { RequireAuth } from "./components/RequireAuth";
import { RequireOnboarded } from "./components/RequireOnboarded";
import { ChatPage } from "./pages/ChatPage";
import { CitationsPage } from "./pages/CitationsPage";
import { ContentQueuePage } from "./pages/ContentQueuePage";
import { DashboardPage } from "./pages/DashboardPage";
import { GbpPage } from "./pages/GbpPage";
import { NewScanPage } from "./pages/NewScanPage";
import { OnboardingPage } from "./pages/OnboardingPage";
import { OpportunitiesPage } from "./pages/OpportunitiesPage";
import { RanksPage } from "./pages/RanksPage";
import { ReportsPage } from "./pages/ReportsPage";
import { ResultsLoadingPage } from "./pages/ResultsLoadingPage";
import { ReviewsPage } from "./pages/ReviewsPage";
import { SettingsPage } from "./pages/SettingsPage";
import { LoginPage } from "./pages/LoginPage";
import { PrivacyPolicyPage } from "./pages/PrivacyPolicyPage";
import { VisibilityMapPage } from "./pages/VisibilityMapPage";

export default function App() {
  return (
    <Routes>
      {/* Public routes */}
      <Route path="/login" element={<LoginPage />} />
      <Route path="/privacy" element={<PrivacyPolicyPage />} />

      {/* Requires login — onboarding lives here so unauthenticated users
          are bounced to /login before they see the form */}
      <Route element={<RequireAuth />}>
        <Route path="/onboarding" element={<OnboardingPage />} />
        <Route path="/loading-results" element={<ResultsLoadingPage />} />

        {/* Requires login AND a completed onboarding profile */}
        <Route element={<RequireOnboarded />}>
          <Route element={<AppShell />}>
            <Route index element={<DashboardPage />} />
            <Route path="heatmap" element={<Navigate to="/map" replace />} />
            <Route path="map" element={<VisibilityMapPage />} />
            <Route path="opportunities" element={<OpportunitiesPage />} />
            <Route path="content" element={<ContentQueuePage />} />
            <Route path="scan" element={<NewScanPage />} />
            <Route path="ranks" element={<RanksPage />} />
            <Route path="gbp" element={<GbpPage />} />
            <Route path="citations" element={<CitationsPage />} />
            <Route path="reviews" element={<ReviewsPage />} />
            <Route path="chat" element={<ChatPage />} />
            <Route path="reports" element={<ReportsPage />} />
            <Route path="settings" element={<SettingsPage />} />
          </Route>
        </Route>
      </Route>
    </Routes>
  );
}
