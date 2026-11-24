/** Query param of `/dashboard` that opens an application's panel (`/dashboard?application=<id>`). */
export const APPLICATION_SEARCH_PARAM = "application";

/**
 * App URLs that several slices build. Lower layers (features) cannot import
 * pages, so both the links and the pages that read them use these.
 */
export const ROUTES = {
  dashboard: "/dashboard",
  /** The CVs list; the CV editor returns here after every successful save. */
  cvs: "/cvs",
  /** Dashboard with the application panel open (read by pages/dashboard, then cleared). */
  dashboardApplication: (applicationId: string): string =>
    `/dashboard?${APPLICATION_SEARCH_PARAM}=${encodeURIComponent(applicationId)}`,
  /** The application's AI chat. */
  chat: (applicationId: string): string => `/applications/${encodeURIComponent(applicationId)}/chat`,
} as const;
