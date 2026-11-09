import React, { useState } from "react";
import { SelectField } from "./controls.jsx";
import { LocalDisplayPreferences, AboutDialog } from "./upgrade.jsx";
export default function UIKit() {
  const [value, set] = useState("dark"),
    [open, setOpen] = useState(false);
  return (
    <main
      className="ui-kit"
      style={{ padding: 32, overflow: "auto", height: "100%" }}
    >
      <h1 style={{ fontFamily: "var(--font-editorial)", fontSize: 28 }}>
        Offline Studio · UI kit
      </h1>
      <p>Development only. No backend or model access.</p>
      <section className="workspace-toolbar">
        <button className="primary-button">Primary</button>
        <button className="secondary-button">Secondary</button>
        <button disabled>Disabled</button>
        <button className="secondary-button" aria-busy="true">
          Loading…
        </button>
        <button onClick={() => setOpen(true)}>About & licences</button>
      </section>
      <label>
        Text
        <input aria-label="Sample input" placeholder="Type here" />
      </label>
      <label>
        Notes
        <textarea aria-label="Sample notes" />
      </label>
      <SelectField
        aria-label="Example select"
        value={value}
        onChange={(e) => set(e.target.value)}
      >
        <option value="dark">Dark</option>
        <option value="light">Light</option>
        <option disabled value="disabled">
          Disabled
        </option>
      </SelectField>
      <label>
        <input type="checkbox" />
        Checkbox
      </label>
      <progress value="60" max="100" aria-label="Example progress" />
      <p role="status">Saved on this computer.</p>
      <LocalDisplayPreferences />
      <AboutDialog open={open} onClose={() => setOpen(false)} />
    </main>
  );
}
