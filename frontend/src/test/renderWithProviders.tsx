import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, type RenderOptions } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter, type MemoryRouterProps } from "react-router-dom";

type Options = RenderOptions & {
  router?: MemoryRouterProps;
  queryClient?: QueryClient;
};

export function renderWithProviders(ui: ReactElement, options: Options = {}) {
  const { router, queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } }), ...renderOptions } = options;

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter {...router}>{ui}</MemoryRouter>
    </QueryClientProvider>,
    renderOptions,
  );
}
