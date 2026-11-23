// Shared widget: apps load it from their own port as /_launcher/src/widgets/stop-button.js.
// Both imports are relative so they resolve on the launcher's origin and under /_launcher/.
import { LitElement, html } from "../../vendor/lit.js";
import { requestStop } from "../services/api.js";

/** `<stop-button>`: stops the app serving this page, then tells the user the list is next. */
export class StopButton extends LitElement {
  static properties = {
    stopped: { state: true },
    error: { state: true },
  };

  constructor() {
    super();
    this.stopped = false;
    this.error = null;
  }

  // Light DOM, so the page's CSS (checked by tests/test_layout.py) styles the button.
  createRenderRoot() {
    return this;
  }

  async stop() {
    try {
      await requestStop();
      this.stopped = true;
    } catch (error) {
      this.error = error.message;
    }
  }

  render() {
    if (this.stopped) {
      return html`<p>Stopped. Returning to the list...</p>`;
    }
    return html`
      <button @click=${this.stop}>Stop</button>
      ${this.error ? html`<p class="error" role="alert">${this.error}</p>` : ""}
    `;
  }
}

customElements.define("stop-button", StopButton);
