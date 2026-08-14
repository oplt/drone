import { useEffect } from "react";
import type {
  AnnotationCanvasHandle,
  AnnotationDraft,
  AnnotationTool,
} from "../components/AnnotationCanvas";
import type { VisionClass } from "../visionTypes";

export function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  if (target.isContentEditable) return true;
  const contentEditableAttr = target.getAttribute("contenteditable");
  if (contentEditableAttr != null && contentEditableAttr.toLowerCase() !== "false") {
    return true;
  }
  const tag = target.tagName;
  if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return true;
  return Boolean(target.closest("[contenteditable='true'], [role='textbox']"));
}

export function useLabelingShortcuts({
  annotations,
  reviewed,
  classes,
  canvas,
  persist,
  navigate,
  deleteSelected,
  setTool,
  setSpacePan,
  setSelectedId,
  setActiveClassId,
}: {
  annotations: AnnotationDraft[];
  reviewed: boolean;
  classes: VisionClass[];
  canvas: React.RefObject<AnnotationCanvasHandle | null>;
  persist: (annotations: AnnotationDraft[], reviewed: boolean) => Promise<void>;
  navigate: (direction: -1 | 1) => Promise<void>;
  deleteSelected: () => void;
  setTool: (tool: AnnotationTool) => void;
  setSpacePan: (active: boolean) => void;
  setSelectedId: (id: string | null) => void;
  setActiveClassId: (id: string) => void;
}) {
  useEffect(() => {
    const keyDown = (event: KeyboardEvent) => {
      if (isTypingTarget(event.target)) return;
      if (event.code === "Space") {
        event.preventDefault();
        setSpacePan(true);
        return;
      }
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") {
        event.preventDefault();
        void persist(annotations, reviewed);
        return;
      }
      const key = event.key.toLowerCase();
      if (key === "b") setTool("draw");
      else if (key === "v") setTool("select");
      else if (key === "delete" || key === "backspace") deleteSelected();
      else if (key === "escape") {
        canvas.current?.cancel();
        setSelectedId(null);
      } else if (key === "a" || event.key === "ArrowLeft") void navigate(-1);
      else if (key === "d" || event.key === "ArrowRight") void navigate(1);
      else if (key === "f" || key === "0") canvas.current?.fit();
      else if (key === "+" || key === "=") canvas.current?.zoomIn();
      else if (key === "-") canvas.current?.zoomOut();
      else if (/^[1-9]$/.test(key)) {
        const visionClass = classes[Number(key) - 1];
        if (visionClass) setActiveClassId(visionClass.id);
      }
    };
    const keyUp = (event: KeyboardEvent) => {
      if (event.code === "Space") setSpacePan(false);
    };
    window.addEventListener("keydown", keyDown);
    window.addEventListener("keyup", keyUp);
    return () => {
      window.removeEventListener("keydown", keyDown);
      window.removeEventListener("keyup", keyUp);
    };
  }, [
    annotations,
    canvas,
    classes,
    deleteSelected,
    navigate,
    persist,
    reviewed,
    setActiveClassId,
    setSelectedId,
    setSpacePan,
    setTool,
  ]);
}
