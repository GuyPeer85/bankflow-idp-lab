const form = document.querySelector("#serviceForm");
const resultPanel = document.querySelector("#resultPanel");
const validateButton = document.querySelector("#validateButton");


function escapeHtml(value) {
  return String(value).replace(
    /[&<>"']/g,
    (character) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#039;",
    })[character],
  );
}


function buildServiceRequest() {
  return {
    apiVersion: "platform.bankflow.io/v1alpha1",
    kind: "ServiceRequest",

    metadata: {
      name: document.querySelector("#serviceName").value.trim(),
      owner: document.querySelector("#owner").value.trim(),
    },

    spec: {
      workloadType:
        document.querySelector("#workloadType").value,

      environment:
        document.querySelector("#environment").value,

      clusterClass: "general",

      goldenPath: {
        name: "http-api",
        channel: "stable",
        version: "1.0.0",
      },

      image: {
        repository:
          document.querySelector("#imageRepository").value.trim(),

        tag:
          document.querySelector("#imageTag").value.trim(),
      },

      size: document.querySelector("#size").value,

      replicas: Number(
        document.querySelector("#replicas").value,
      ),

      exposure:
        document.querySelector("#exposure").value,

      features: {
        pilotMode: false,
      },
    },
  };
}


function showLoading() {
  resultPanel.className = "preview-card is-loading";

  resultPanel.innerHTML = `
    <div class="preview-heading">
      <p class="eyebrow">REQUEST PREVIEW</p>
      <h2>Validating request</h2>
    </div>

    <div class="empty-preview">
      <div class="loading-indicator"></div>
      <p>Checking platform guardrails...</p>
    </div>
  `;
}


function showApproved(result) {
  const preview = result.preview;

  const resources = preview.resourcesToGenerate
    .map(
      (resource) =>
        `<li>${escapeHtml(resource)}</li>`,
    )
    .join("");

  resultPanel.className = "preview-card is-approved";

  resultPanel.innerHTML = `
    <div class="preview-heading">
      <p class="eyebrow">REQUEST APPROVED</p>
      <h2>${escapeHtml(preview.serviceName)}</h2>
    </div>

    <div class="result-status approved-status">
      Approved by platform guardrails
    </div>

    <dl class="preview-details">
      <div>
        <dt>Owner</dt>
        <dd>${escapeHtml(preview.owner)}</dd>
      </div>

      <div>
        <dt>Environment</dt>
        <dd>${escapeHtml(preview.environment)}</dd>
      </div>

      <div>
        <dt>Namespace</dt>
        <dd>${escapeHtml(preview.namespace)}</dd>
      </div>

      <div>
        <dt>Image</dt>
        <dd>${escapeHtml(preview.image)}</dd>
      </div>

      <div>
        <dt>Replicas</dt>
        <dd>${escapeHtml(preview.replicas)}</dd>
      </div>

      <div>
        <dt>Resource profile</dt>
        <dd>${escapeHtml(preview.size)}</dd>
      </div>
    </dl>

    <div class="resource-list">
      <h3>Resources to generate</h3>
      <ul>${resources}</ul>
    </div>

    <p class="preview-note">
      Validation only — no resources were created.
    </p>
  `;
}


function normalizeErrors(result) {
  const errors = result.errors || result.detail || [];

  if (!Array.isArray(errors)) {
    return ["The request was rejected."];
  }

  return errors.map((error) => {
    if (typeof error === "string") {
      return error;
    }

    const location = Array.isArray(error.loc)
      ? error.loc.join(" → ")
      : "request";

    return `${location}: ${error.msg || "Invalid value"}`;
  });
}


function showRejected(result) {
  const errors = normalizeErrors(result);

  const errorItems = errors
    .map(
      (error) =>
        `<li>${escapeHtml(error)}</li>`,
    )
    .join("");

  resultPanel.className = "preview-card is-rejected";

  resultPanel.innerHTML = `
    <div class="preview-heading">
      <p class="eyebrow">REQUEST REJECTED</p>
      <h2>Changes required</h2>
    </div>

    <div class="result-status rejected-status">
      The request did not pass the guardrails
    </div>

    <div class="error-list">
      <h3>Why was it rejected?</h3>
      <ul>${errorItems}</ul>
    </div>

    <p class="preview-note">
      Update the request and validate it again.
    </p>
  `;
}


function showConnectionError() {
  resultPanel.className = "preview-card is-rejected";

  resultPanel.innerHTML = `
    <div class="preview-heading">
      <p class="eyebrow">CONNECTION ERROR</p>
      <h2>Platform API unavailable</h2>
    </div>

    <div class="error-list">
      <p>
        The portal could not contact the platform API.
      </p>
    </div>
  `;
}


form.addEventListener("submit", async (event) => {
  event.preventDefault();

  showLoading();

  validateButton.disabled = true;
  validateButton.textContent = "Validating...";

  try {
    const serviceRequest = buildServiceRequest();

    const response = await fetch(
      "/api/v1/service-requests/validate",
      {
        method: "POST",

        headers: {
          "Content-Type": "application/json",
        },

        body: JSON.stringify(serviceRequest),
      },
    );

    const result = await response.json();

    if (response.ok && result.approved) {
      showApproved(result);
    } else {
      showRejected(result);
    }
  } catch (error) {
    console.error(error);
    showConnectionError();
  } finally {
    validateButton.disabled = false;
    validateButton.textContent = "Validate request";
  }
});