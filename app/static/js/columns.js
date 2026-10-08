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

        // 1. видимость
        state.forEach(item => {
            const th = headerByKey[item.key];
            if (!th) return;
            th.style.display = item.visible ? "" : "none";
        });

        // 2. порядок заголовков
        state.forEach(item => {
            const th = headerByKey[item.key];
            if (th) theadRow.appendChild(th);
        });

        // 3. порядок и видимость ячеек в каждой строке
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
            // Игнорируем клик, если он по ссылке, кнопке или полю формы
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