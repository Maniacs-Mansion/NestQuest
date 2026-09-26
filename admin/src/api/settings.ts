/**
 * Typed client for the admin household-settings routes
 * (/api/v1/admin/settings).
 */
import { apiFetch } from "./client";
import { readJson } from "./definitions";

export interface HouseholdSettings {
  horizon_days: number;
  /** Local wall-clock "HH:MM", as are the other *_time fields. */
  day_rollover_time: string;
  notify_target: string;
  morning_summary_time: string;
  afternoon_reminder_time: string;
  end_of_day_report_time: string;
  morning_summary_enabled: boolean;
  afternoon_reminder_enabled: boolean;
  end_of_day_report_enabled: boolean;
  celebration_enabled: boolean;
  /** IANA zone name (e.g. "America/New_York"); "" means the API host's local time. */
  timezone: string;
  /**
   * True once the admin explicitly chose `timezone` (even ""); false on a
   * fresh install, where the screen auto-sets the browser's zone. API-only:
   * never shown in the form.
   */
  timezone_configured: boolean;
}

/** Only the supplied fields are updated; the API answers with all of them. */
export type SettingsChanges = Partial<HouseholdSettings>;

export const SETTINGS_PATH = "/api/v1/admin/settings";

export async function fetchSettings(): Promise<HouseholdSettings> {
  return readJson<HouseholdSettings>(await apiFetch(SETTINGS_PATH));
}

export async function updateSettings(changes: SettingsChanges): Promise<HouseholdSettings> {
  return readJson<HouseholdSettings>(
    await apiFetch(SETTINGS_PATH, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(changes),
    }),
  );
}
