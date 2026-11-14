import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { auth } from "./lib/api/client";
import { Analytics } from "./app/Analytics";
import { Inbox } from "./app/Inbox";
import { JobDetail } from "./app/JobDetail";
import { Layout } from "./app/Layout";
import { Login } from "./app/Login";
import { Messages } from "./app/Messages";
import { Pipeline } from "./app/Pipeline";
import { Settings } from "./app/Settings";
import "./styles.css";

function Private({ children }: { children: React.ReactNode }) {
  return auth.get() ? <>{children}</> : <Navigate to="/login" replace />;
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route element={<Private><Layout /></Private>}>
          <Route index element={<Inbox />} />
          <Route path="jobs/:id" element={<JobDetail />} />
          <Route path="pipeline" element={<Pipeline />} />
          <Route path="messages" element={<Messages />} />
          <Route path="analytics" element={<Analytics />} />
          <Route path="settings" element={<Settings />} />
        </Route>
      </Routes>
    </BrowserRouter>
  </StrictMode>,
);
