import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router";
import App from "./App.jsx";
import { AuthProvider } from "./hooks/useAuth.jsx";
import { StatusProvider } from "./hooks/useStatus.jsx";
import "./styles.css";

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <StatusProvider><App /></StatusProvider>
      </AuthProvider>
    </BrowserRouter>
  </React.StrictMode>,
);
