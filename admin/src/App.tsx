import { useState } from "react";
import "./App.css";

const TABS = [
  { id: "today", label: "Today" },
  { id: "tasks", label: "Tasks" },
  { id: "schedule", label: "Schedule" },
  { id: "history", label: "History" },
] as const;

type TabId = (typeof TABS)[number]["id"];

export default function App() {
  const [active, setActive] = useState<TabId>("today");

  return (
    <div className="admin-shell">
      <header className="admin-header">
        <h1 className="admin-title">NestQuest Admin</h1>
        <p className="admin-subline">Admin console</p>
      </header>
      <main
        className="admin-panel"
        role="tabpanel"
        aria-labelledby={`tab-${active}`}
      >
        <p className="admin-placeholder">
          {TABS.find((tab) => tab.id === active)?.label} placeholder — screens
          arrive in later tasks.
        </p>
      </main>
      <nav className="admin-tabbar" aria-label="Admin sections">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            id={`tab-${tab.id}`}
            type="button"
            role="tab"
            aria-selected={tab.id === active}
            className={tab.id === active ? "admin-tab active" : "admin-tab"}
            onClick={() => setActive(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </nav>
    </div>
  );
}