"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";

export function useApi<T>(path: string) {
  const [data, setData] = useState<T>();
  const [error, setError] = useState<string>();
  const [loading, setLoading] = useState(true);
  const refresh = useCallback(async () => { setError(undefined); try { setData(await api<T>(path)); } catch (error) { setError(error instanceof Error ? error.message : "Unknown error"); } }, [path]);
  useEffect(() => {
    let active = true;
    api<T>(path)
      .then((value) => { if (active) setData(value); })
      .catch((reason: unknown) => { if (active) setError(reason instanceof Error ? reason.message : "Unknown error"); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [path]);
  return { data, error, loading, refresh };
}
