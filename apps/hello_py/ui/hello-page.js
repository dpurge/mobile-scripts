import { LitElement, html } from "/_launcher/vendor/lit.js";

/** Shows which language and runtime serve this page, plus the shared stop button. */
export class HelloPage extends LitElement {
  static properties = {
    info: { state: true },
    error: { state: true },
  };

  constructor() {
    super();
    this.info = null;
    this.error = null;
  }

  // Light DOM, so style.css applies.
  createRenderRoot() {
    return this;
  }

  async connectedCallback() {
    super.connectedCallback();
    try {
      const response = await fetch("/api/info");
      this.info = await response.json();
    } catch (error) {
      this.error = error.message;
    }
  }

  render() {
    const heading = this.info
      ? html`<h1>Hello from ${this.info.language}</h1>
          <p class="secondary">Runtime version ${this.info.runtime}</p>`
      : html`<h1>${this.error ?? "Loading..."}</h1>`;
    return html`${heading}<stop-button></stop-button>`;
  }
}

customElements.define("hello-page", HelloPage);
