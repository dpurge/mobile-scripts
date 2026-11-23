import { LitElement, html } from "../../vendor/lit.js";

/**
 * Form to add or edit one app.
 *
 * Fires `save` with `detail: {name, script_path}` and `cancel` (both bubble).
 */
export class AppForm extends LitElement {
  static properties = {
    name: { type: String },
    scriptPath: { type: String, attribute: "script-path" },
    message: { state: true },
  };

  constructor() {
    super();
    this.name = "";
    this.scriptPath = "";
    this.message = null;
  }

  // Light DOM, so styles/global.css (the testable layout rules) applies.
  createRenderRoot() {
    return this;
  }

  save(event) {
    event.preventDefault();
    const name = this.querySelector("[name=name]").value.trim();
    const scriptPath = this.querySelector("[name=script_path]").value.trim();
    if (!name || !scriptPath) {
      this.message = "Name and script path are both required.";
      return;
    }
    this.message = null;
    this.dispatchEvent(
      new CustomEvent("save", { detail: { name, script_path: scriptPath }, bubbles: true }),
    );
  }

  cancel() {
    this.dispatchEvent(new CustomEvent("cancel", { bubbles: true }));
  }

  render() {
    return html`
      <form @submit=${this.save}>
        <label>Name <input name="name" .value=${this.name} /></label>
        <label>
          Script path
          <input name="script_path" .value=${this.scriptPath} placeholder="apps/hello_py/main.py" />
        </label>
        ${this.message ? html`<p class="error" role="alert">${this.message}</p>` : ""}
        <div class="buttons">
          <button type="submit">Save</button>
          <button type="button" @click=${this.cancel}>Cancel</button>
        </div>
      </form>
    `;
  }
}

customElements.define("app-form", AppForm);
