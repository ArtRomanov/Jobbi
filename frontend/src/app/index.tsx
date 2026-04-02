import { BrowserRouter } from "react-router-dom";
import { ToastProvider } from "@/shared/ui";
import { AppRouter } from "./router";

export function App() {
  return (
    <BrowserRouter>
      <ToastProvider>
        <AppRouter />
      </ToastProvider>
    </BrowserRouter>
  );
}
