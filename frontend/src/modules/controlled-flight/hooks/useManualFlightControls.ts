import { useCallback, useEffect, useRef, useState } from "react";
import { getSessionMarker } from "../../session";
import { sendManualControlCommand } from "../api/manualControlApi";
import {
  MANUAL_CONTROL_REPEAT_MS,
  MANUAL_KEY_BINDINGS,
  type ManualCommandPhase,
  type ManualFlightCommand,
} from "../types";

export function useManualFlightControls({
  flightId,
  enabled,
  ready,
  onDisable,
}: {
  flightId: string | null;
  enabled: boolean;
  ready: boolean;
  onDisable: () => void;
}) {
  const heldManualCommandsRef = useRef<Map<string, ManualFlightCommand>>(new Map());
  const activeKeyboardKeysRef = useRef<Set<string>>(new Set());
  const [activeManualCommands, setActiveManualCommands] = useState<ManualFlightCommand[]>([]);
  const [manualControlError, setManualControlError] = useState<string | null>(null);
  const [lastManualCommand, setLastManualCommand] = useState<{
    command: ManualFlightCommand;
    phase: ManualCommandPhase;
    source: "keyboard" | "button";
    sentAt: string;
  } | null>(null);

  const sendManualFlightCommand = useCallback(
    async (
      command: ManualFlightCommand,
      phase: ManualCommandPhase,
      source: "keyboard" | "button",
    ) => {
      const token = getSessionMarker();
      if (!token) {
        setManualControlError("Not authenticated");
        return;
      }
      try {
        await sendManualControlCommand(
          { command, phase, source, flight_id: flightId },
          token,
        );
        setManualControlError(null);
        setLastManualCommand({ command, phase, source, sentAt: new Date().toISOString() });
      } catch (error: unknown) {
        setManualControlError(
          error instanceof Error ? error.message : "Manual control request failed",
        );
      }
    },
    [flightId],
  );

  const syncActiveManualCommands = useCallback(() => {
    setActiveManualCommands(
      Array.from(new Set(Array.from(heldManualCommandsRef.current.values()))),
    );
  }, []);

  const stopAllManualCommands = useCallback(
    (source: "keyboard" | "button" = "keyboard") => {
      const commands = Array.from(new Set(Array.from(heldManualCommandsRef.current.values())));
      heldManualCommandsRef.current.clear();
      activeKeyboardKeysRef.current.clear();
      syncActiveManualCommands();
      commands.forEach((command) => {
        void sendManualFlightCommand(command, "stop", source);
      });
    },
    [sendManualFlightCommand, syncActiveManualCommands],
  );

  const beginManualControl = useCallback(
    (keyId: string, command: ManualFlightCommand, source: "keyboard" | "button") => {
      if (!ready) return;
      heldManualCommandsRef.current.set(keyId, command);
      syncActiveManualCommands();
      void sendManualFlightCommand(command, "start", source);
    },
    [ready, sendManualFlightCommand, syncActiveManualCommands],
  );

  const endManualControl = useCallback(
    (keyId: string, source: "keyboard" | "button") => {
      const command = heldManualCommandsRef.current.get(keyId);
      if (!command) return;
      heldManualCommandsRef.current.delete(keyId);
      syncActiveManualCommands();
      void sendManualFlightCommand(command, "stop", source);
    },
    [sendManualFlightCommand, syncActiveManualCommands],
  );

  useEffect(() => {
    if (ready) return;
    if (!enabled && activeManualCommands.length === 0) return;
    onDisable();
    stopAllManualCommands();
  }, [activeManualCommands.length, enabled, onDisable, ready, stopAllManualCommands]);

  useEffect(() => {
    if (!enabled || !ready) return;

    const isTypingTarget = (target: EventTarget | null) => {
      const element = target as HTMLElement | null;
      if (!element) return false;
      const tagName = element.tagName?.toLowerCase();
      return (
        tagName === "input" || tagName === "textarea" || tagName === "select" || element.isContentEditable
      );
    };

    const handleKeyDown = (event: KeyboardEvent) => {
      const key = event.key.toLowerCase();
      const command = MANUAL_KEY_BINDINGS[key];
      if (!command || isTypingTarget(event.target)) return;
      event.preventDefault();
      if (activeKeyboardKeysRef.current.has(key)) return;
      activeKeyboardKeysRef.current.add(key);
      beginManualControl(`key:${key}`, command, "keyboard");
    };

    const handleKeyUp = (event: KeyboardEvent) => {
      const key = event.key.toLowerCase();
      const command = MANUAL_KEY_BINDINGS[key];
      if (!command) return;
      event.preventDefault();
      activeKeyboardKeysRef.current.delete(key);
      endManualControl(`key:${key}`, "keyboard");
    };

    const handleWindowBlur = () => {
      onDisable();
      stopAllManualCommands();
    };

    window.addEventListener("keydown", handleKeyDown);
    window.addEventListener("keyup", handleKeyUp);
    window.addEventListener("blur", handleWindowBlur);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
      window.removeEventListener("keyup", handleKeyUp);
      window.removeEventListener("blur", handleWindowBlur);
      stopAllManualCommands();
    };
  }, [beginManualControl, enabled, endManualControl, onDisable, ready, stopAllManualCommands]);

  useEffect(() => {
    if (!enabled || activeManualCommands.length === 0) return;
    const timer = window.setInterval(() => {
      const uniqueCommands = Array.from(
        new Set(Array.from(heldManualCommandsRef.current.values())),
      );
      uniqueCommands.forEach((command) => {
        void sendManualFlightCommand(command, "hold", "keyboard");
      });
    }, MANUAL_CONTROL_REPEAT_MS);
    return () => window.clearInterval(timer);
  }, [activeManualCommands, enabled, sendManualFlightCommand]);

  return {
    activeManualCommands,
    manualControlError,
    lastManualCommand,
    beginManualControl,
    endManualControl,
    stopAllManualCommands,
    sendManualFlightCommand,
    setManualControlError,
  };
}
