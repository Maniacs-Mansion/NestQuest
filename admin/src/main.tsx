import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import AppRoutes from "./AppRoutes";
import "./index.css";
import { registerServiceWorker } from "./pwa/register";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <AppRoutes />
  </StrictMode>,
);

void registerServiceWorker();
