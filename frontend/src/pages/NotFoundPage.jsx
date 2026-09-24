import { Link } from "react-router-dom";

export default function NotFoundPage() {
  return (
    <div className="p-10 text-center text-slate-300">
      <h1 className="text-2xl font-semibold">Page not found</h1>
      <Link to="/" className="mt-3 inline-block text-sky-400 underline">
        Back to the dashboard
      </Link>
    </div>
  );
}
