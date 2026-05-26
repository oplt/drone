import { render, type RenderOptions } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter, type MemoryRouterProps } from "react-router-dom";

type Options = RenderOptions & {
  router?: MemoryRouterProps;
};

export function renderWithRouter(ui: ReactElement, options: Options = {}) {
  const { router, ...renderOptions } = options;
  return render(
    <MemoryRouter {...router}>{ui}</MemoryRouter>,
    renderOptions,
  );
}
