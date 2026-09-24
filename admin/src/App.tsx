import { useState } from "react";
import "./App.css";
import TodayTab from "./today/TodayTab";

const TABS = [
  { id: "today", label: "Today" },
  { id: "tasks", label: "Tasks" },
  { id: "schedule", label: "Schedule" },
  { id: "history", label: "History" },
] as const;

type TabId = (typeof TABS)[number]["id"];

export default function App() {
  const [active, setActive] = useState<TabId>("today");
  // Built screens own their header (ADMIN-SPEC §1); the generic shell header
  // stays for placeholder tabs and is visually hidden otherwise.
  const hasScreen = active === "today";

  return (
    <div className="admin-shell">
      <header className={hasScreen ? "admin-header visually-hidden" : "admin-header"}>
        <h1 className="admin-title">NestQuest Admin</h1>
        <p className="admin-subline">Admin console</p>
      </header>
      <main
        className={hasScreen ? "admin-panel admin-panel--screen" : "admin-panel"}
        role="tabpanel"
        aria-labelledby={`tab-${active}`}
      >
        {active === "today" ? (
          <TodayTab />
        ) : (
          <p className="admin-placeholder">
            {TABS.find((tab) => tab.id === active)?.label} placeholder — screens
            arrive in later tasks.
          </p>
        )}
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