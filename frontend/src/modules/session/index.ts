export type {
  LoginRequest,
  LoginResponse,
  SessionUser,
  SignUpRequest,
} from "./types";

export {
  clearSessionMarker,
  getSessionMarker,
  readSessionMarker,
  setSessionMarker,
} from "./sessionCookies";

export {
  fetchCurrentUser,
  login,
  logout,
  refreshSession,
  signUp,
  updateCurrentUser,
  verifySession,
} from "./api/sessionApi";

export {
  disableTwoFactor,
  fetchAccountProfile,
  setupTwoFactor,
  updatePassword,
  verifyTwoFactor,
} from "./api/accountApi";
export type {
  AccountProfile,
  PasswordUpdatePayload,
  TwoFactorDisablePayload,
  TwoFactorSetup,
  TwoFactorVerifyPayload,
} from "./api/accountApi";

export { useCurrentUser } from "./hooks/useCurrentUser";
export { useSession } from "./hooks/useSession";
export { default as LandingPage } from "./views/LandingPage";

/** @deprecated Use getSessionMarker(). */
export { getSessionMarker as getToken } from "./sessionCookies";

/** @deprecated Use setSessionMarker(). */
export { setSessionMarker as setToken } from "./sessionCookies";

/** @deprecated Use clearSessionMarker(). */
export { clearSessionMarker as clearToken } from "./sessionCookies";
