import React, { useState } from "react";
import {
  BrowserRouter as Router,
  Routes,
  Route,
} from "react-router-dom";
import Register from "./Register";
import Login from "./Login";
import Chat from "./Chat";
import Settings from "./Settings";
import Onboarding from "./Onboarding";

function App() {
  const [token, setToken] = useState(
    localStorage.getItem("companion_token"),
  );

  const handleLogin = (jwtToken) => {
    localStorage.setItem("companion_token", jwtToken);
    setToken(jwtToken);
  };

  const handleLogout = () => {
    localStorage.removeItem("companion_token");
    setToken(null);
  };

  return (
    <Router>
      <Routes>
        <Route path="/register" element={<Register onLogin={handleLogin} />} />
        <Route path="/login" element={<Login onLogin={handleLogin} />} />
        <Route path="/onboarding" element={<Onboarding />} />
        <Route
          path="/chat"
          element={<Chat token={token} onLogout={handleLogout} />}
        />
        <Route
          path="/settings"
          element={<Settings />}
        />
        <Route
          path="/"
          element={<Chat token={token} onLogout={handleLogout} />}
        />
      </Routes>
    </Router>
  );
}

export default App;
