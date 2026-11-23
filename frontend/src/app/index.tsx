import { createBrowserRouter, RouterProvider } from "react-router-dom";
import { appRoutes } from "./router";

// A data router (not <BrowserRouter>) so data-router-only APIs such as
// useBlocker work. Created once at module scope, as the react-router docs advise.
const router = createBrowserRouter(appRoutes);

export function App() {
  return <RouterProvider router={router} />;
}
