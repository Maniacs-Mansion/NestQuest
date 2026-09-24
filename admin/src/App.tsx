import { useState } from "react";
import "./App.css";
import { TransitionsProvider } from "./api/useTransitions";
import DefinitionsTab from "./definitions/DefinitionsTab";
import HistoryTab from "./history/HistoryTab";
import ScheduleTab from "./schedule/ScheduleTab";
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

  return (
    <TransitionsProvider>
      <div className="admin-shell">
        {/* Every tab is a built screen that owns its header (ADMIN-SPEC §1); the
            generic shell header stays only as a visually hidden page heading. */}
        <header className="admin-header visually-hidden">
          <h1 className="admin-title">NestQuest Admin</h1>
          <p className="admin-subline">Admin console</p>
        </header>
        <main
          className="admin-panel admin-panel--screen"
          role="tabpanel"
          aria-labelledby={`tab-${active}`}
        >
          {active === "today" ? (
            <TodayTab />
          ) : active === "tasks" ? (
            <DefinitionsTab />
          ) : active === "schedule" ? (
            <ScheduleTab />
          ) : (
            <HistoryTab />
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
    </TransitionsProvider>
  );
}