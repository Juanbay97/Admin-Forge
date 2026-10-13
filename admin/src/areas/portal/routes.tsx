import { Navigate } from "react-router";
import { Download } from "./Download";

export const PortalIndexRoute = () => <Navigate to="/portal/download" replace />;
export const DownloadRoute = () => <Download />;