"use strict";

const labels = {
  runtime: {unconfigured: "Unconfigured", checking: "Checking", ready: "Ready",
    unavailable: "Unavailable"},
  configuration: {missing: "Not provided", provided: "Provided"},
  storage: {not_configured: "Not configured", checking: "Checking",
    ready: "Role and schema verified", unavailable: "Unavailable"},
  identity_provider: {not_configured: "Not configured",
    configured_unverified: "Configured · live connection unverified"},
  onboarding: {not_implemented: "Not implemented"},
  user_access: {not_evaluated: "Not evaluated"}
};
const button = document.getElementById("refresh");
const announcement = document.getElementById("announcement");

function validStatus(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)
      || value.schema_version !== "1.0") return false;
  const expected = ["schema_version", ...Object.keys(labels)].sort();
  if (Object.keys(value).sort().join("|") !== expected.join("|")) return false;
  return Object.keys(labels).every((key) => typeof value[key] === "string"
    && Object.prototype.hasOwnProperty.call(labels[key], value[key]));
}

async function refresh() {
  if (button.disabled) return;
  button.disabled = true;
  announcement.textContent = "Checking runtime status…";
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 4000);
  try {
    const response = await fetch("/forge/v1/status", {
      cache: "no-store", credentials: "omit", redirect: "error",
      headers: {"Accept": "application/json"}, signal: controller.signal
    });
    if (!response.ok) throw new Error("Status unavailable");
    const text = await response.text();
    if (text.length > 4096) throw new Error("Status unavailable");
    const value = JSON.parse(text);
    if (!validStatus(value)) throw new Error("Status unavailable");
    for (const key of Object.keys(labels)) {
      // Only fixed local labels reach the DOM, never server-provided text/diagnostics.
      document.getElementById(key).textContent = labels[key][value[key]];
    }
    announcement.textContent = "Status refreshed. Live identity and user access remain unverified.";
  } catch {
    for (const key of Object.keys(labels)) {
      document.getElementById(key).textContent = "Not checked";
    }
    document.getElementById("runtime").textContent = "Unavailable";
    announcement.textContent = "Status unavailable. Refresh to try again.";
  } finally {
    clearTimeout(timeout);
    button.disabled = false;
  }
}

button.addEventListener("click", refresh);
refresh();
