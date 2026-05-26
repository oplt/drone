import { httpRequest } from "../../../shared/api/httpClient";

export type AccountProfile = {
  id: string;
  email: string;
  full_name: string | null;
  created_at: string;
  email_verified?: boolean;
  twofa_enabled?: boolean;
};

export type PasswordUpdatePayload = {
  current_password: string;
  new_password: string;
  new_password_confirm: string;
};

export type TwoFactorSetup = {
  secret: string;
  qr_code: string;
};

export type TwoFactorVerifyPayload = {
  token: string;
  secret?: string;
};

export type TwoFactorDisablePayload = {
  password: string;
};

export async function fetchAccountProfile(
  token?: string | null,
): Promise<AccountProfile> {
  return httpRequest<AccountProfile>("/auth/me", { token, skipUnauthorizedRedirect: true });
}

export async function updatePassword(
  payload: PasswordUpdatePayload,
  token?: string | null,
): Promise<void> {
  await httpRequest<void>("/auth/password", {
    method: "PUT",
    body: payload,
    token,
    skipUnauthorizedRedirect: true,
  });
}

export async function setupTwoFactor(token?: string | null): Promise<TwoFactorSetup> {
  return httpRequest<TwoFactorSetup>("/auth/2fa/setup", {
    method: "POST",
    token,
    skipUnauthorizedRedirect: true,
  });
}

export async function verifyTwoFactor(
  payload: TwoFactorVerifyPayload,
  token?: string | null,
): Promise<void> {
  await httpRequest<void>("/auth/2fa/verify", {
    method: "POST",
    body: payload,
    token,
    skipUnauthorizedRedirect: true,
  });
}

export async function disableTwoFactor(
  payload: TwoFactorDisablePayload,
  token?: string | null,
): Promise<void> {
  await httpRequest<void>("/auth/2fa/disable", {
    method: "POST",
    body: payload,
    token,
    skipUnauthorizedRedirect: true,
  });
}
