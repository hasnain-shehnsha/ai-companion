import React, { useState } from "react";
import {
  BrowserRouter as Router,
  Routes,
  Route,
  Navigate,
} from "react-router-dom";
import Register from "./Register";
import Login from "./Login";
import Chat from "./Chat";

function App() {
  const [userId, setUserId] = useState(
    localStorage.getItem("companion_user_id"),
  );

  const handleLogin = (id) => {
    localStorage.setItem("companion_user_id", id);
    setUserId(id);
  };

  const handleLogout = () => {
    localStorage.removeItem("companion_user_id");
    setUserId(null);
  };

  return (
    <Router>
      <Routes>
        <Route path="/register" element={<Register onLogin={handleLogin} />} />
        <Route path="/login" element={<Login onLogin={handleLogin} />} />
        <Route
          path="/chat"
          element={<Chat userId={userId} onLogout={handleLogout} />}
        />
        <Route
          path="/"
          element={<Chat userId={userId} onLogout={handleLogout} />}
        />
      </Routes>
    </Router>
  );
}

export default App;
