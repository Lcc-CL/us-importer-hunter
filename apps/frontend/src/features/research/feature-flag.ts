/**
 * Research is an internal development surface, off unless explicitly enabled.
 *
 * Default-off is a security property, not a convenience: the backend research
 * API must not be reachable anonymously until the DNS-rebinding window is
 * closed (ADR-0026), and this flag is what keeps the UI from inviting that.
 */
export const RESEARCH_ENABLED = process.env.NEXT_PUBLIC_ENABLE_RESEARCH === "true";
