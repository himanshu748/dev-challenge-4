const themeButtons = [...document.querySelectorAll(".theme-button")];
const modeButtons = [...document.querySelectorAll(".mode-button")];
const filenameField = document.getElementById("filenameField");
const sourceInput = document.getElementById("sourceInput");
const sourceLabel = document.getElementById("sourceLabel");
const resultMeta = document.getElementById("resultMeta");
const emptyState = document.getElementById("emptyState");
const issueList = document.getElementById("issueList");
const logPanel = document.getElementById("logPanel");
const standardsBody = document.getElementById("standardsBody");
const resultsSummary = document.getElementById("resultsSummary");
const consoleStream = document.getElementById("consoleStream");
const setupBtn = document.getElementById("setupBtn");
const reviewBtn = document.getElementById("reviewBtn");
const digestBtn = document.getElementById("digestBtn");
const refreshStandardsBtn = document.getElementById("refreshStandardsBtn");
const statMode = document.getElementById("statMode");
const statIssues = document.getElementById("statIssues");
const statStandards = document.getElementById("statStandards");
const statStatus = document.getElementById("statStatus");

const THEME_KEY = "prreviewiq-theme";
let currentMode = "diff";

themeButtons.forEach((button) => {
  button.addEventListener("click", () => setTheme(button.dataset.theme));
});

modeButtons.forEach((button) => {
  button.addEventListener("click", () => setMode(button.dataset.mode));
});

setupBtn.addEventListener("click", async () => {
  setStatus("Bootstrapping Notion");
  const data = await api("/api/setup", {
    method: "POST",
    body: JSON.stringify({ force: false }),
  });

  resultMeta.textContent = "Knowledge base is ready.";
  statIssues.textContent = "0";
  setStatus("Knowledge base ready");
  renderSummary({
    title: "Notion knowledge base connected",
    description:
      "The Review Insights, Coding Standards, and Team Stats surfaces are ready for live writes.",
    items: [
      { label: "Review Insights", value: data.review_insights_url, href: data.review_insights_url },
      { label: "Team Stats", value: data.team_stats_url, href: data.team_stats_url },
    ],
  });
  renderIssues([]);
  renderLogs(data.logs);
  await loadStandards();
});

reviewBtn.addEventListener("click", async () => {
  const prTitle = document.getElementById("prTitle").value.trim();
  const repoName = document.getElementById("repoName").value.trim();
  const source = sourceInput.value.trim();

  if (!prTitle || !repoName || !source) {
    renderLogs(["PR title, repo, and input content are required."]);
    setStatus("Waiting for required fields");
    return;
  }

  const endpoint = currentMode === "diff" ? "/api/review-pr" : "/api/review-file";
  const payload =
    currentMode === "diff"
      ? {
          diff: source,
          pr_title: prTitle,
          repo: repoName,
        }
      : {
          filename: document.getElementById("filename").value.trim(),
          content: source,
          pr_title: prTitle,
          repo: repoName,
        };

  if (currentMode === "file" && !payload.filename) {
    renderLogs(["Filename is required for single-file reviews."]);
    setStatus("Filename required");
    return;
  }

  setStatus(currentMode === "diff" ? "Reviewing diff" : "Reviewing file");

  const data = await api(endpoint, {
    method: "POST",
    body: JSON.stringify(payload),
  });

  resultMeta.textContent = `${data.issues.length} issue(s) found | ${data.standards_updated} standards updated`;
  statIssues.textContent = String(data.issues.length);
  setStatus(data.issues.length ? "Review complete" : "No issues found");

  renderSummary({
    title: data.issues.length
      ? "Review findings captured"
      : "Clean pass on the latest review",
    description: data.issues.length
      ? "Each finding is ready to inspect below and has been sent to the Notion review knowledge base."
      : "AI did not surface actionable issues in the latest run, so the knowledge base stays clean.",
    items: [
      { label: "Notion target", value: data.notion_url, href: data.notion_url },
      { label: "Standards touched", value: String(data.standards_updated) },
    ],
  });
  renderIssues(data.issues);
  renderLogs(data.logs);
  await loadStandards();
});

digestBtn.addEventListener("click", async () => {
  setStatus("Building weekly digest");
  const data = await api("/api/weekly-digest", {
    method: "POST",
    body: JSON.stringify({}),
  });

  resultMeta.textContent = `${data.report_title} | ${data.notion_url}`;
  statIssues.textContent = "0";
  setStatus("Weekly digest created");
  renderSummary({
    title: data.report_title,
    description: data.summary,
    items: [{ label: "Report page", value: data.notion_url, href: data.notion_url }],
  });
  renderIssues([]);
  renderLogs([data.summary, ...data.logs]);
});

refreshStandardsBtn.addEventListener("click", loadStandards);

setTheme(localStorage.getItem(THEME_KEY) || "signal-room");
setMode("diff");
renderSummary({
  title: "Awaiting a review run",
  description:
    "Feed PRReviewIQ a diff or a file to populate findings, activity logs, and team standards.",
  items: [
    { label: "Workflow", value: "Setup -> Review -> Digest" },
    { label: "Destination", value: "Notion MCP knowledge base" },
  ],
});
renderLogs([
  "Console online.",
  "Run setup to connect the Notion knowledge base.",
  "Paste a diff or switch to single-file mode.",
]);

function setTheme(theme) {
  document.body.dataset.theme = theme;
  themeButtons.forEach((button) =>
    button.classList.toggle("active", button.dataset.theme === theme),
  );
  localStorage.setItem(THEME_KEY, theme);
}

function setMode(mode) {
  currentMode = mode;
  statMode.textContent = mode === "file" ? "Single File" : "PR Diff";
  modeButtons.forEach((button) =>
    button.classList.toggle("active", button.dataset.mode === mode),
  );
  const fileMode = mode === "file";
  filenameField.classList.toggle("hidden", !fileMode);
  sourceLabel.textContent = fileMode ? "File content" : "Raw git diff";
  sourceInput.placeholder = fileMode
    ? "Paste the full file content here"
    : "Paste the output of git diff main...HEAD here";
}

function setStatus(text) {
  statStatus.textContent = text;
}

async function loadStandards() {
  try {
    const data = await api("/api/standards");
    statStandards.textContent = String(data.rules.length);
    renderStandards(data.rules);
    if (data.logs?.length) {
      renderLogs(data.logs);
    }
  } catch (error) {
    statStandards.textContent = "Pending";
    if (!String(error.message).includes("Run POST /api/setup")) {
      renderLogs([error.message]);
    }
  }
}

function renderSummary({ title, description, items }) {
  resultsSummary.innerHTML = `
    <article class="summary-card">
      <span class="section-kicker">Overview</span>
      <h3 class="summary-title">${escapeHtml(title)}</h3>
      <p class="summary-description">${escapeHtml(description)}</p>
    </article>
    ${items
      .map(
        (item) => `
          <article class="summary-card">
            <span class="section-kicker">${escapeHtml(item.label)}</span>
            ${
              item.href
                ? `<strong><a class="summary-link" href="${escapeHtml(item.href)}" target="_blank" rel="noreferrer">${escapeHtml(item.value)}</a></strong>`
                : `<strong>${escapeHtml(item.value)}</strong>`
            }
          </article>
        `,
      )
      .join("")}
  `;
}

function renderIssues(issues) {
  issueList.innerHTML = "";

  if (!issues.length) {
    emptyState.style.display = "block";
    emptyState.textContent =
      "No issue cards to show yet. Once a review finishes, this feed becomes your triage board.";
    return;
  }

  emptyState.style.display = "none";

  issues.forEach((issue) => {
    const card = document.createElement("article");
    card.className = `issue-card ${sanitizeClass(issue.severity)}`;
    card.innerHTML = `
      <div class="issue-topline">
        <div>
          <p class="issue-file">${escapeHtml(issue.file)}</p>
          <h3 class="issue-title">${escapeHtml(issue.message)}</h3>
        </div>
        <div class="badge-row">
          <span class="badge ${escapeHtml(issue.severity)}">${escapeHtml(issue.severity)}</span>
          <span class="badge category">${escapeHtml(issue.category)}</span>
        </div>
      </div>
      <p class="issue-copy">${escapeHtml(issue.explanation)}</p>
      <pre>${escapeHtml(issue.code_snippet)}</pre>
    `;
    issueList.appendChild(card);
  });
}

function renderLogs(logs) {
  const lines = logs?.length ? logs : ["No Notion activity yet."];

  logPanel.innerHTML = "";
  lines.forEach((line) => {
    const row = document.createElement("div");
    row.className = "log-line";
    row.textContent = line;
    logPanel.appendChild(row);
  });

  consoleStream.innerHTML = "";
  lines.slice(0, 4).forEach((line) => {
    const row = document.createElement("div");
    row.className = "stream-line";
    row.textContent = line;
    consoleStream.appendChild(row);
  });
}

function renderStandards(rules) {
  if (!rules.length) {
    standardsBody.innerHTML = `
      <tr>
        <td colspan="5" class="table-empty">No coding standards have been recorded yet.</td>
      </tr>
    `;
    return;
  }

  standardsBody.innerHTML = rules
    .map(
      (rule) => `
        <tr>
          <td>${escapeHtml(rule.rule)}</td>
          <td><span class="table-category">${escapeHtml(rule.category)}</span></td>
          <td>${escapeHtml(String(rule.times_flagged))}</td>
          <td>${escapeHtml(rule.last_seen || "-")}</td>
          <td>${escapeHtml(rule.example)}</td>
        </tr>
      `,
    )
    .join("");
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    ...options,
  });

  let data = {};
  try {
    data = await response.json();
  } catch (error) {
    if (!response.ok) {
      throw new Error(`${response.status} ${response.statusText}`);
    }
    return data;
  }

  if (!response.ok) {
    throw new Error(data.detail || `${response.status} ${response.statusText}`);
  }

  return data;
}

function sanitizeClass(value) {
  return String(value).replaceAll(/[^a-zA-Z0-9_-]/g, "");
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}
