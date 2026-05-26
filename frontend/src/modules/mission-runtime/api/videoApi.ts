import { httpRequest } from "../../../shared/api/httpClient";

export async function startVideoStream(token?: string | null): Promise<void> {
  await httpRequest<void>("/video/start", {
    method: "POST",
    token,
    skipUnauthorizedRedirect: true,
  });
}
