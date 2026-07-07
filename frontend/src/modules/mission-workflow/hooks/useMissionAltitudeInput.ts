import { useCallback, useState } from "react";

export function useMissionAltitudeInput({
  initialAltitude = 30,
  minAltitude = 1,
  maxAltitude = 500,
  validationMessage,
  addError,
}: {
  initialAltitude?: number;
  minAltitude?: number;
  maxAltitude?: number;
  validationMessage?: string;
  addError: (message: string) => void;
}) {
  const [alt, setAlt] = useState(initialAltitude);
  const [altInput, setAltInput] = useState(String(initialAltitude));

  const handleAltitudeInputChange = useCallback((value: string) => {
    if (value === "") {
      setAltInput("");
      return;
    }
    if (!/^\d+$/.test(value)) return;
    setAltInput(value);
  }, []);

  const normalizeAltitude = useCallback(() => {
    if (altInput === "") {
      setAltInput(String(alt));
      return;
    }
    const num = Number(altInput);
    if (!Number.isFinite(num)) {
      setAltInput(String(alt));
      return;
    }
    if (num < minAltitude || num > maxAltitude) {
      addError(
        validationMessage ??
          `Altitude must be between ${minAltitude} and ${maxAltitude} meters`
      );
      return;
    }
    setAlt(num);
  }, [addError, alt, altInput, maxAltitude, minAltitude, validationMessage]);

  return {
    alt,
    setAlt,
    altInput,
    setAltInput,
    handleAltitudeInputChange,
    normalizeAltitude,
  };
}
