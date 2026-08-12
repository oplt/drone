const CLASS_PALETTE = [
  "#2E7D32",
  "#1565C0",
  "#C62828",
  "#6A1B9A",
  "#EF6C00",
  "#00838F",
  "#AD1457",
  "#5D4037",
  "#283593",
  "#558B2F",
] as const;

export function classColor(value: string): string {
  let hash = 0;
  for (let index = 0; index < value.length; index += 1) {
    hash = (hash * 31 + value.charCodeAt(index)) | 0;
  }
  return CLASS_PALETTE[Math.abs(hash) % CLASS_PALETTE.length];
}
