const SOURCE_LABELS = { setting: "Setting", usage: "API", dependency: "Dependency" };

document.querySelectorAll("[data-stats-search]").forEach((input) => {
  if (typeof TomSelect === "undefined") return;

  const form = input.form;
  const source = input.dataset.statsSearch;

  // Only a picked name filters; there is nothing to submit.
  form.hidden = false;
  form.addEventListener("submit", (event) => event.preventDefault());

  const picker = new TomSelect(input, {
    valueField: "key",
    labelField: "name",
    searchField: ["name"],
    // Exact names first, then those starting with the query (or whose last dotted
    // part does, like "atomic"), then anything containing it.
    score(search) {
      const query = search.toLowerCase();
      return (item) => {
        const name = item.name.toLowerCase();
        if (name === query) return 3;
        if (name.startsWith(query) || name.split(".").pop().startsWith(query)) return 2;
        return name.includes(query) ? 1 : 0;
      };
    },
    sortField: [
      { field: "$score", direction: "desc" },
      { field: "projects", direction: "desc" },
    ],
    maxItems: 1,
    maxOptions: 50,
    create: false,
    render: {
      option: (item, escape) => `
        <div class="stats-option">
          <code>${escape(item.name)}</code>
          <span class="stats-option__meta">${escape(SOURCE_LABELS[item.source])} · ${escape(item.projects)} projects</span>
        </div>`,
      no_results: () => '<div class="no-results">No matches used by enough projects</div>',
    },
    onItemAdd(value) {
      // Each picked name narrows to the projects also using it.
      const params = new URLSearchParams(new FormData(form));
      params.append("key", value);
      // Unescaped like the server's canonical URLs, to skip a redirect.
      window.location.assign(`${form.action}?${params.toString().replaceAll("%3A", ":")}`);
    },
  });

  // The whole list is one cached request, fetched the first time it's needed.
  let requested = false;
  picker.on("focus", () => {
    if (requested) return;
    requested = true;
    fetch(source)
      .then((response) => response.json())
      .then((data) => {
        // A name without a count would lead to a page withheld for too few projects.
        const chosen = new FormData(form).getAll("key");
        picker.addOptions(
          data.keys.filter((row) => row.projects !== null && !chosen.includes(row.key)),
        );
        picker.refreshOptions(picker.isFocused);
      })
      .catch(() => {
        requested = false;
      });
  });
});
