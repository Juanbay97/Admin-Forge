import { createBrowserRouter, Navigate, type RouteObject } from "react-router";
import { NotFound } from "../components/NotFound";
import { AREAS } from "./areas";
import { AreaGate, HomeRedirect } from "./AreaGate";
import { IdentityBoundary } from "./IdentityBoundary";
import { NotFoundPage } from "./NotFoundPage";
import { RequireSession } from "./RequireSession";
import { ResetPasswordRoute } from "./publicRoutes";

type PlatformRoutes = typeof import("../areas/platform/routes");
const platform = (name: keyof PlatformRoutes) => async () => ({ Component: (await import("../areas/platform/routes"))[name] });
type CompanyRoutes = typeof import("../areas/company/routes");
const company = (name: keyof CompanyRoutes) => async () => ({ Component: (await import("../areas/company/routes"))[name] });

/** Area bundles are lazy chunks; the registry (areas.ts) and this tree are the only eager parts. */
export const routes: RouteObject[] = [
  // Public pages live outside RequireSession: they never call an authenticated endpoint.
  { path: "reset-password", element: <ResetPasswordRoute /> },
  {
    path: "/",
    element: (
      <RequireSession>
        <IdentityBoundary />
      </RequireSession>
    ),
    children: [
      { index: true, element: <HomeRedirect /> },
      { path: "login", element: <Navigate to="/" replace /> },
      {
        path: "company",
        element: <AreaGate area={AREAS.company} />,
        children: [
          {
            lazy: async () => ({ Component: (await import("../areas/company/CompanyLayout")).CompanyLayout }),
            children: [
              { index: true, lazy: company("OverviewRoute") },
              { path: "members", lazy: company("MembersRoute") },
              { path: "gateway", lazy: company("GatewayRoute") },
              { path: "catalog", lazy: company("CatalogRoute") },
              { path: "branding", lazy: company("BrandingRoute") },
              { path: "*", element: <NotFound /> },
            ],
          },
        ],
      },
      {
        path: "platform",
        element: <AreaGate area={AREAS.platform} />,
        children: [
          {
            lazy: async () => ({ Component: (await import("../areas/platform/PlatformLayout")).PlatformLayout }),
            children: [
              { index: true, lazy: platform("OverviewRoute") },
              { path: "companies", lazy: platform("CompaniesRoute") },
              { path: "keys", lazy: platform("KeysRoute") },
              { path: "prices", lazy: platform("PricesRoute") },
              { path: "companies/new", lazy: platform("NewCompanyRoute") },
              { path: "companies/:id", lazy: platform("CompanyRoute") },
              { path: "*", element: <NotFound /> },
            ],
          },
        ],
      },
      { path: "portal/*", element: <AreaGate area={AREAS.portal} /> },
      { path: "*", element: <NotFoundPage /> },
    ],
  },
];

export const createAppRouter = () => createBrowserRouter(routes, { basename: "/admin" });