const STORAGE_KEY = "django-probe:command-tabs";

function getTabButtons(tabs) {
  return Array.from(tabs.querySelectorAll(':scope > .tabs__list > [role="tab"]'));
}

function getTabPanels(tabs) {
  return Array.from(tabs.querySelectorAll(':scope > [role="tabpanel"]'));
}

function selectTab(group, value) {
  document.querySelectorAll(`[data-tab-group="${group}"]`).forEach((tabs) => {
    const tabButtons = getTabButtons(tabs);
    const tab = tabButtons.find((candidate) => candidate.dataset.tabValue === value);
    if (!tab) return;

    tabButtons.forEach((candidate) => {
      const selected = candidate === tab;
      candidate.setAttribute("aria-selected", String(selected));
      candidate.tabIndex = selected ? 0 : -1;
    });

    getTabPanels(tabs).forEach((panel) => {
      panel.hidden = panel.getAttribute("aria-labelledby") !== tab.id;
    });
  });
}

document.querySelectorAll("[data-tab-group]").forEach((tabs) => {
  const group = tabs.dataset.tabGroup;
  const tabButtons = getTabButtons(tabs);

  tabButtons.forEach((tab, index) => {
    tab.addEventListener("click", () => {
      selectTab(group, tab.dataset.tabValue);
      // Only package-manager style choices are worth carrying between pages.
      if ("tabEphemeral" in tabs.dataset) return;
      try {
        localStorage.setItem(STORAGE_KEY, tab.dataset.tabValue);
      } catch {
        // Private browsing or disabled storage; the selection just won't persist.
      }
    });

    tab.addEventListener("keydown", (event) => {
      let nextIndex;
      if (event.key === "ArrowRight") nextIndex = (index + 1) % tabButtons.length;
      else if (event.key === "ArrowLeft") nextIndex = (index - 1 + tabButtons.length) % tabButtons.length;
      else if (event.key === "Home") nextIndex = 0;
      else if (event.key === "End") nextIndex = tabButtons.length - 1;
      else return;

      event.preventDefault();
      const nextTab = tabButtons[nextIndex];
      nextTab.focus();
      nextTab.click();
    });
  });
});

let storedValue = null;
try {
  storedValue = localStorage.getItem(STORAGE_KEY);
} catch {
  storedValue = null;
}

if (storedValue) {
  document.querySelectorAll("[data-tab-group]").forEach((tabs) => {
    if (getTabButtons(tabs).some((tab) => tab.dataset.tabValue === storedValue)) {
      selectTab(tabs.dataset.tabGroup, storedValue);
    }
  });
}

function selectTabForHash() {
  const panel = location.hash && document.getElementById(location.hash.slice(1));
  if (!panel || panel.getAttribute("role") !== "tabpanel") return;
  const tabs = panel.closest("[data-tab-group]");
  const tab = document.getElementById(panel.getAttribute("aria-labelledby"));
  if (!tabs || !tab) return;
  selectTab(tabs.dataset.tabGroup, tab.dataset.tabValue);
  panel.scrollIntoView();
}

// A link to a panel's id, like #python-versions, opens that tab.
selectTabForHash();
window.addEventListener("hashchange", selectTabForHash);
