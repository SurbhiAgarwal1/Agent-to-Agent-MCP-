import { useState, useCallback } from "react";

export function useApi(apiFunction) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const execute = useCallback(
    async (...args) => {
      setLoading(true);
      setError(null);
      try {
        const result = await apiFunction(...args);
        setData(result);
        return { data: result, error: null };
      } catch (err) {
        const message = err.message || "An unexpected error occurred.";
        setError(message);
        return { data: null, error: message };
      } finally {
        setLoading(false);
      }
    },
    [apiFunction]
  );

  return { data, loading, error, execute, setData, setError };
}
