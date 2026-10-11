(function () {
    function getTable() {
        return document.querySelector("table[data-columns-table]");
    }

    function getStorageKey(table) {
        return "columns:" + table.dataset.columnsTable;
    }

    function readHeaders(table) {
        const ths = table.querySelectorAll("thead tr th");
        return Array.from(ths).map((th, idx) => {
            const key = th.dataset.colKey || ("col-" + idx);
            th.dataset.colKey = key;
            return { key, label: th.textContent.trim() };
        });
    }

    function defaultState(headers) {
        return headers.map(h => ({ key: h.key, visible: true }));
    }

    function loadState(table, headers) {
        try {
            const raw = localStorage.getItem(getStorageKey(table));
            if (!raw) return defaultState(headers);
            const parsed = JSON.parse(raw);
            const known = new Set(headers.map(h => h.key));
            const filtered = parsed.filter(p => known.has(p.key));
            const missing = headers
                .filter(h => !parsed.find(p => p.key === h.key))
                .map(h => ({ key: h.key, visible: true }));
            return filtered.concat(missing);
        } catch (e) {
            return defaultState(headers);
        }
    }

    function saveState(table, state) {
        localStorage.setItem(getStorageKey(table), JSON.stringify(state));
    }

    function applyState(table, state) {
        const theadRow = table.querySelector("thead tr");
        const ths = Array.from(theadRow.children);

        const headerByKey = {};
        ths.forEach(th => { headerByKey[th.dataset.colKey] = th; });

        state.forEach(item => {
            const th = headerByKey[item.key];
            if (!th) return;
            th.style.display = item.visible ? "" : "none";
        });

        state.forEach(item => {
            const th = headerByKey[item.key];
            if (th) theadRow.appendChild(th);
        });

        const bodyRows = table.querySelectorAll("tbody tr");
        bodyRows.forEach(tr => {
            if (tr.children.length === 1 && tr.children[0].hasAttribute("colspan")) {
                return;
            }
            const cellsByKey = {};
            const tds = Array.from(tr.children);
            tds.forEach(td => {
                const key = td.dataset.colKey;
                if (key) cellsByKey[key] = td;
            });

            state.forEach(item => {
                const td = cellsByKey[item.key];
                if (!td) return;
                td.style.display = item.visible ? "" : "none";
                tr.appendChild(td);
            });
        });
    }

    function buildMenu(table, headers, state, onChange) {
        const list = document.querySelector("[data-cols-list]");
        const resetBtn = document.querySelector("[data-cols-reset]");
        if (!list) return;

        function render() {
            list.innerHTML = "";
            state.forEach((item, index) => {
                const header = headers.find(h => h.key === item.key);
                if (!header) return;

                const li = document.createElement("li");
                li.className = "d-flex align-items-center mb-1";

                const cb = document.createElement("input");
                cb.type = "checkbox";
                cb.className = "form-check-input me-2";
                cb.checked = item.visible;
                cb.addEventListener("change", () => {
                    item.visible = cb.checked;
                    onChange();
                });

                const label = document.createElement("span");
                label.className = "flex-grow-1 small";
                label.textContent = header.label;

                const up = document.createElement("button");
                up.type = "button";
                up.className = "btn btn-sm btn-link p-0 px-1 text-decoration-none";
                up.textContent = "↑";
                up.disabled = index === 0;
                up.addEventListener("click", () => {
                    [state[index - 1], state[index]] = [state[index], state[index - 1]];
                    render();
                    onChange();
                });

                const down = document.createElement("button");
                down.type = "button";
                down.className = "btn btn-sm btn-link p-0 px-1 text-decoration-none";
                down.textContent = "↓";
                down.disabled = index === state.length - 1;
                down.addEventListener("click", () => {
                    [state[index + 1], state[index]] = [state[index], state[index + 1]];
                    render();
                    onChange();
                });

                li.appendChild(cb);
                li.appendChild(label);
                li.appendChild(up);
                li.appendChild(down);
                list.appendChild(li);
            });
        }

        render();

        if (resetBtn) {
            resetBtn.addEventListener("click", () => {
                state.length = 0;
                defaultState(headers).forEach(s => state.push(s));
                render();
                onChange();
            });
        }
    }

    document.addEventListener("DOMContentLoaded", () => {
        const table = getTable();
        if (!table) return;

        const headers = readHeaders(table);
        const state = loadState(table, headers);

        applyState(table, state);

        buildMenu(table, headers, state, () => {
            saveState(table, state);
            applyState(table, state);
        });
    });
})();


document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll("tr[data-href]").forEach(row => {
        row.addEventListener("click", (event) => {
            if (event.target.closest("a, button, input, select, textarea, label")) {
                return;
            }
            window.location.href = row.dataset.href;
        });
    });
});


document.addEventListener("DOMContentLoaded", () => {
    const toggle = document.querySelector("[data-filter-toggle]");
    const panel = document.querySelector("[data-filter-panel]");
    const overlay = document.querySelector("[data-filter-overlay]");
    const close = document.querySelector("[data-filter-close]");

    if (!toggle || !panel || !overlay) return;

    function open() {
        panel.classList.add("open");
        overlay.classList.add("open");
    }

    function hide() {
        panel.classList.remove("open");
        overlay.classList.remove("open");
    }

    toggle.addEventListener("click", open);
    overlay.addEventListener("click", hide);
    if (close) close.addEventListener("click", hide);

    document.addEventListener("keydown", (e) => {
        if (e.key === "Escape") hide();
    });
});


document.addEventListener("DOMContentLoaded", () => {
    const currencySelect = document.getElementById("currency_select");
    const accountSelect = document.getElementById("cash_account_select");
    if (!currencySelect || !accountSelect) return;

    const defaultUsd = accountSelect.dataset.defaultUsd;
    const defaultUzs = accountSelect.dataset.defaultUzs;

    function applyDefault() {
        const cur = currencySelect.value;
        let targetId = "";
        if (cur === "USD") targetId = defaultUsd;
        else if (cur === "UZS") targetId = defaultUzs;
        if (!targetId) return;

        for (const opt of accountSelect.options) {
            if (opt.value === targetId) {
                accountSelect.value = targetId;
                break;
            }
        }
    }

    if (!accountSelect.value) {
        applyDefault();
    }

    currencySelect.addEventListener("change", applyDefault);
});


document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll(".customer-autocomplete").forEach(initCustomerAutocomplete);
    document.querySelectorAll(".phone-autocomplete").forEach(initPhoneAutocomplete);
});


function initCustomerAutocomplete(root) {
    const customersRaw = root.dataset.customers;
    if (!customersRaw) return;
    let customers;
    try {
        customers = JSON.parse(customersRaw);
    } catch (e) {
        return;
    }

    const searchInput = root.querySelector(".customer-search");
    const idInput = root.querySelector(".customer-id");
    const list = root.querySelector(".customer-suggestions");
    if (!searchInput || !list) return;

    let activeIndex = -1;
    let currentItems = [];

    function normalize(str) {
        return (str || "").toLowerCase().trim();
    }

    function filterCustomers(query) {
        const q = normalize(query);
        if (!q) return [];
        const results = [];
        for (const c of customers) {
            const name = normalize(c.full_name);
            const phone = normalize(c.phone);
            if (name.includes(q) || phone.includes(q)) {
                results.push(c);
                if (results.length >= 20) break;
            }
        }
        return results;
    }

    function render(items) {
        list.innerHTML = "";
        activeIndex = -1;
        currentItems = items;

        if (!items.length) {
            const li = document.createElement("li");
            li.className = "empty";
            li.textContent = "Ничего не найдено";
            list.appendChild(li);
            list.classList.add("open");
            return;
        }

        items.forEach((c, i) => {
            const li = document.createElement("li");
            li.dataset.index = i;
            li.innerHTML = `${escapeHtml(c.full_name)}<span class="phone">${escapeHtml(c.phone)}</span>`;
            li.addEventListener("click", () => selectCustomer(c));
            list.appendChild(li);
        });

        list.classList.add("open");
    }

    function escapeHtml(str) {
        return String(str || "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    function selectCustomer(c) {
        if (idInput) idInput.value = c.id;
        searchInput.value = `${c.full_name} · ${c.phone}`;
        list.classList.remove("open");
        list.innerHTML = "";
    }

    function closeList() {
        list.classList.remove("open");
        list.innerHTML = "";
        activeIndex = -1;
    }

    searchInput.addEventListener("input", () => {
        const q = searchInput.value;
        if (idInput) idInput.value = "";
        if (!q.trim()) {
            closeList();
            return;
        }
        const items = filterCustomers(q);
        render(items);
    });

    searchInput.addEventListener("keydown", (e) => {
        if (!list.classList.contains("open")) return;
        const items = currentItems;
        if (!items.length) return;

        if (e.key === "ArrowDown") {
            e.preventDefault();
            activeIndex = (activeIndex + 1) % items.length;
            updateActive();
        } else if (e.key === "ArrowUp") {
            e.preventDefault();
            activeIndex = (activeIndex - 1 + items.length) % items.length;
            updateActive();
        } else if (e.key === "Enter") {
            if (activeIndex >= 0) {
                e.preventDefault();
                selectCustomer(items[activeIndex]);
            }
        } else if (e.key === "Escape") {
            closeList();
        }
    });

    function updateActive() {
        const lis = list.querySelectorAll("li:not(.empty)");
        lis.forEach((li, i) => {
            li.classList.toggle("active", i === activeIndex);
        });
    }

    document.addEventListener("click", (e) => {
        if (!root.contains(e.target)) closeList();
    });
}


function initPhoneAutocomplete(root) {
    const phonesRaw = root.dataset.phones;
    if (!phonesRaw) return;
    let phones;
    try {
        phones = JSON.parse(phonesRaw);
    } catch (e) {
        return;
    }

    const searchInput = root.querySelector(".phone-search");
    const idInput = root.querySelector(".phone-id");
    const list = root.querySelector(".phone-suggestions");
    if (!searchInput || !list) return;

    let activeIndex = -1;
    let currentItems = [];

    function normalize(str) {
        return (str || "").toLowerCase().trim();
    }

    function filterPhones(query) {
        const q = normalize(query);
        if (!q) return [];
        const results = [];
        for (const p of phones) {
            const brand = normalize(p.brand);
            const model = normalize(p.model);
            const imei = normalize(p.imei);
            if (brand.includes(q) || model.includes(q) || imei.includes(q)) {
                results.push(p);
                if (results.length >= 20) break;
            }
        }
        return results;
    }

    function render(items) {
        list.innerHTML = "";
        activeIndex = -1;
        currentItems = items;

        if (!items.length) {
            const li = document.createElement("li");
            li.className = "empty";
            li.textContent = "Ничего не найдено";
            list.appendChild(li);
            list.classList.add("open");
            return;
        }

        items.forEach((p, i) => {
            const li = document.createElement("li");
            li.dataset.index = i;
            const extra = [p.storage, p.color].filter(Boolean).join(" · ");
            let html = `<span class="fw-semibold">${escapeHtml(p.brand)} ${escapeHtml(p.model)}</span>`;
            if (extra) html += `<span class="phone">${escapeHtml(extra)}</span>`;
            if (p.imei) html += `<span class="phone">IMEI: ${escapeHtml(p.imei)}</span>`;
            li.innerHTML = html;
            li.addEventListener("click", () => selectPhone(p));
            list.appendChild(li);
        });

        list.classList.add("open");
    }

    function escapeHtml(str) {
        return String(str || "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    function selectPhone(p) {
        if (idInput) idInput.value = p.id;
        const extra = [p.storage, p.color].filter(Boolean).join(" · ");
        let text = `${p.brand} ${p.model}`;
        if (extra) text += ` · ${extra}`;
        searchInput.value = text;
        list.classList.remove("open");
        list.innerHTML = "";
    }

    function closeList() {
        list.classList.remove("open");
        list.innerHTML = "";
        activeIndex = -1;
    }

    searchInput.addEventListener("input", () => {
        const q = searchInput.value;
        if (idInput) idInput.value = "";
        if (!q.trim()) {
            closeList();
            return;
        }
        const items = filterPhones(q);
        render(items);
    });

    searchInput.addEventListener("keydown", (e) => {
        if (!list.classList.contains("open")) return;
        const items = currentItems;
        if (!items.length) return;

        if (e.key === "ArrowDown") {
            e.preventDefault();
            activeIndex = (activeIndex + 1) % items.length;
            updateActive();
        } else if (e.key === "ArrowUp") {
            e.preventDefault();
            activeIndex = (activeIndex - 1 + items.length) % items.length;
            updateActive();
        } else if (e.key === "Enter") {
            if (activeIndex >= 0) {
                e.preventDefault();
                selectPhone(items[activeIndex]);
            }
        } else if (e.key === "Escape") {
            closeList();
        }
    });

    function updateActive() {
        const lis = list.querySelectorAll("li:not(.empty)");
        lis.forEach((li, i) => {
            li.classList.toggle("active", i === activeIndex);
        });
    }

    document.addEventListener("click", (e) => {
        if (!root.contains(e.target)) closeList();
    });
}