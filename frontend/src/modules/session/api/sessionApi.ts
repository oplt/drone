import { httpRequest } from "../../../shared/api/httpClient";
import { ApiError } from "../../../shared/api/apiError";
import { clearSessionMarker } from "../sessionCookies";
import type {
  LoginRequest,
  LoginResponse,
  SessionUser,
  SignUpRequest,
} from "../types";

async function getCurrentUser(signal?: AbortSignal): Promise<SessionUser> {
  return httpRequest<SessionUser>("/auth/me", {
    signal,
    skipUnauthorizedRedirect: true,
  });
}

export async function refreshSession(): Promise<boolean> {
  try {
    await httpRequest<void>("/auth/refresh", {
      method: "POST",
      skipUnauthorizedRedirect: true,
    });
    return true;
  } catch {
    return false;
  }
}

export async function updateCurrentUser(
  payload: { full_name?: string },
  token?: string | null,
): Promise<SessionUser> {
  return httpRequest<SessionUser>("/auth/me", {
    method: "PATCH",
    body: payload,
    token,
  });
}

export async function fetchCurrentUser(signal?: AbortSignal): Promise<SessionUser> {
  try {
    return await getCurrentUser(signal);
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) {
      const refreshed = await refreshSession();
      if (!refreshed) {
        clearSessionMarker();
        throw error;
      }
      return getCurrentUser(signal);
    }
    throw error;
  }
}

export async function verifySession(): Promise<boolean> {
  try {
    await fetchCurrentUser();
    return true;
  } catch {
    clearSessionMarker();
    return false;
  }
}

export async function logout(): Promise<void> {
  try {
    await httpRequest<void>("/auth/logout", {
      method: "POST",
      skipUnauthorizedRedirect: true,
    });
  } finally {
    clearSessionMarker();
  }
}

export async function login(payload: LoginRequest): Promise<LoginResponse> {
  return httpRequest<LoginResponse>("/auth/login", {
    method: "POST",
    body: payload,
    skipUnauthorizedRedirect: true,
  });
}

export async function signUp(payload: SignUpRequest): Promise<LoginResponse> {
  return httpRequest<LoginResponse>("/auth/signup", {
    method: "POST",
    body: payload,
    skipUnauthorizedRedirect: true,
  });
}
