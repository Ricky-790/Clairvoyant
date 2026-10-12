import { useCallback, useEffect, useState } from "react";
import {
  getMe,
  getRepos,
  installApp,
  logout,
  signInWithGitHub,
  type Me,
  type ReposResponse,
} from "../api";

export function Dashboard() {
  const [me, setMe] = useState<Me | null>(null);
  const [repos, setRepos] = useState<ReposResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingRepos, setLoadingRepos] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const user = await getMe();
        if (cancelled) return;
        setMe(user);
      } catch (err) {
        // 401 simply means "not signed in" - that is a normal state, not an error.
        if (!cancelled)
          setError(err instanceof Error ? err.message : String(err));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const loadRepos = useCallback(async () => {
    setLoadingRepos(true);
    try {
      setRepos(await getRepos());
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoadingRepos(false);
    }
  }, []);

  useEffect(() => {
    if (me) void loadRepos();
  }, [me, loadRepos]);

  const onLogout = async () => {
    await logout();
    window.location.reload();
  };

  if (loading) {
    return <p className="status">Checking your session...</p>;
  }

  if (!me) {
    return (
      <div className="card signin">
        <h2>Clairvoyant</h2>
        <p className="muted">
          Sign in with GitHub to see the repositories you have granted this app
          access to.
        </p>
        {error && <p className="error">{error}</p>}
        <button className="btn primary" onClick={signInWithGitHub}>
          Sign in with GitHub
        </button>
      </div>
    );
  }

  const all = repos?.repositories ?? [];
  const term = search.trim().toLowerCase();
  const shown = term
    ? all.filter(
        (r) =>
          r.full_name?.toLowerCase().includes(term) ||
          r.description?.toLowerCase().includes(term),
      )
    : all;

  return (
    <>
      <header className="topbar">
        <span className="brand">Clairvoyant</span>
        <span className="spacer" />
        <span className="who">
          {me.avatar_url && (
            <img
              src={me.avatar_url}
              alt=""
              className="avatar"
              width={28}
              height={28}
            />
          )}
          {me.login}
        </span>
        <button className="btn" onClick={() => void onLogout()}>
          Sign out
        </button>
      </header>

      <main className="content">
        <div className="row">
          <h2>Repositories</h2>
          <span className="spacer" />
          <input
            className="search"
            placeholder="Filter by name..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <button
            className="btn"
            onClick={() => void loadRepos()}
            disabled={loadingRepos}
          >
            {loadingRepos ? "Refreshing..." : "Refresh"}
          </button>
        </div>

        {repos && repos.installations.length > 0 && (
          <p className="muted">
            {repos.installations.length} installation
            {repos.installations.length === 1 ? "" : "s"}:{" "}
            {repos.installations.map((i) => i.account_login).join(", ")}
          </p>
        )}

        {repos?.errors.map((e) => (
          <p key={e.installation_id} className="error">
            Could not read repositories for <strong>{e.account_login}</strong>:{" "}
            {e.error}
          </p>
        ))}

        {error && <p className="error">{error}</p>}

        {loadingRepos && all.length === 0 ? (
          <p className="status">Loading repositories...</p>
        ) : all.length === 0 ? (
          <div className="empty">
            <p>No repositories yet.</p>
            <p className="muted">
              Install the app on a GitHub account or organisation and grant it
              access to some repositories.
            </p>
            <button className="btn primary" onClick={installApp}>
              Manage GitHub App access
            </button>
          </div>
        ) : (
          <table className="repos">
            <thead>
              <tr>
                <th>Repository</th>
                <th>Account</th>
                <th>Language</th>
                <th className="num">Stars</th>
                <th>Access</th>
              </tr>
            </thead>
            <tbody>
              {shown.map((r) => (
                <tr key={`${r.installation_id}-${r.id}`}>
                  <td>
                    {r.html_url ? (
                      <a href={r.html_url} target="_blank" rel="noreferrer">
                        {r.full_name}
                      </a>
                    ) : (
                      r.full_name
                    )}
                    {r.description && (
                      <div className="muted desc">{r.description}</div>
                    )}
                  </td>
                  <td className="muted">{r.account_login}</td>
                  <td className="muted">{r.language ?? "-"}</td>
                  <td className="num">{r.stargazers_count ?? 0}</td>
                  <td>
                    <span className={`tag ${r.private ? "private" : "public"}`}>
                      {r.private ? "Private" : "Public"}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {shown.length === 0 && all.length > 0 && (
          <p className="status">No repositories match "{search}".</p>
        )}
      </main>
    </>
  );
}

export default Dashboard;
