import { describe, expect, it } from "vitest";
import { createTheme } from "@mui/material/styles";
import { colorSchemes, fontText, radius, shape } from "./themePrimitives";
import { surfacesCustomizations } from "./customizations/surfaces";

describe("design system foundation", () => {
  it("ships DM Sans in the typography stack", () => {
    expect(fontText).toContain("DM Sans");
  });

  it("exposes a radius scale tied to shape.borderRadius", () => {
    expect(shape.borderRadius).toBe(4);
    expect(shape.borderRadius * radius.md).toBe(12);
    expect(shape.borderRadius * radius.sm).toBe(8);
  });

  it("defines dual-scheme surface tokens without light-only greys", () => {
    expect(colorSchemes.light.palette.surface.inset).toBeTruthy();
    expect(colorSchemes.dark.palette.surface.inset).toBeTruthy();
    expect(colorSchemes.dark.palette.surface.raised).not.toMatch(/#f4f4f4/i);
  });

  it("registers ops Panel / Overlay / Quiet Paper variants", () => {
    const theme = createTheme({
      colorSchemes,
      shape,
      components: surfacesCustomizations,
    });
    const paper = theme.components?.MuiPaper?.styleOverrides?.root;
    expect(paper).toBeTypeOf("function");
  });
});
