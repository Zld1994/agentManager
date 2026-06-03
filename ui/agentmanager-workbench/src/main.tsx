import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { ApiClientContext, createApiClient } from "./api/client";
import "./styles.css";

const queryClient = new QueryClient();
const apiClient = createApiClient();

createRoot(document.getElementById("root") as HTMLElement).render(
  <StrictMode>
    <ApiClientContext.Provider value={apiClient}>
      <QueryClientProvider client={queryClient}>
        <App />
      </QueryClientProvider>
    </ApiClientContext.Provider>
  </StrictMode>
);
