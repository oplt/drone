import { PROVIDER_IDS } from "./aiSettingsDefaults";
import type { SettingsDoc } from "./settingsTypes";

export function validateSettingsDoc(doc: SettingsDoc): string | null {
  if (doc.preflight.BATTERY_MIN_PERCENT < 10 || doc.preflight.BATTERY_MIN_PERCENT > 50) {
    return "Battery Min (%) must be 10-50%.";
  }
  if (doc.preflight.BANK_MAX_DEG > 45) return "Bank angle exceeds 45° safe limit.";
  for (const providerId of PROVIDER_IDS) {
    const provider = doc.ai.providers[providerId];
    if (!provider?.enabled) continue;
    try {
      const parsed = new URL(provider.api_base);
      if (!["http:", "https:"].includes(parsed.protocol)) throw new Error();
    } catch {
      return `${providerId} API base must be a valid http(s) URL.`;
    }
  }
  for (const profile of doc.ai.profiles) {
    if (!profile.enabled) continue;
    try {
      const parsed = new URL(profile.api_base);
      if (!["http:", "https:"].includes(parsed.protocol)) throw new Error();
    } catch {
      return `${profile.name || profile.provider} API base must be a valid http(s) URL.`;
    }
  }
  return null;
}
