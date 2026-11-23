import { LitElement, html } from "../../vendor/lit.js";
import { fetchApps, saveApps, startApp } from "../services/api.js";
import "./app-form.js";

/**
 * The list of configured apps with start, reorder, edit, delete and add.
 *
 * Every change sends the whole list to the server and re-renders from the server's reply, so the
 * screen always shows what is saved.
 */
export class AppList extends LitElement {
  static properties = {
    apps: { state: true },
    error: { state: true },
    editing: { state: true },
  };

  constructor() {
    super();
    this.apps = null;
    this.error = null;
    // null: no form; {index: null}: adding; {index: n}: editing the app at n.
    this.editing = null;
  }

  // Light DOM, so styles/global.css (the testable layout rules) applies.
  createRenderRoot() {
    return this;
  }

  async connectedCallback() {
    super.connectedCallback();
    try {
      this.apps = await fetchApps();
    } catch (error) {
      this.error = error.message;
    }
  }

  /** Run `action`, showing any failure in the banner instead of leaving the page unchanged. */
  async attempt(action) {
    this.error = null;
    try {
      await action();
    } catch (error) {
      this.error = error.message;
    }
  }

  async replaceApps(apps) {
    await this.attempt(async () => {
      this.apps = await saveApps(apps);
      this.editing = null;
    });
  }

  start(index) {
    return this.attempt(async () => {
      const started = await startApp(index);
      window.location.href = started.url;
    });
  }

  move(index, offset) {
    const apps = [...this.apps];
    const target = index + offset;
    if (target < 0 || target >= apps.length) {
      return;
    }
    [apps[index], apps[target]] = [apps[target], apps[index]];
    return this.replaceApps(apps);
  }

  remove(index) {
    return this.replaceApps(this.apps.filter((_, position) => position !== index));
  }

  saveForm(event) {
    const apps = [...this.apps];
    if (this.editing.index === null) {
      apps.push(event.detail);
    } else {
      apps[this.editing.index] = event.detail;
    }
    return this.replaceApps(apps);
  }

  renderRow(app, index) {
    return html`
      <li>
        <div class="app-info">
          ${app.name}<span class="secondary">${app.script_path}</span>
        </div>
        <div class="buttons">
          <button @click=${() => this.start(index)}>Start</button>
          <button @click=${() => this.move(index, -1)}>Up</button>
          <button @click=${() => this.move(index, 1)}>Down</button>
          <button @click=${() => (this.editing = { index })}>Edit</button>
          <button @click=${() => this.remove(index)}>Delete</button>
        </div>
      </li>
    `;
  }

  renderForm() {
    const app = this.editing.index === null ? null : this.apps[this.editing.index];
    return html`
      <app-form
        .name=${app?.name ?? ""}
        .scriptPath=${app?.script_path ?? ""}
        @save=${this.saveForm}
        @cancel=${() => (this.editing = null)}
      ></app-form>
    `;
  }

  render() {
    const banner = this.error ? html`<p class="error" role="alert">${this.error}</p>` : "";
    if (this.apps === null) {
      return html`${banner}${this.error ? "" : html`<p>Loading...</p>`}`;
    }
    return html`
      <h1>Apps</h1>
      ${banner}
      <ul>
        ${this.apps.map((app, index) => this.renderRow(app, index))}
      </ul>
      ${this.editing
        ? this.renderForm()
        : html`<button @click=${() => (this.editing = { index: null })}>Add</button>`}
    `;
  }
}

customElements.define("app-list", AppList);
