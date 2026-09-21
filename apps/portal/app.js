const form = document.querySelector("#serviceForm");
const resultPanel = document.querySelector("#resultPanel");
const validateButton = document.querySelector("#validateButton");
const createTabButton = document.querySelector("#createTabButton");
const servicesTabButton = document.querySelector("#servicesTabButton");
const createView = document.querySelector("#createView");
const servicesView = document.querySelector("#servicesView");
const serviceCount = document.querySelector("#serviceCount");
const serviceList = document.querySelector("#serviceList");
const serviceDetailsPanel = document.querySelector(
  "#serviceDetailsPanel",
);
const refreshServicesButton = document.querySelector(
  "#refreshServicesButton",
);
const lastUpdated = document.querySelector("#lastUpdated");

let approvedServiceRequest = null;
let catalogRefreshTimer = null;
let selectedServiceKey = null;
let loadedServices = [];


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
      name: document
        .querySelector("#serviceName")
        .value
        .trim(),

      owner: document
        .querySelector("#owner")
        .value
        .trim(),
    },

    spec: {
      workloadType: document
        .querySelector("#workloadType")
        .value,

      environment: document
        .querySelector("#environment")
        .value,

      clusterClass: "general",

      goldenPath: {
        name: "http-api",
        channel: "stable",
        version: "1.0.0",
      },

      image: {
        repository: document
          .querySelector("#imageRepository")
          .value
          .trim(),

        tag: document
          .querySelector("#imageTag")
          .value
          .trim(),
      },

      size: document
        .querySelector("#size")
        .value,

      replicas: Number(
        document
          .querySelector("#replicas")
          .value,
      ),

      exposure: document
        .querySelector("#exposure")
        .value,

      features: {
        pilotMode: false,
      },
    },
  };
}


function showWaitingForValidation() {
  resultPanel.className = "preview-card";

  resultPanel.innerHTML = `
    <div class="preview-heading">
      <p class="eyebrow">REQUEST PREVIEW</p>
      <h2>Validation required</h2>
    </div>

    <div class="empty-preview">
      <div class="document-icon">✓</div>

      <p>
        The request changed and must be validated again.
      </p>

      <small>
        Nothing has been created.
      </small>
    </div>
  `;
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

      <p>
        Checking platform guardrails...
      </p>
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

  resultPanel.className =
    "preview-card is-approved";

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

    <button
      id="createDraftButton"
      class="create-draft-button"
      type="button"
    >
      Create GitOps draft
    </button>

    <p class="preview-note">
      This creates local Git files only.
      It does not commit, push or deploy.
    </p>
  `;

  const createDraftButton = document.querySelector(
    "#createDraftButton",
  );

  createDraftButton.addEventListener(
    "click",
    createGitOpsDraft,
  );
}


function normalizeErrors(result) {
  const errors =
    result.errors ||
    result.detail ||
    [];

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

    return (
      `${location}: ` +
      `${error.msg || "Invalid value"}`
    );
  });
}


function showRejected(result) {
  approvedServiceRequest = null;

  const errors = normalizeErrors(result);

  const errorItems = errors
    .map(
      (error) =>
        `<li>${escapeHtml(error)}</li>`,
    )
    .join("");

  resultPanel.className =
    "preview-card is-rejected";

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


function showDraftCreated(result) {
  approvedServiceRequest = null;

  const draft = result.draft;

  resultPanel.className =
    "preview-card is-approved";

  resultPanel.innerHTML = `
    <div class="preview-heading">
      <p class="eyebrow">GITOPS DRAFT CREATED</p>
      <h2>${escapeHtml(draft.serviceName)}</h2>
    </div>

    <div class="result-status approved-status">
      Files generated successfully
    </div>

    <div class="draft-files">
      <h3>Generated files</h3>

      <div>
        <span>Service request</span>
        <code>
          ${escapeHtml(draft.requestFile)}
        </code>
      </div>

      <div>
        <span>Kubernetes manifest</span>
        <code>
          ${escapeHtml(draft.manifestFile)}
        </code>
      </div>
    </div>

    <div class="next-action">
      <h3>Next controlled action</h3>

      <p>
        ${escapeHtml(draft.nextAction)}
      </p>
    </div>

    <p class="preview-note">
      No commit, push or deployment was performed.
    </p>
  `;
}


function showConnectionError() {
  approvedServiceRequest = null;

  resultPanel.className =
    "preview-card is-rejected";

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


async function createGitOpsDraft(event) {
  const createButton = event.currentTarget;

  if (!approvedServiceRequest) {
    showWaitingForValidation();
    return;
  }

  createButton.disabled = true;
  createButton.textContent =
    "Creating GitOps draft...";

  try {
    const response = await fetch(
      "/api/v1/service-requests",
      {
        method: "POST",

        headers: {
          "Content-Type": "application/json",
        },

        body: JSON.stringify(
          approvedServiceRequest,
        ),
      },
    );

    const result = await response.json();

    if (response.ok && result.created) {
      showDraftCreated(result);
    } else {
      showRejected(result);
    }
  } catch (error) {
    console.error(error);
    showConnectionError();
  } finally {
    createButton.disabled = false;
    createButton.textContent =
      "Create GitOps draft";
  }
}


function serviceKey(service) {
  return `${service.environment}/${service.serviceName}`;
}


function statusLabel(status) {
  return String(status || "unknown")
    .replace("-", " ")
    .toUpperCase();
}


function renderServiceDetails(service) {
  const status = service.status || "unavailable";
  const application = service.argocd || {};
  const kubernetes = service.kubernetes || {};
  const problems = service.problems || [];

  const problemItems = problems
    .map((problem) => {
      if (typeof problem === "string") {
        return `<li>${escapeHtml(problem)}</li>`;
      }

      return `
        <li>
          <strong>${escapeHtml(problem.reason)}</strong>
          — ${escapeHtml(problem.message)}
        </li>
      `;
    })
    .join("");

  serviceDetailsPanel.className =
    `preview-card service-details-card status-border-${status}`;

  serviceDetailsPanel.innerHTML = `
    <div class="preview-heading">
      <p class="eyebrow">RUNTIME STATUS</p>
      <h2>${escapeHtml(service.serviceName)}</h2>
      <span class="environment-badge">
        ${escapeHtml(service.environment)}
      </span>
    </div>

    <div class="result-status runtime-${escapeHtml(status)}">
      ${escapeHtml(statusLabel(status))}
      — ${escapeHtml(service.summary || "Status unavailable")}
    </div>

    ${service.argocd ? `
      <dl class="preview-details">
        <div>
          <dt>Argo CD sync</dt>
          <dd>${escapeHtml(application.syncStatus)}</dd>
        </div>

        <div>
          <dt>Argo CD health</dt>
          <dd>${escapeHtml(application.healthStatus)}</dd>
        </div>

        <div>
          <dt>Ready replicas</dt>
          <dd>
            ${escapeHtml(kubernetes.readyReplicas)} /
            ${escapeHtml(kubernetes.desiredReplicas)}
          </dd>
        </div>
      </dl>
    ` : ""}

    ${problemItems ? `
      <div class="error-list">
        <h3>What needs attention?</h3>
        <ul>${problemItems}</ul>
      </div>
    ` : ""}

    <p class="preview-note">
      Read-only status. Automatically refreshed every 10 seconds.
    </p>
  `;
}


function selectService(key) {
  selectedServiceKey = key;

  document
    .querySelectorAll(".service-card")
    .forEach((card) => {
      card.classList.toggle(
        "is-selected",
        card.dataset.serviceKey === key,
      );
    });

  const selectedService = loadedServices.find(
    (service) => serviceKey(service) === key,
  );

  if (selectedService) {
    renderServiceDetails(selectedService);
  }
}


function renderServiceCatalog(services) {
  loadedServices = services;
  serviceCount.textContent = String(services.length);

  if (!services.length) {
    serviceList.innerHTML = `
      <div class="catalog-loading">
        No managed services were found.
      </div>
    `;
    return;
  }

  serviceList.innerHTML = services
    .map((service) => {
      const key = serviceKey(service);
      const status = service.status || "unavailable";

      const ready = service.kubernetes
        ? `${service.kubernetes.readyReplicas}/` +
          `${service.kubernetes.desiredReplicas} ready`
        : "Runtime unavailable";

      return `
        <button
          class="service-card status-${escapeHtml(status)}"
          type="button"
          data-service-key="${escapeHtml(key)}"
        >
          <span class="service-status-dot"></span>

          <span class="service-card-content">
            <strong>${escapeHtml(service.serviceName)}</strong>

            <small>
              ${escapeHtml(service.environment)} ·
              ${escapeHtml(ready)}
            </small>
          </span>

          <span class="service-card-status">
            ${escapeHtml(statusLabel(status))}
          </span>
        </button>
      `;
    })
    .join("");

  document
    .querySelectorAll(".service-card")
    .forEach((card) => {
      card.addEventListener("click", () => {
        selectService(card.dataset.serviceKey);
      });
    });

  const selectedStillExists = services.some(
    (service) =>
      serviceKey(service) === selectedServiceKey,
  );

  selectService(
    selectedStillExists
      ? selectedServiceKey
      : serviceKey(services[0]),
  );
}


async function loadServiceCatalog() {
  refreshServicesButton.disabled = true;
  refreshServicesButton.textContent = "Refreshing...";

  try {
    const response = await fetch(
      "/api/v1/services/status",
    );

    const result = await response.json();

    if (!response.ok) {
      throw new Error(
        result.summary || "Catalog request failed",
      );
    }

    renderServiceCatalog(
      result.services || [],
    );

    lastUpdated.textContent =
      `Updated ${new Date().toLocaleTimeString()}`;
  } catch (error) {
    console.error(error);

    serviceList.innerHTML = `
      <div class="catalog-error">
        Could not read service status.
      </div>
    `;
  } finally {
    refreshServicesButton.disabled = false;
    refreshServicesButton.textContent = "Refresh now";
  }
}


function stopCatalogRefresh() {
  if (catalogRefreshTimer) {
    clearInterval(catalogRefreshTimer);
    catalogRefreshTimer = null;
  }
}


function startCatalogRefresh() {
  stopCatalogRefresh();

  if (servicesView.hidden || document.hidden) {
    return;
  }

  loadServiceCatalog();

  catalogRefreshTimer = setInterval(
    loadServiceCatalog,
    10000,
  );
}


function showPortalView(viewName) {
  const showServices = viewName === "services";

  createView.hidden = showServices;
  servicesView.hidden = !showServices;

  createTabButton.classList.toggle(
    "is-active",
    !showServices,
  );

  servicesTabButton.classList.toggle(
    "is-active",
    showServices,
  );

  createTabButton.setAttribute(
    "aria-selected",
    !showServices,
  );

  servicesTabButton.setAttribute(
    "aria-selected",
    showServices,
  );

  if (showServices) {
    startCatalogRefresh();
  } else {
    stopCatalogRefresh();
  }
}


form.addEventListener(
  "input",
  () => {
    if (approvedServiceRequest) {
      approvedServiceRequest = null;
      showWaitingForValidation();
    }
  },
);


createTabButton.addEventListener(
  "click",
  () => showPortalView("create"),
);


servicesTabButton.addEventListener(
  "click",
  () => showPortalView("services"),
);


refreshServicesButton.addEventListener(
  "click",
  loadServiceCatalog,
);


document.addEventListener(
  "visibilitychange",
  () => {
    if (document.hidden) {
      stopCatalogRefresh();
    } else if (!servicesView.hidden) {
      startCatalogRefresh();
    }
  },
);


form.addEventListener(
  "submit",
  async (event) => {
    event.preventDefault();

    approvedServiceRequest = null;

    showLoading();

    validateButton.disabled = true;
    validateButton.textContent =
      "Validating...";

    try {
      const serviceRequest =
        buildServiceRequest();

      const response = await fetch(
        "/api/v1/service-requests/validate",
        {
          method: "POST",

          headers: {
            "Content-Type": "application/json",
          },

          body: JSON.stringify(
            serviceRequest,
          ),
        },
      );

      const result = await response.json();

      if (response.ok && result.approved) {
        approvedServiceRequest =
          JSON.parse(
            JSON.stringify(serviceRequest),
          );

        showApproved(result);
      } else {
        showRejected(result);
      }
    } catch (error) {
      console.error(error);
      showConnectionError();
    } finally {
      validateButton.disabled = false;
      validateButton.textContent =
        "Validate request";
    }
  },
);