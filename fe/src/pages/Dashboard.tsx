import { useCallback, useEffect, useState } from "react";
import {
  getMe,
  getRepos,
  installApp,
  logout,
  signInWithGitHub,
  startIngestion,
  type Me,
  type Repo,
  type ReposResponse,
} from "../api";

/** Per-repo ingestion state, keyed the same way the rows are. */
type IngestState = { status: "queued" | "error"; message?: string };

const repoKey = (r: Repo) => `${r.installation_id}-${r.id}`;

export function Dashboard() {
  const [me, setMe] = useState<Me | null>(null);
  const [repos, setRepos] = useState<ReposResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingRepos, setLoadingRepos] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [ingesting, setIngesting] = useState<Record<string, true>>({});
  const [ingestState, setIngestState] = useState<Record<string, IngestState>>({});

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

  const onIngest = async (r: Repo) => {
    const key = repoKey(r);
    // id is GitHub's numeric repo id; -1 means GitHub did not send one.
    if (r.id === null || !r.full_name) {
      setIngestState((prev) => ({
        ...prev,
        [key]: { status: "error", message: "Repository is missing an id" },
      }));
      return;
    }

    setIngesting((prev) => ({ ...prev, [key]: true }));
    try {
      const res = await startIngestion({
        installation_id: r.installation_id,
        repo_id: r.id,
        repo_full_name: r.full_name,
      });
      setIngestState((prev) => ({
        ...prev,
        [key]: { status: "queued", message: res.message },
      }));
    } catch (err) {
      setIngestState((prev) => ({
        ...prev,
        [key]: {
          status: "error",
          message: err instanceof Error ? err.message : String(err),
        },
      }));
    } finally {
      setIngesting((prev) => {
        const next = { ...prev };
        delete next[key];
        return next;
      });
    }
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
                <th>Ingest</th>
              </tr>
            </thead>
            <tbody>
              {shown.map((r) => {
                const key = repoKey(r);
                const busy = ingesting[key] === true;
                const state = ingestState[key];
                return (
                  <tr key={key}>
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
                    <td>
                      <button
                        className="btn"
                        onClick={() => void onIngest(r)}
                        disabled={busy}
                      >
                        {busy ? "Queuing..." : "Start ingest"}
                      </button>
                      {state && (
                        <div
                          className={`muted ingest-note ${state.status}`}
                          title={state.message}
                        >
                          {state.status === "queued"
                            ? state.message
                            : state.message}
                        </div>
                      )}
                    </td>
                  </tr>
                );
              })}
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
