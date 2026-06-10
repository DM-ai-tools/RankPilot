import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";

import App from "./App";
import { AuthHydrationGate } from "./components/AuthHydrationGate";
import "./index.css";
import "leaflet/dist/leaflet.css";
import "./lib/leafletDefaultIconFix";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 60_000, retry: 1 },
  },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AuthHydrationGate>
          <App />
        </AuthHydrationGate>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
