import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Link, Navigate, Route, Routes, useLocation, matchPath } from "react-router-dom";

import { AuthProvider, useAuth } from "./auth";
import { BrandMark } from "./components/BrandMark";
import { DocsDashboard } from "./views/DocsDashboard";
import { Home } from "./views/Home";
import { ImpactGraph } from "./views/ImpactGraph";
import { Login } from "./views/Login";
import { PrDiffView } from "./views/PrDiffView";
import { Signup } from "./views/Signup";

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 5_000, retry: 1 } },
});

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AuthProvider>
          <NavBar />
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route path="/signup" element={<Signup />} />
            <Route path="/" element={<RequireAuth><Home /></RequireAuth>} />
            <Route path="/runs/:runId" element={<RequireAuth><DocsDashboard /></RequireAuth>} />
            <Route path="/runs/:runId/graph" element={<RequireAuth><ImpactGraph /></RequireAuth>} />
            <Route path="/prs/:pullRequestId" element={<RequireAuth><PrDiffView /></RequireAuth>} />
          </Routes>
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  );
}

function RequireAuth({ children }) {
  const { user, loading } = useAuth();
  const location = useLocation();
  if (loading) return null;
  if (!user) return <Navigate to="/login" replace state={{ from: location }} />;
  return children;
}

function NavBar() {
  const { user, logout } = useAuth();
  const { pathname } = useLocation();
  const onAuthRoute = ["/login", "/signup"].some((p) => matchPath(p, pathname));
  if (onAuthRoute) return null;
  return (
    <nav className="nav">
      <Link to="/" className="nav-brand">
        <BrandMark size={24} />
        <span>Aura</span>
      </Link>
      <span className="nav-tag">Documentation as a byproduct of code changes.</span>
      <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 12 }}>
        {user ? (
          <>
            <span className="muted" style={{ fontSize: 13 }}>{user.email}</span>
            <button className="ghost" onClick={logout}>Sign out</button>
          </>
        ) : null}
      </div>
    </nav>
  );
}
