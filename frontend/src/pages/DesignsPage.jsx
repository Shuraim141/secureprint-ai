import { useState } from "react";

import DesignDetail from "../components/designs/DesignDetail";
import DesignList from "../components/designs/DesignList";
import UploadCard from "../components/designs/UploadCard";
import VerifyCard from "../components/designs/VerifyCard";
import ErrorBanner from "../components/ErrorBanner";
import { useAuth } from "../hooks/useAuth";
import { useResource } from "../hooks/useResource";
import { api } from "../services/api";

export default function DesignsPage() {
  const { can } = useAuth();
  const canView = can("design:view");
  const canManage = can("design:upload");
  const canVerify = can("design:verify");
  const [selectedId, setSelectedId] = useState(null);

  const list = useResource((signal) => api.listDesigns(signal), { enabled: canView });
  const detail = useResource((signal) => api.getDesign(selectedId, signal), {
    enabled: canView && selectedId !== null,
    deps: [selectedId],
  });

  function refreshAll() {
    list.reload();
    detail.reload();
  }

  function handleRegistered(design) {
    setSelectedId(design.id);
    list.reload();
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-white">3D/4D Design Security</h1>
        <p className="text-sm text-slate-400">
          Every value below is computed by the backend from the uploaded file. Files are encrypted at rest
          (AES-256-GCM) and every action is written to the audit log.
        </p>
      </div>

      <div className="grid gap-6 xl:grid-cols-2">
        <div className="space-y-6">
          {canManage ? <UploadCard onRegistered={handleRegistered} /> : null}
          {canView ? (
            <DesignList resource={list} selectedId={selectedId} onSelect={setSelectedId} />
          ) : null}
          {canVerify ? (
            <VerifyCard
              selectedDesign={detail.data && selectedId !== null ? detail.data : null}
              onVerified={() => detail.reload()}
            />
          ) : null}
        </div>
        <div>
          {selectedId === null ? (
            <div className="rounded-xl border border-dashed border-slate-700 p-8 text-center text-sm text-slate-400">
              {canView
                ? "Select or register a design to see its 3D analysis, fingerprints, encryption status and 4D profile."
                : "Your role can verify files against the registry but cannot browse designs."}
            </div>
          ) : (
            <>
              <ErrorBanner error={detail.error} prefix="Could not load design" />
              {detail.data ? (
                <DesignDetail
                  design={detail.data}
                  canManage={canManage}
                  canDownload={can("design:download")}
                  onChanged={refreshAll}
                />
              ) : detail.loading ? (
                <div className="p-8 text-center text-slate-400">Loading design…</div>
              ) : null}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
