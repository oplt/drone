import { describe, expect, it } from "vitest";

/** Relative luminance for sRGB hex (#RRGGBB). */
function luminance(hex: string): number {
  const normalized = hex.replace("#", "");
  const value = Number.parseInt(normalized, 16);
  const channels = [16, 8, 0].map((shift) => {
    const channel = ((value >> shift) & 0xff) / 255;
    return channel <= 0.03928
      ? channel / 12.92
      : ((channel + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2];
}

function contrastRatio(foreground: string, background: string): number {
  const lighter = Math.max(luminance(foreground), luminance(background));
  const darker = Math.min(luminance(foreground), luminance(background));
  return (lighter + 0.05) / (darker + 0.05);
}

/**
 * Documented WCAG AA (≥4.5:1) checks for severity chip label colors on dark carbon panels.
 * Colors match dark overrides in dataDisplay MuiChip customizations.
 */
describe("status chip contrast on dark surfaces", () => {
  const darkPanel = "#121212";

  const cases: Array<{ severity: string; label: string; min: number }> = [
    { severity: "critical/high (error)", label: "#FFCDD2", min: 4.5 },
    { severity: "medium (warning)", label: "#FFE0B2", min: 4.5 },
    { severity: "low (info)", label: "#B3E5FC", min: 4.5 },
    { severity: "success", label: "#C8E6C9", min: 4.5 },
  ];

  it.each(cases)(
    "$severity label on dark carbon meets AA ($min:1)",
    ({ label, min }) => {
      expect(contrastRatio(label, darkPanel)).toBeGreaterThanOrEqual(min);
    },
  );
});
