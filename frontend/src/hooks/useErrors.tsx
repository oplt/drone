import { useCallback, useState } from "react";

export function useErrors() {
  const [errors, setErrors] = useState<string[]>([]);

  const addError = useCallback((msg: string) => {
    setErrors((prev) => [...prev, msg]);
  }, []);

  const clearErrors = useCallback(() => setErrors([]), []);

  const dismissError = useCallback((index: number) => {
    setErrors((prev) => prev.filter((_, i) => i !== index));
  }, []);

  return { errors, addError, clearErrors, dismissError };
}