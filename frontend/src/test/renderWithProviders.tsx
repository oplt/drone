import {
  QueryClient,
  QueryClientProvider,
  type DefaultOptions,
} from "@tanstack/react-query";
import { render, type RenderOptions } from "@testing-library/react";
import type { ComponentType, ReactElement, ReactNode } from "react";
import { MemoryRouter, type MemoryRouterProps } from "react-router-dom";

type ProviderOptions = Omit<RenderOptions, "wrapper"> & {
  router?: MemoryRouterProps;
};

const DEFAULT_TEST_QUERY_OPTIONS: DefaultOptions = {
  queries: { retry: false },
};

export function createTestQueryClient(
  defaultOptions: DefaultOptions = DEFAULT_TEST_QUERY_OPTIONS,
): QueryClient {
  return new QueryClient({ defaultOptions });
}

export function createTestQueryWrapper(
  queryClient: QueryClient = createTestQueryClient(),
): ComponentType<{ children: ReactNode }> {
  return function TestQueryWrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
  };
}

export function renderWithProviders(
  ui: ReactElement,
  { router, ...options }: ProviderOptions = {},
) {
  const queryClient = createTestQueryClient({
      queries: { retry: false },
      mutations: { retry: false },
  });

  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        <MemoryRouter {...router}>{children}</MemoryRouter>
      </QueryClientProvider>
    );
  }

  return render(ui, { wrapper: Wrapper, ...options });
}
