import { BrowserRouter, Route, Routes } from "react-router-dom";

import Layout from "./components/Layout";
import ProtectedRoute from "./components/ProtectedRoute";
import { AuthProvider } from "./hooks/useAuth";
import DashboardPage from "./pages/DashboardPage";
import DesignsPage from "./pages/DesignsPage";
import QualityPage from "./pages/QualityPage";
import ManufacturingPage from "./pages/ManufacturingPage";
import SupplyChainPage from "./pages/SupplyChainPage";
import CompliancePage from "./pages/CompliancePage";
import AuditLogsPage from "./pages/AuditLogsPage";
import LoginPage from "./pages/LoginPage";
import NotFoundPage from "./pages/NotFoundPage";

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route
            element={
              <ProtectedRoute>
                <Layout />
              </ProtectedRoute>
            }
          >
            <Route index element={<DashboardPage />} />
            <Route
              path="designs"
              element={
                <ProtectedRoute permission={["design:view", "design:verify"]}>
                  <DesignsPage />
                </ProtectedRoute>
              }
            />
            <Route
              path="quality"
              element={
                <ProtectedRoute permission={["quality:inspect", "quality:view"]}>
                  <QualityPage />
                </ProtectedRoute>
              }
            />
            <Route
              path="supply-chain"
              element={
                <ProtectedRoute permission={["provenance:verify", "part:authenticate"]}>
                  <SupplyChainPage />
                </ProtectedRoute>
              }
            />
            <Route
              path="manufacturing"
              element={
                <ProtectedRoute permission={["printer:control", "gcode:analyze", "incident:view"]}>
                  <ManufacturingPage />
                </ProtectedRoute>
              }
            />
            <Route
              path="compliance"
              element={
                <ProtectedRoute permission={["compliance:view"]}>
                  <CompliancePage />
                </ProtectedRoute>
              }
            />
            <Route
              path="audit"
              element={
                <ProtectedRoute permission={["audit:view"]}>
                  <AuditLogsPage />
                </ProtectedRoute>
              }
            />
          </Route>
          <Route path="*" element={<NotFoundPage />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}
