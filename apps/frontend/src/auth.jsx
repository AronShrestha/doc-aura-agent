import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { client, getToken, setToken, setUnauthorizedHandler } from "./api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const queryClient = useQueryClient();
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    const token = getToken();
    if (!token) {
      setUser(null);
      setLoading(false);
      return null;
    }
    try {
      const { data } = await client.get("/auth/me");
      setUser(data);
      setLoading(false);
      return data;
    } catch {
      setToken("");
      setUser(null);
      setLoading(false);
      return null;
    }
  }, []);

  const logout = useCallback(() => {
    setToken("");
    setUser(null);
    queryClient.clear();
  }, [queryClient]);

  useEffect(() => {
    setUnauthorizedHandler(() => {
      setUser(null);
      queryClient.clear();
    });
    refresh();
  }, [refresh, queryClient]);

  const login = useCallback(
    async (email, password) => {
      const { data } = await client.post("/auth/login", { email, password });
      setToken(data.access_token);
      const me = await refresh();
      return me;
    },
    [refresh],
  );

  const signup = useCallback(
    async (email, password, displayName) => {
      const { data } = await client.post("/auth/signup", {
        email,
        password,
        display_name: displayName || null,
      });
      setToken(data.access_token);
      const me = await refresh();
      return me;
    },
    [refresh],
  );

  const value = useMemo(
    () => ({ user, loading, login, signup, logout, refresh }),
    [user, loading, login, signup, logout, refresh],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
