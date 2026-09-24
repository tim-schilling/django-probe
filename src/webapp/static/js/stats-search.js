document.querySelectorAll("[data-stats-search]").forEach((input) => {
  if (typeof TomSelect === "undefined") return;

  const form = input.form;
  const source = input.dataset.statsSearch;

  // Only a picked name filters; there is nothing to submit.
  form.hidden = false;
  form.addEventListener("submit", (event) => event.preventDefault());

  const picker = new TomSelect(input, {
    valueField: "key",
    labelField: "key",
    searchField: ["key"],
    // Exact names first, then those starting with the query (or whose last dotted
    // part does, like "atomic"), then anything containing it.
    score(search) {
      const query = search.toLowerCase();
      return (item) => {
        const key = item.key.toLowerCase();
        if (key === query) return 3;
        if (key.startsWith(query) || key.split(".").pop().startsWith(query)) return 2;
        return key.includes(query) ? 1 : 0;
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
          <code>${escape(item.key)}</code>
          <span class="stats-option__meta">${item.source === "setting" ? "Setting" : "API"} · ${escape(item.projects)} projects</span>
        </div>`,
      no_results: () => '<div class="no-results">No matches used by enough projects</div>',
    },
    onItemAdd(value) {
      // Each picked name narrows to the projects also using it.
      const params = new URLSearchParams(new FormData(form));
      params.append("key", value);
      window.location.assign(`${form.action}?${params}`);
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
        // Rarer names would lead to a page withheld for having too few projects.
        const chosen = new FormData(form).getAll("key");
        picker.addOptions(
          data.keys.filter(
            (row) => row.projects >= data.minimum_projects && !chosen.includes(row.key),
          ),
        );
        picker.refreshOptions(picker.isFocused);
      })
      .catch(() => {
        requested = false;
      });
  });
});
