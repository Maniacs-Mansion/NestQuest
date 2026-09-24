/**
 * Settings — a pushed screen opened from the Today header's Settings button.
 *
 * Its one section so far is Children: list, add, edit, deactivate/reactivate
 * and reorder the household's child profiles. Every write refetches the list.
 *
 * TODO: the other household settings (horizon days, day rollover time,
 * notification config) are a separate later task.
 */
import {
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent as ReactKeyboardEvent,
} from "react";
import { ApiForbiddenError } from "../api/client";
import {
  createChild,
  reorderChildren,
  setChildActive,
  updateChild,
  type ChildCreateBody,
  type ChildEditBody,
} from "../api/children";
import { ApiRequestError, fetchChildren, type AdminChild } from "../api/definitions";
import { FOCUSABLE, inertOutside } from "../schedule/OverrideEditor";
import { ArrowDownGlyph, ArrowUpGlyph, ChevronLeftGlyph, PlusGlyph } from "./glyphs";
import "./SettingsScreen.css";

/** The swatch picker's presets; any other "#RRGGBB" can be typed. */
export const COLOUR_PRESETS = ["#e11d48", "#f97316", "#eab308", "#16a34a", "#0ea5e9", "#7c3aed"];

/** ADMIN-SPEC §1: every scroll column ends with 92px so content clears the tab bar. */
export const SCROLL_BOTTOM_PADDING = "92px";

const HEX_COLOUR = /^#[0-9a-fA-F]{6}$/;

type LoadState =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; children: AdminChild[] };

type FormTarget = null | "new" | AdminChild;

interface Draft {
  name: string;
  colour: string;
  avatar: string;
  order: string;
}

/** Display order: sort_order, ties broken by id (the API's own order). */
function sortChildren(children: AdminChild[]): AdminChild[] {
  return [...children].sort((a, b) => a.sort_order - b.sort_order || a.id - b.id);
}

function errorMessage(error: unknown, action: string): string {
  if (error instanceof ApiForbiddenError) return error.message;
  if (error instanceof ApiRequestError && error.detail) return `${action}: ${error.detail}`;
  return `${action}. Check your connection and try again.`;
}

function draftFor(target: "new" | AdminChild, siblings: AdminChild[]): Draft {
  if (target === "new") {
    const next = siblings.reduce((max, c) => Math.max(max, c.sort_order), 0) + 1;
    return { name: "", colour: "", avatar: "", order: String(next) };
  }
  return {
    name: target.display_name,
    colour: target.colour ?? "",
    avatar: target.avatar_ref ?? "",
    order: String(target.sort_order),
  };
}

/** The request body for the draft, or a validation message. */
function buildBody(
  draft: Draft,
  target: "new" | AdminChild,
): ChildCreateBody | ChildEditBody | string {
  const name = draft.name.trim();
  const colour = draft.colour.trim();
  const avatar = draft.avatar.trim();
  const order = draft.order.trim();
  if (!name) return "Enter a display name.";
  if (colour && !HEX_COLOUR.test(colour)) return "Colour must be a hex value like #0ea5e9.";
  if (order && !/^-?\d+$/.test(order)) return "Order must be a whole number.";

  if (target === "new") {
    const body: ChildCreateBody = { display_name: name };
    if (colour) body.colour = colour;
    if (avatar) body.avatar_ref = avatar;
    if (order) body.sort_order = Number(order);
    return body;
  }

  // The API rejects null, so a set colour, avatar or order cannot be cleared.
  if (!colour && target.colour !== null) return "A colour, once set, cannot be removed. Pick another.";
  if (!avatar && target.avatar_ref !== null) return "An avatar ref, once set, cannot be removed.";
  if (!order) return "Enter an order.";
  const body: ChildEditBody = {};
  if (name !== target.display_name) body.display_name = name;
  if (colour && colour !== target.colour) body.colour = colour;
  if (avatar && avatar !== target.avatar_ref) body.avatar_ref = avatar;
  if (Number(order) !== target.sort_order) body.sort_order = Number(order);
  if (Object.keys(body).length === 0) return "No changes to save.";
  return body;
}

function ChildForm({
  target,
  siblings,
  saving,
  error,
  onCancel,
  onSubmit,
}: {
  target: "new" | AdminChild;
  /** The current list; a new child's order defaults to after the last. */
  siblings: AdminChild[];
  saving: boolean;
  error: string | null;
  onCancel: () => void;
  onSubmit: (body: ChildCreateBody | ChildEditBody | string) => void;
}) {
  const [draft, setDraft] = useState<Draft>(() => draftFor(target, siblings));
  const nameRef = useRef<HTMLInputElement>(null);
  const update = (patch: Partial<Draft>) => setDraft((d) => ({ ...d, ...patch }));
  const isNew = target === "new";
  const title = isNew ? "Add child" : `Edit ${target.display_name}`;

  useEffect(() => {
    nameRef.current?.focus();
  }, []);

  function submit(event: FormEvent) {
    event.preventDefault();
    onSubmit(buildBody(draft, target));
  }

  return (
    <form className="settings-card settings-form" aria-label={title} onSubmit={submit} noValidate>
      <h4 className="settings-form-title">{title}</h4>
      <label className="settings-field">
        <span className="settings-label">Display name</span>
        <input
          ref={nameRef}
          className="settings-input"
          type="text"
          required
          value={draft.name}
          disabled={saving}
          onChange={(event) => update({ name: event.target.value })}
        />
      </label>
      <div className="settings-field">
        <label className="settings-field">
          <span className="settings-label">Colour</span>
          <input
            className="settings-input"
            type="text"
            placeholder="#0ea5e9"
            value={draft.colour}
            disabled={saving}
            onChange={(event) => update({ colour: event.target.value })}
          />
        </label>
        <div className="settings-swatches" role="group" aria-label="Colour presets">
          {COLOUR_PRESETS.map((hex) => (
            <button
              key={hex}
              type="button"
              className="settings-swatch-option"
              style={{ background: hex }}
              aria-label={`Colour ${hex}`}
              aria-pressed={draft.colour.toLowerCase() === hex}
              disabled={saving}
              onClick={() => update({ colour: hex })}
            />
          ))}
        </div>
      </div>
      <label className="settings-field">
        <span className="settings-label">Avatar ref (optional)</span>
        <input
          className="settings-input"
          type="text"
          value={draft.avatar}
          disabled={saving}
          onChange={(event) => update({ avatar: event.target.value })}
        />
      </label>
      <label className="settings-field">
        <span className="settings-label">Order</span>
        <input
          className="settings-input"
          type="text"
          inputMode="numeric"
          value={draft.order}
          disabled={saving}
          onChange={(event) => update({ order: event.target.value })}
        />
      </label>
      {error ? (
        <p className="settings-error" role="alert" data-testid="child-form-error">
          {error}
        </p>
      ) : null}
      <div className="settings-form-footer">
        <button type="button" className="settings-cancel" disabled={saving} onClick={onCancel}>
          Cancel
        </button>
        <button type="submit" className="settings-save" disabled={saving} aria-busy={saving}>
          {saving ? "Saving…" : isNew ? "Add child" : "Save child"}
        </button>
      </div>
    </form>
  );
}

function ChildRow({
  child,
  index,
  count,
  busy,
  onEdit,
  onMove,
  onToggleActive,
}: {
  child: AdminChild;
  index: number;
  count: number;
  /** The in-flight action key, or null. Every write control waits on it. */
  busy: string | null;
  onEdit: () => void;
  onMove: (delta: -1 | 1) => void;
  onToggleActive: () => void;
}) {
  const locked = busy !== null;
  const toggling = busy === `active-${child.id}`;
  return (
    <li
      className={child.is_active ? "settings-child" : "settings-child settings-child--inactive"}
      data-testid={`settings-child-${child.id}`}
    >
      <span
        className="settings-swatch"
        data-testid={`settings-swatch-${child.id}`}
        style={{ background: child.colour ?? "var(--nq-a-border)" }}
        aria-hidden="true"
      />
      <div className="settings-child-text">
        <div className="settings-child-name">{child.display_name}</div>
        <div className="settings-child-meta">
          Order {child.sort_order} · {child.colour ?? "no colour"}
        </div>
      </div>
      <span
        className={child.is_active ? "settings-pill settings-pill--active" : "settings-pill"}
        data-testid={`settings-active-${child.id}`}
      >
        {child.is_active ? "Active" : "Inactive"}
      </span>
      <div className="settings-child-actions">
        <button
          type="button"
          className="settings-icon-button"
          aria-label={`Move ${child.display_name} up`}
          aria-busy={busy === `move-${child.id}`}
          disabled={locked || index === 0}
          onClick={() => onMove(-1)}
        >
          <ArrowUpGlyph />
        </button>
        <button
          type="button"
          className="settings-icon-button"
          aria-label={`Move ${child.display_name} down`}
          aria-busy={busy === `move-${child.id}`}
          disabled={locked || index === count - 1}
          onClick={() => onMove(1)}
        >
          <ArrowDownGlyph />
        </button>
        <button
          type="button"
          className="settings-action"
          aria-label={`Edit ${child.display_name}`}
          disabled={locked}
          onClick={onEdit}
        >
          Edit
        </button>
        <button
          type="button"
          className="settings-action"
          aria-label={`${child.is_active ? "Deactivate" : "Reactivate"} ${child.display_name}`}
          aria-busy={toggling}
          disabled={locked}
          onClick={onToggleActive}
        >
          {toggling ? "Saving…" : child.is_active ? "Deactivate" : "Reactivate"}
        </button>
      </div>
    </li>
  );
}

export default function SettingsScreen({ onClose }: { onClose: () => void }) {
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [attempt, setAttempt] = useState(0);
  const [form, setForm] = useState<FormTarget>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  // A ref, not state: two taps in one frame must not both see `busy === null`.
  const inFlight = useRef(false);
  const screenRef = useRef<HTMLDivElement>(null);
  const titleRef = useRef<HTMLHeadingElement>(null);
  const addRef = useRef<HTMLButtonElement>(null);
  const formWasOpen = useRef(false);

  // Modal focus: move in on open, keep the background out of reach, and hand
  // focus back to the opener (the Settings button) on close.
  useEffect(() => {
    const trigger = document.activeElement as HTMLElement | null;
    titleRef.current?.focus();
    const restoreBackground = screenRef.current ? inertOutside(screenRef.current) : undefined;
    return () => {
      restoreBackground?.();
      if (trigger && trigger.isConnected) trigger.focus();
    };
  }, []);

  // The form's controls unmount when it closes; hand focus to Add child then
  // (after the render that re-enables it).
  useEffect(() => {
    if (formWasOpen.current && form === null) addRef.current?.focus();
    formWasOpen.current = form !== null;
  }, [form]);

  useEffect(() => {
    let cancelled = false;
    setState((current) => (current.kind === "ready" ? current : { kind: "loading" }));
    fetchChildren()
      .then((children) => {
        if (!cancelled) setState({ kind: "ready", children: sortChildren(children) });
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        setState({ kind: "error", message: errorMessage(error, "Children could not be loaded") });
      });
    return () => {
      cancelled = true;
    };
  }, [attempt]);

  function onKeyDown(event: ReactKeyboardEvent<HTMLDivElement>) {
    if (event.key === "Escape") {
      event.preventDefault();
      if (!inFlight.current) onClose();
      return;
    }
    if (event.key !== "Tab" || !screenRef.current) return;
    const focusable = Array.from(screenRef.current.querySelectorAll<HTMLElement>(FOCUSABLE));
    if (focusable.length === 0) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    const current = document.activeElement;
    const outside = !focusable.includes(current as HTMLElement);
    if (event.shiftKey && (current === first || outside)) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && (current === last || outside)) {
      event.preventDefault();
      first.focus();
    }
  }

  /**
   * Run one write, then refetch the list. One write at a time; a failure
   * keeps the screen (and any open form) as it was and says why.
   */
  async function run(key: string, write: () => Promise<unknown>, action: string): Promise<boolean> {
    if (inFlight.current) return false;
    inFlight.current = true;
    setBusy(key);
    setActionError(null);
    setFormError(null);
    try {
      await write();
    } catch (error) {
      const message = errorMessage(error, action);
      if (key === "form") setFormError(message);
      else setActionError(message);
      inFlight.current = false;
      setBusy(null);
      return false;
    }
    try {
      const children = await fetchChildren();
      setState({ kind: "ready", children: sortChildren(children) });
    } catch (error) {
      setActionError(errorMessage(error, "Saved, but the children list could not be refreshed"));
    }
    inFlight.current = false;
    setBusy(null);
    return true;
  }

  function closeForm() {
    setForm(null);
    setFormError(null);
  }

  async function submitForm(body: ChildCreateBody | ChildEditBody | string) {
    if (form === null) return;
    if (typeof body === "string") {
      setFormError(body);
      return;
    }
    const saved =
      form === "new"
        ? await run("form", () => createChild(body as ChildCreateBody), "The child could not be added")
        : await run("form", () => updateChild(form.id, body), "The child could not be saved");
    if (saved) closeForm();
  }

  function move(children: AdminChild[], index: number, delta: -1 | 1) {
    const ids = children.map((c) => c.id);
    const target = index + delta;
    [ids[index], ids[target]] = [ids[target], ids[index]];
    void run(`move-${children[index].id}`, () => reorderChildren(ids), "The order could not be saved");
  }

  function toggleActive(child: AdminChild) {
    void run(
      `active-${child.id}`,
      () => setChildActive(child.id, !child.is_active),
      child.is_active ? "The child could not be deactivated" : "The child could not be reactivated",
    );
  }

  let body;
  if (state.kind === "loading") {
    body = (
      <div className="settings-status" role="status" data-testid="settings-loading">
        Loading children…
      </div>
    );
  } else if (state.kind === "error") {
    body = (
      <div className="settings-status settings-status--error" role="alert" data-testid="settings-error">
        <p>{state.message}</p>
        <button type="button" className="settings-action" onClick={() => setAttempt((n) => n + 1)}>
          Try again
        </button>
      </div>
    );
  } else {
    const { children } = state;
    body = (
      <>
        {children.length > 0 ? (
          <ul className="settings-card settings-list" aria-label="Children">
            {children.map((child, index) => (
              <ChildRow
                key={child.id}
                child={child}
                index={index}
                count={children.length}
                busy={busy}
                onEdit={() => {
                  setFormError(null);
                  setForm(child);
                }}
                onMove={(delta) => move(children, index, delta)}
                onToggleActive={() => toggleActive(child)}
              />
            ))}
          </ul>
        ) : (
          <div className="settings-card settings-empty">No children yet.</div>
        )}
        {form !== null ? (
          <ChildForm
            key={form === "new" ? "new" : form.id}
            target={form}
            siblings={children}
            saving={busy === "form"}
            error={formError}
            onCancel={closeForm}
            onSubmit={(b) => void submitForm(b)}
          />
        ) : null}
      </>
    );
  }

  return (
    <div
      ref={screenRef}
      className="settings-screen"
      role="dialog"
      aria-modal="true"
      aria-labelledby="settings-title"
      onKeyDown={onKeyDown}
    >
      <header className="settings-header">
        <button
          type="button"
          className="settings-back"
          aria-label="Back"
          disabled={busy !== null}
          onClick={onClose}
        >
          <ChevronLeftGlyph size={20} />
        </button>
        <div>
          <h2 className="settings-title" id="settings-title" ref={titleRef} tabIndex={-1}>
            Settings
          </h2>
          <p className="settings-sub">Household setup</p>
        </div>
      </header>
      <div
        className="settings-scroll"
        data-testid="settings-scroll"
        style={{ paddingBottom: SCROLL_BOTTOM_PADDING }}
      >
        <div className="settings-section-head">
          <h3 className="settings-section-label">Children</h3>
          <button
            ref={addRef}
            type="button"
            className="settings-add"
            disabled={state.kind !== "ready" || busy !== null || form === "new"}
            onClick={() => {
              setFormError(null);
              setForm("new");
            }}
          >
            <PlusGlyph />
            Add child
          </button>
        </div>
        {actionError !== null ? (
          <div className="settings-action-error" role="alert" data-testid="settings-action-error">
            <span>{actionError}</span>
            <button type="button" className="settings-action" onClick={() => setActionError(null)}>
              Dismiss
            </button>
          </div>
        ) : null}
        {body}
      </div>
    </div>
  );
}
