import { useAuth } from "../hooks/useAuth";
import { useResource } from "../hooks/useResource";
import HistoryPanel from "../components/quality/HistoryPanel";
import InspectCard from "../components/quality/InspectCard";
import PredictCard from "../components/quality/PredictCard";
import { api } from "../services/api";

export default function QualityPage() {
  const { can } = useAuth();
  const history = useResource((signal) => api.qualityHistory({ limit: 15 }, signal), {
    enabled: can("quality:view"),
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-white">AI Quality Control</h1>
        <p className="text-sm text-slate-400">
          Classical computer vision (OpenCV) + Random Forest, trained on the demonstration
          dataset. Results shown here are computed by the backend from the actual uploaded
          image or parameters, not hardcoded.
        </p>
      </div>

      {can("quality:inspect") ? (
        <InspectCard api={api} onInspected={() => history.reload()} />
      ) : null}
      {can("quality:view") ? <PredictCard api={api} /> : null}
      {can("quality:view") ? <HistoryPanel resource={history} /> : null}
    </div>
  );
}
