import { render, type RenderOptions } from "@testing-library/react";
import { BrowserRouter } from "react-router-dom";
import { ToastProvider } from "@/shared/ui";
import type { ReactElement, ReactNode } from "react";

function AllProviders({ children }: { children: ReactNode }) {
  return (
    <BrowserRouter>
      <ToastProvider>{children}</ToastProvider>
    </BrowserRouter>
  );
}

export function renderWithProviders(
  ui: ReactElement,
  options?: Omit<RenderOptions, "wrapper">,
) {
  return render(ui, { wrapper: AllProviders, ...options });
}
