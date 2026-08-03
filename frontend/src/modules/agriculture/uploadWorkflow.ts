import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  completeAgricultureUpload,
  initiateAgricultureUpload,
  uploadAgricultureChunk,
} from "./api";
import type { AgricultureUploadSession } from "./types";

const STORAGE_PREFIX = "agriculture-upload-session:";

async function checksum(file: File): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", await file.arrayBuffer());
  return Array.from(new Uint8Array(digest), (value) => value.toString(16).padStart(2, "0")).join("");
}

function sessionKey(flightId: string, file: File): string {
  return `${STORAGE_PREFIX}${flightId}:${file.name}:${file.size}:${file.lastModified}`;
}

function loadSession(key: string): AgricultureUploadSession | null {
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as AgricultureUploadSession) : null;
  } catch {
    return null;
  }
}

function saveSession(key: string, session: AgricultureUploadSession): void {
  try { localStorage.setItem(key, JSON.stringify(session)); } catch { /* storage is an optimization */ }
}

export function useAgricultureMediaUpload(flightId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (file: File) => {
      const key = sessionKey(flightId, file);
      const hash = await checksum(file);
      let session = loadSession(key);
      if (!session || session.status !== "uploading" || session.total_bytes !== file.size) {
        session = await initiateAgricultureUpload(flightId, {
          source_kind: file.type.startsWith("video/") ? "rgb_video" : "rgb_stills",
          filename: file.name,
          content_type: file.type || "application/octet-stream",
          total_bytes: file.size,
          checksum: hash,
          metadata: { client_resume_key: key },
        });
        saveSession(key, session);
      }
      while (session.upload_offset < file.size) {
        const start = session.upload_offset;
        const end = Math.min(file.size, start + session.chunk_bytes);
        let next: AgricultureUploadSession | null = null;
        let lastError: unknown;
        for (let attempt = 0; attempt < 3 && !next; attempt += 1) {
          try {
            next = await uploadAgricultureChunk(session, file.slice(start, end));
          } catch (error) {
            lastError = error;
          }
        }
        if (!next) throw lastError ?? new Error("Media chunk upload failed");
        session = { ...session, ...next };
        saveSession(key, session);
      }
      const result = await completeAgricultureUpload(flightId, session.id);
      localStorage.removeItem(key);
      return result;
    },
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["agriculture", "media-inventory", flightId] });
    },
  });
}
