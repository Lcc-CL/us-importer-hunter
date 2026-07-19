/**
 * The sender is who you are. It does not change between prospects, and having
 * to retype it for every company was the single most-repeated action in the
 * internal trial — and it vanished on every reload.
 *
 * Stored in localStorage under a versioned key so a future shape change can
 * be recognised and ignored rather than mis-read. Only the three fields the
 * user typed are stored: never a credential, an endpoint, or a contact. A
 * contact belongs to one company and must never become a global default.
 */

import type { ProspectSender } from "./prospect-state";
import { EMPTY_SENDER } from "./prospect-state";

export const SENDER_PROFILE_KEY = "sender_profile_v1";

interface StoredSenderProfile {
  sender_name: string;
  sender_company: string;
  value_proposition: string;
}

function isStored(value: unknown): value is StoredSenderProfile {
  if (typeof value !== "object" || value === null) return false;
  const record = value as Record<string, unknown>;
  return (
    typeof record.sender_name === "string" &&
    typeof record.sender_company === "string" &&
    typeof record.value_proposition === "string"
  );
}

/** Reads the saved profile. Never throws: a bad entry is treated as absent. */
export function loadSenderProfile(): ProspectSender | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(SENDER_PROFILE_KEY);
    if (!raw) return null;
    const parsed: unknown = JSON.parse(raw);
    if (!isStored(parsed)) return null;
    return {
      name: parsed.sender_name,
      company: parsed.sender_company,
      valueProposition: parsed.value_proposition,
    };
  } catch {
    return null;
  }
}

/** Saves, or clears the entry once every field is empty again. */
export function saveSenderProfile(sender: ProspectSender): void {
  if (typeof window === "undefined") return;
  const isEmpty = ![sender.name, sender.company, sender.valueProposition].some((value) =>
    value.trim(),
  );
  try {
    if (isEmpty) {
      window.localStorage.removeItem(SENDER_PROFILE_KEY);
      notifySenderProfileChanged();
      return;
    }
    window.localStorage.setItem(
      SENDER_PROFILE_KEY,
      JSON.stringify({
        sender_name: sender.name,
        sender_company: sender.company,
        value_proposition: sender.valueProposition,
      }),
    );
    notifySenderProfileChanged();
  } catch {
    // A full or blocked storage must not break the workflow.
  }
}

export function clearSenderProfile(): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(SENDER_PROFILE_KEY);
    notifySenderProfileChanged();
  } catch {
    // Ignored for the same reason as above.
  }
}

/**
 * Restores saved values without clobbering anything already on screen.
 *
 * Field by field rather than wholesale: a user who typed a new company but
 * not a new name should keep the typed company and regain the saved name.
 */
export function mergeSenderProfile(
  current: ProspectSender,
  stored: ProspectSender | null,
): ProspectSender {
  if (!stored) return current;
  return {
    name: current.name.trim() ? current.name : stored.name,
    company: current.company.trim() ? current.company : stored.company,
    valueProposition: current.valueProposition.trim()
      ? current.valueProposition
      : stored.valueProposition,
  };
}

export { EMPTY_SENDER };

/* --- external-store plumbing -------------------------------------------
 *
 * localStorage is an external system, so it is read through
 * useSyncExternalStore rather than an effect: the server snapshot is null and
 * the client swaps in the stored profile after hydration, which is exactly
 * the mismatch this hook exists to avoid.
 */

const listeners = new Set<() => void>();
let cachedRaw: string | null = null;
let cachedProfile: ProspectSender | null = null;

export function subscribeSenderProfile(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function notifySenderProfileChanged(): void {
  for (const listener of listeners) listener();
}

/** Stable snapshot: the same object identity until the stored value changes. */
export function senderProfileSnapshot(): ProspectSender | null {
  if (typeof window === "undefined") return null;
  let raw: string | null = null;
  try {
    raw = window.localStorage.getItem(SENDER_PROFILE_KEY);
  } catch {
    return null;
  }
  if (raw !== cachedRaw) {
    cachedRaw = raw;
    cachedProfile = loadSenderProfile();
  }
  return cachedProfile;
}

export function senderProfileServerSnapshot(): ProspectSender | null {
  return null;
}
