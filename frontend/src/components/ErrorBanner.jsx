export default function ErrorBanner({ error, prefix = "" }) {
  if (!error) return null;
  return (
    <div role="alert" className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">
      {prefix ? `${prefix}: ` : ""}
      {error.message}
    </div>
  );
}
