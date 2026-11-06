import "./style.css";

const root = document.getElementById("app");
const base = import.meta.env.VITE_HRM_API_BASE?.replace(/\/$/, "");
let token, periods = [], selected = null, activeTab = "profile", revision = 0;
let leaveMode = "request", leaveFeedback = "";
const money = new Intl.NumberFormat("vi-VN");
const statuses = { draft: "Nháp", submitted: "Đã gửi", pending_approval: "Chờ duyệt", approved: "Đã duyệt",
    rejected: "Từ chối", taken: "Đã nghỉ", cancelled: "Đã hủy" };

function node(tag, text, props = {}) {
    const element = document.createElement(tag);
    if (text != null) element.textContent = text;
    Object.assign(element, props);
    return element;
}

function card(title, entries, className = "info-card") {
    const section = node("section", null, { className });
    section.append(node("h2", title));
    for (const [label, value] of entries) {
        const row = node("div", null, { className: "row" });
        row.append(node("span", label), node("strong", value || value === 0 ? value : "—"));
        section.append(row);
    }
    return section;
}

async function api(path, body) {
    if (!base || !base.startsWith("https://")) throw new Error("Chưa cấu hình địa chỉ HTTPS của hệ thống nhân sự.");
    const result = await fetch(base + path, {
        method: body ? "POST" : "GET", credentials: "omit",
        headers: { ...(token ? { Authorization: "Bearer " + token } : {}),
            ...(body ? { "Content-Type": "application/json" } : {}) },
        body: body ? JSON.stringify(body) : undefined,
    }).catch(() => { throw new Error("Không kết nối được hệ thống nhân sự. Vui lòng thử lại."); });
    const data = await result.json().catch(() => null);
    if (!result.ok || !data) {
        const error = new Error(data?.message || "Không kết nối được hệ thống nhân sự.");
        error.code = data?.error;
        throw error;
    }
    return data;
}

function showError(container, error) {
    container.append(node("p", error.message || "Có lỗi xảy ra.", { className: "error", role: "alert" }));
}

function button(label, click) {
    return node("button", label, { type: "button", onclick: click });
}

const tabIcons = {
    profile: "M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2 M12 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8",
    time: "M4 7h16v14H4z M4 11h16 M8 3v6 M16 3v6 M8 15h3 M13 15h3",
    leave: "M6 3h8l4 4v14H6z M14 3v5h4 M9 14h6 M12 11v6",
    notices: "M6 9a6 6 0 0 1 12 0c0 6 2 7 2 7H4s2-1 2-7 M10 20h4",
};
const views = { profile: "Hồ sơ", time: "Công & lương", leave: "Nghỉ phép", notices: "Thông báo" };

function tabIcon(key) {
    const namespace = "http://www.w3.org/2000/svg";
    const icon = document.createElementNS(namespace, "svg");
    icon.setAttribute("viewBox", "0 0 24 24");
    icon.setAttribute("aria-hidden", "true");
    const path = document.createElementNS(namespace, "path");
    path.setAttribute("d", tabIcons[key]);
    icon.append(path);
    return icon;
}

function pageHeader(title, description) {
    const header = node("header", null, { className: "page-hero" });
    header.append(node("span", "SMBPLUS / NHÂN SỰ", { className: "login-wordmark" }),
        node("h1", title), node("p", description));
    return header;
}

function quickActions() {
    const actions = node("section", null, { className: "quick-actions" });
    const tiles = node("div", null, { className: "quick-tiles" });
    for (const key of ["time", "leave", "notices"]) {
        const tile = button(null, () => navigate(key));
        tile.append(tabIcon(key), node("span", views[key]));
        tiles.append(tile);
    }
    actions.append(node("h2", "Truy cập nhanh"), tiles);
    return actions;
}

function profileHeader(profile) {
    const header = node("section", null, { className: "profile-hero" });
    const initials = profile.name.trim().split(/\s+/).slice(-2).map((word) => [...word][0]).join("").toUpperCase();
    const avatar = node("div", initials || "NV", { className: "avatar", ariaHidden: "true" });
    if (/^data:image\/(jpeg|png|webp);base64,/.test(profile.avatar || "")) {
        const image = node("img", null, { alt: "", src: profile.avatar });
        image.onerror = () => image.remove();
        avatar.append(image);
    }
    const identity = node("div");
    identity.append(node("p", "HỒ SƠ NHÂN VIÊN", { className: "eyebrow" }), node("h2", profile.name),
        node("p", [profile.position, profile.department].filter(Boolean).join(" · ") || profile.company));
    header.append(avatar, identity);
    return header;
}

function start() {
    if (token) return navigate(activeTab);
    showLogin();
}

function showLogin() {
    const page = node("div", null, { className: "login-page" });
    const cover = node("header", null, { className: "login-cover" });
    cover.append(node("span", "SMBPLUS / NHÂN SỰ", { className: "login-wordmark" }),
        node("div", null, { className: "signal-art", ariaHidden: "true" }),
        node("h1", "Chào mừng trở lại"),
        node("p", "Xem chấm công, phiếu lương và gửi đơn nghỉ phép tại một nơi."));
    const form = node("form", null, { className: "login-form" });
    const employeeCode = node("input", null, { required: true, maxLength: 128,
        autocomplete: "username", placeholder: "Nhập mã nhân viên" });
    const code = node("input", null, { inputMode: "numeric", maxLength: 6, required: true, pattern: "[0-9]{6}",
        type: "password", autocomplete: "one-time-code", placeholder: "Nhập 6 chữ số" });
    const employeeLabel = node("label", "Mã nhân viên");
    const codeLabel = node("label", "Mã 6 số");
    employeeLabel.append(employeeCode);
    codeLabel.append(code);
    const submit = node("button", null, { type: "submit", className: "login-submit" });
    const submitText = node("span", "Đăng nhập");
    submit.append(submitText, node("span", "→", { ariaHidden: "true" }));
    form.append(node("h2", "Đăng nhập"), employeeLabel, codeLabel, submit);
    const panel = node("div", null, { className: "login-panel" });
    panel.append(form, node("p", "Cần mã đăng nhập? Liên hệ bộ phận nhân sự.", { className: "login-help" }));
    page.append(cover, panel);
    root.replaceChildren(page);
    let submitting = false;
    form.onsubmit = async (event) => {
        event.preventDefault();
        if (submitting) return;
        submitting = true;
        form.querySelector(".error")?.remove();
        submit.disabled = true;
        submitText.textContent = "Đang đăng nhập…";
        try {
            const result = await api("/login", {
                employee_code: employeeCode.value.trim(), code: code.value,
            });
            token = result.session_token;
            await navigate("profile");
        } catch (error) {
            showError(form, error);
        } finally {
            submitting = false;
            submit.disabled = false;
            submitText.textContent = "Đăng nhập";
        }
    };
}

async function navigate(tab) {
    activeTab = tab;
    const current = ++revision;
    const nav = node("nav", null, { ariaLabel: "Chức năng nhân sự", className: "bottom-nav" });
    for (const [key, title] of Object.entries(views)) {
        const item = button(null, () => navigate(key));
        item.append(tabIcon(key), node("span", title));
        item.className = activeTab === key ? "active" : "";
        item.setAttribute("aria-pressed", String(tab === key));
        nav.append(item);
    }
    const screen = node("div", null, { className: "app-screen screen-" + tab });
    const content = node("div", null, { className: "screen-content" });
    const descriptions = { time: "Lịch sử chấm công và phiếu lương theo tháng.",
        leave: "Gửi yêu cầu và theo dõi kết quả duyệt.", notices: "Tin tức và sự kiện từ bộ phận nhân sự." };
    if (tab !== "profile") screen.append(pageHeader(views[tab], descriptions[tab]));
    screen.append(content, nav);
    root.replaceChildren(screen);
    content.append(node("p", "Đang tải…", { className: "empty", role: "status" }));
    try {
        if (tab === "profile") {
            const profile = await api("/profile");
            content.replaceChildren(profileHeader(profile), quickActions(), card("Thông tin công việc", [["Mã nhân viên", profile.employee_code],
                ["Công ty", profile.company], ["Phòng ban", profile.department], ["Chức vụ", profile.position],
                ["Dự án", profile.projects.join(", ")]]));
        } else if (tab === "time") {
            const periodData = await api("/periods");
            if (current !== revision) return;
            periods = periodData.items;
            const select = node("select", null, { ariaLabel: "Kỳ công và lương" });
            selected = periods.some((p) => p.id === selected) ? selected : periodData.current_id ?? periods[0]?.id;
            periods.forEach((p) => select.append(node("option", p.label, { value: p.id, selected: p.id === selected })));
            const detail = node("div");
            select.onchange = () => {
                selected = Number(select.value);
                navigate("time");
            };
            content.replaceChildren(select, detail);
            if (!selected) return detail.append(node("p", "Chưa có kỳ công và lương."));
            const data = await api("/periods/" + selected);
            const total = data.attendance.reduce((sum, day) => sum + day.hours, 0);
            const overtime = data.attendance.reduce((sum, day) => sum + day.overtime, 0);
            detail.append(card("Tổng công trong kỳ", [["Giờ thường", money.format(total)], ["Giờ tăng ca", money.format(overtime)]], "work-summary"),
                card("Lịch sử công theo ngày", data.attendance.map((day) => [dateLabel(day.date),
                    [day.symbol, money.format(day.hours) + " giờ", day.overtime ? "+" + money.format(day.overtime) + " giờ OT" : ""]
                        .filter(Boolean).join(" · ")])));
            const salary = data.salary;
            const format = (value) => money.format(value) + " " + salary.currency;
            detail.append(salary ? card("Phiếu lương", [["Tổng thu nhập", format(salary.gross)],
                ["Khấu trừ", format(salary.deductions)], ["Thuế", format(salary.tax)], ["Thực nhận", format(salary.net)]], "salary-summary")
                : node("p", "Chưa có phiếu lương đã chốt cho kỳ này."));
        } else if (tab === "leave") {
            const data = await api("/leave");
            if (current === revision) renderLeave(content, data);
        } else {
            const data = await api("/notices");
            content.replaceChildren();
            if (!data.items.length) content.append(node("p", "Chưa có thông báo.", { className: "empty" }));
            for (const notice of data.items) {
                const section = node("section", null, { className: "notice-card" });
                if (notice.important) section.append(node("small", "Sự kiện quan trọng"));
                section.append(node("h2", notice.title), node("p", notice.body));
                if (/^data:image\/(jpeg|png|webp);base64,/.test(notice.image || "")) {
                    section.append(node("img", null, { src: notice.image, alt: "Ảnh thông báo", loading: "lazy" }));
                }
                content.append(section);
            }
        }
    } catch (error) {
        if (current !== revision) return;
        if (error.code === "session_expired") {
            token = null;
            showLogin();
            showError(root.querySelector("form"), error);
            return;
        }
        content.replaceChildren();
        showError(content, error);
        content.append(button("Tải lại", start));
    }
}

const dateLabel = (value) => value.split("-").reverse().join("/");

function renderLeave(content, data) {
    const controls = node("div", null, { className: "segmented" });
    for (const [mode, label] of [["history", "Đơn của tôi"], ["request", "Tạo ticket"]]) {
        const item = button(label, () => {
            leaveMode = mode;
            renderLeave(content, data);
        });
        item.setAttribute("aria-pressed", String(mode === leaveMode));
        controls.append(item);
    }
    content.replaceChildren(controls);
    if (leaveFeedback) {
        content.append(node("p", leaveFeedback, { className: "success", role: "status" }));
        leaveFeedback = "";
    }
    if (leaveMode === "request") {
        content.append(leaveForm(data.options || []));
        return;
    }
    if (!data.items.length) {
        content.append(node("p", "Bạn chưa có đơn nghỉ phép.", { className: "empty" }));
        return;
    }
    for (const row of data.items) {
        const entry = node("section", null, { className: "leave-card" });
        const heading = node("div", null, { className: "leave-heading" });
        heading.append(node("h2", row.type), node("span", statuses[row.status] || row.status, {
            className: "status status-" + row.status,
        }));
        const range = row.start === row.end ? dateLabel(row.start) : dateLabel(row.start) + " → " + dateLabel(row.end);
        entry.append(heading, node("p", range + " · " + (row.minutes ? row.minutes + " phút" : money.format(row.days) + " ngày")));
        if (row.reason) entry.append(node("p", row.reason, { className: "leave-reason" }));
        content.append(entry);
    }
}

function leaveForm(options) {
    const form = node("form");
    const kind = node("select", null, { required: true });
    kind.append(node("option", "Chọn loại yêu cầu", { value: "", disabled: true, selected: true }));
    options.forEach((option) => kind.append(node("option", option.label, { value: option.kind })));
    const duration = node("select");
    const first = node("input", null, { type: "date", required: true });
    const last = node("input", null, { type: "date", required: true });
    const reason = node("textarea", null, { placeholder: "Nhập lý do nghỉ", required: true, maxLength: 1000, rows: 3 });
    const kindLabel = node("label", "Loại yêu cầu"), reasonLabel = node("label", "Lý do");
    const startLabel = node("label", "Ngày áp dụng"), endLabel = node("label", "Đến ngày", { hidden: true });
    const durationLabel = node("label", "Thời lượng", { hidden: true });
    durationLabel.append(duration);
    kindLabel.append(kind);
    reasonLabel.append(reason);
    startLabel.append(first);
    endLabel.append(last);
    const submit = node("button", "Gửi yêu cầu", { type: "submit", className: "primary-action" });
    const dates = node("div", null, { className: "date-fields" });
    dates.append(startLabel, endLabel);
    last.disabled = true;
    first.onchange = () => { last.min = first.value; };
    kind.onchange = () => {
        const option = options.find((item) => item.kind === kind.value);
        endLabel.hidden = last.disabled = option.kind !== "days";
        durationLabel.hidden = !option.minutes.length;
        duration.replaceChildren(...option.minutes.map((minutes) =>
            node("option", minutes % 60 ? minutes + " phút" : minutes / 60 + " giờ", { value: minutes })));
    };
    form.append(node("h2", "Tạo ticket"), kindLabel, dates, durationLabel, reasonLabel, submit);
    form.onsubmit = async (event) => {
        event.preventDefault();
        form.querySelector(".error")?.remove();
        submit.disabled = true;
        try {
            await api("/leave", { kind: kind.value, minutes: Number(duration.value), start: first.value,
                end: last.disabled ? first.value : last.value, reason: reason.value });
            leaveMode = "history";
            leaveFeedback = "Đã gửi yêu cầu. Nhân sự sẽ xem và duyệt.";
            if (activeTab === "leave") await navigate("leave");
        } catch (error) {
            showError(form, error);
        } finally {
            submit.disabled = false;
        }
    };
    return form;
}

start();
