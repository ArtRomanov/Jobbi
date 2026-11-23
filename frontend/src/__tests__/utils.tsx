import { render, type RenderOptions, type RenderResult } from "@testing-library/react";
import {
  createMemoryRouter,
  Outlet,
  RouterProvider,
  type InitialEntry,
  type RouteObject,
} from "react-router-dom";
import { ToastProvider } from "@/shared/ui";
import type { ReactElement } from "react";

type MemoryRouter = ReturnType<typeof createMemoryRouter>;

export interface RenderWithProvidersOptions extends RenderOptions {
  /** History stack for the memory router. Defaults to `["/"]`. */
  initialEntries?: InitialEntry[];
  /** Index of the active entry in `initialEntries`. Defaults to the last one. */
  initialIndex?: number;
  /** Route path that renders `ui`. Defaults to `"*"` (every URL), so params need an explicit path. */
  path?: string;
  /** Extra sibling routes, e.g. a navigation target such as `/dashboard`. */
  routes?: RouteObject[];
}

export interface RenderWithProvidersResult extends RenderResult {
  /** The data router, for asserting `router.state.location` after a navigation. */
  router: MemoryRouter;
}

/** Same as the app root route: ToastProvider sits inside the router because toasts render `<Link>`. */
function ProvidersOutlet() {
  return (
    <ToastProvider>
      <Outlet />
    </ToastProvider>
  );
}

/**
 * Renders `ui` inside a data router (`createMemoryRouter` + `RouterProvider`),
 * so data-router-only hooks such as `useBlocker` work in tests. A `wrapper`
 * option (e.g. `StrictMode`) wraps the RouterProvider.
 */
export function renderWithProviders(
  ui: ReactElement,
  {
    initialEntries = ["/"],
    initialIndex,
    path = "*",
    routes = [],
    ...options
  }: RenderWithProvidersOptions = {},
): RenderWithProvidersResult {
  const router = createMemoryRouter(
    [{ element: <ProvidersOutlet />, children: [{ path, element: ui }, ...routes] }],
    { initialEntries, initialIndex },
  );
  const result = render(<RouterProvider router={router} />, options);
  return { ...result, router };
}
