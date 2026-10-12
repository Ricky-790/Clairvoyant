import { useCallback, useEffect, useState } from "react";
import { Dashboard } from "./pages/Dashboard";

/**
 * Minimal path-based routing. The Bun server serves `index.html` for every
 * unmatched route, so navigation is client side only.
 */
function useRouter() {
  const [pathname, setPathname] = useState(window.location.pathname);

  useEffect(() => {
    const onPopState = () => setPathname(window.location.pathname);
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  const navigate = useCallback((to: string) => {
    window.history.pushState(null, "", to);
    setPathname(to);
  }, []);

  return { pathname, navigate };
}

export function App() {
  const { pathname, navigate } = useRouter();

  useEffect(() => {
    if (pathname === "/") navigate("/dashboard");
  }, [pathname, navigate]);

  if (pathname === "/dashboard") {
    return <Dashboard />;
  }

  return (
    <div className="card">
      <h2>Not found</h2>
      <p className="muted">
        No page at <code>{pathname}</code>.
      </p>
      <button className="btn primary" onClick={() => navigate("/dashboard")}>
        Go to the dashboard
      </button>
    </div>
  );
}

export default App;