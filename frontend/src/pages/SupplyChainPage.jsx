import { useState } from "react";

import AuthenticateCard from "../components/supplychain/AuthenticateCard";
import CreatePartCard from "../components/supplychain/CreatePartCard";
import PartList from "../components/supplychain/PartList";
import ProvenanceTimeline from "../components/supplychain/ProvenanceTimeline";
import ErrorBanner from "../components/ErrorBanner";
import { useAuth } from "../hooks/useAuth";
import { useResource } from "../hooks/useResource";
import { api } from "../services/api";

export default function SupplyChainPage() {
  const { can } = useAuth();
  const canCreate = can("provenance:create");
  const canVerify = can("provenance:verify");
  const canAuthenticate = can("part:authenticate");
  const [selectedId, setSelectedId] = useState(null);

  const designs = useResource((signal) => api.listDesigns(signal), { enabled: canCreate });
  const parts = useResource((signal) => api.listParts(signal), { enabled: canVerify });
  const detail = useResource((signal) => api.getPart(selectedId, signal), {
    enabled: canVerify && selectedId !== null,
    deps: [selectedId],
  });

  async function handleCreatePart(designId, batch, material) {
    const part = await api.createPart({ design_id: designId, batch, material });
    parts.reload();
    setSelectedId(part.id);
    return part;
  }

  function refresh() {
    parts.reload();
    detail.reload();
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-white">Supply Chain</h1>
        <p className="text-sm text-slate-400">
          Every provenance event is hash-chained and Ed25519-signed. Modifying a stored event
          breaks the chain from that point forward, which "Verify chain" and "Authenticate"
          detect and report exactly where.
        </p>
      </div>

      {canCreate ? (
        <CreatePartCard designs={designs.data ?? []} onCreated={handleCreatePart} />
      ) : null}

      {canAuthenticate ? <AuthenticateCard /> : null}

      {canVerify ? (
        <div className="grid gap-6 xl:grid-cols-2">
          <PartList resource={parts} selectedId={selectedId} onSelect={setSelectedId} />
          <div>
            <ErrorBanner error={detail.error} prefix="Could not load part" />
            {selectedId === null ? (
              <div className="rounded-xl border border-dashed border-slate-700 p-8 text-center text-sm text-slate-400">
                Select a part to see its full provenance timeline.
              </div>
            ) : detail.data ? (
              <ProvenanceTimeline part={detail.data} canAdvance={canCreate} onChanged={refresh} />
            ) : detail.loading ? (
              <div className="p-8 text-center text-slate-400">Loading…</div>
            ) : null}
          </div>
        </div>
      ) : null}
    </div>
  );
}
