var __watchonceAgent = (function(exports) {
	Object.defineProperty(exports, Symbol.toStringTag, { value: "Module" });
	//#region src/content/descriptor.ts
	var MAX_NAME = 200;
	var MAX_TEXT = 100;
	var TESTID_ATTRS = [
		"data-testid",
		"data-test",
		"data-qa",
		"data-cy"
	];
	var KEPT_ATTRS = [
		...TESTID_ATTRS,
		"type",
		"name",
		"placeholder",
		"aria-label",
		"title",
		"role",
		"href",
		"for"
	];
	var collapse = (s) => (s ?? "").replace(/\s+/g, " ").trim();
	var cap = (s, n) => s.length > n ? s.slice(0, n) : s;
	var GENERATED_ID = [
		/^:[a-z0-9]+:?$/i,
		/^(ember|react-|radix-|headlessui-|mui-|rc_|__next|yui_|ext-gen|gwt-|j_id|ng-|cdk-)/i,
		/[0-9a-f]{8,}/i,
		/\d{4,}/,
		/^(?=.*\d)(?=.*[a-z])[a-z0-9]{12,}$/i
	];
	var HASH = String.raw`(?=[a-z0-9]*\d)[a-z0-9]`;
	var GENERATED_CLASS = [
		/^css-[a-z0-9]+$/i,
		/^sc-[a-z0-9]+$/i,
		/^jsx-\d+$/,
		/^ng-(tns|star|c\d)/,
		new RegExp(`^_${HASH}{5,}$`, "i"),
		new RegExp(`^[a-z0-9_-]+__${HASH}{5}$`, "i"),
		new RegExp(`^[a-z]+-${HASH}{6,}$`, "i")
	];
	var isGeneratedId = (id) => GENERATED_ID.some((re) => re.test(id));
	var isGeneratedClass = (c) => GENERATED_CLASS.some((re) => re.test(c));
	function roleOf(el) {
		const explicit = el.getAttribute("role");
		if (explicit) return explicit.split(/\s+/)[0] ?? null;
		switch (el.tagName.toLowerCase()) {
			case "a": return el.hasAttribute("href") ? "link" : null;
			case "button": return "button";
			case "select": return el.multiple || el.size > 1 ? "listbox" : "combobox";
			case "textarea": return "textbox";
			case "option": return "option";
			case "img": return el.getAttribute("alt") === "" ? "presentation" : "img";
			case "h1":
			case "h2":
			case "h3":
			case "h4":
			case "h5":
			case "h6": return "heading";
			case "li": return "listitem";
			case "summary": return "button";
			case "input": {
				const type = (el.getAttribute("type") ?? "text").toLowerCase();
				if ([
					"button",
					"submit",
					"reset",
					"image"
				].includes(type)) return "button";
				if (type === "checkbox") return "checkbox";
				if (type === "radio") return "radio";
				if (type === "range") return "slider";
				if (type === "number") return "spinbutton";
				if (type === "search") return el.hasAttribute("list") ? "combobox" : "searchbox";
				if ([
					"text",
					"email",
					"tel",
					"url",
					"password",
					""
				].includes(type)) return el.hasAttribute("list") ? "combobox" : "textbox";
				return null;
			}
			default: return null;
		}
	}
	function textOf(node, skip) {
		let out = "";
		for (const child of Array.from(node.childNodes)) {
			if (child === skip) continue;
			if (child.nodeType === Node.TEXT_NODE) out += child.textContent ?? "";
			else if (child.nodeType === Node.ELEMENT_NODE) {
				const e = child;
				if (e.getAttribute("aria-hidden") === "true" || [
					"SCRIPT",
					"STYLE",
					"TEMPLATE"
				].includes(e.tagName)) continue;
				if (e.tagName === "IMG") out += ` ${e.getAttribute("alt") ?? ""} `;
				else out += ` ${textOf(e, skip)} `;
			}
		}
		return out;
	}
	function root(el) {
		const r = el.getRootNode();
		return r instanceof ShadowRoot ? r : el.ownerDocument ?? document;
	}
	function byId(el, id) {
		return root(el).getElementById?.(id) ?? el.ownerDocument?.getElementById(id) ?? null;
	}
	var LABELABLE = /* @__PURE__ */ new Set([
		"INPUT",
		"SELECT",
		"TEXTAREA",
		"BUTTON",
		"METER",
		"OUTPUT",
		"PROGRESS"
	]);
	function labelTextOf(el) {
		if (!LABELABLE.has(el.tagName)) return null;
		const parts = [];
		const id = el.getAttribute("id");
		if (id) for (const label of Array.from(root(el).querySelectorAll(`label[for="${CSS.escape(id)}"]`))) parts.push(textOf(label));
		const wrapping = el.closest("label");
		if (wrapping) parts.push(textOf(wrapping, el));
		return collapse(parts.join(" ")) || null;
	}
	function accessibleName(el) {
		const labelledby = el.getAttribute("aria-labelledby");
		if (labelledby) {
			const text = collapse(labelledby.split(/\s+/).map((id) => byId(el, id)).filter((e) => e !== null).map((e) => textOf(e)).join(" "));
			if (text) return cap(text, MAX_NAME);
		}
		const ariaLabel = collapse(el.getAttribute("aria-label"));
		if (ariaLabel) return cap(ariaLabel, MAX_NAME);
		const tag = el.tagName;
		const type = (el.getAttribute("type") ?? "").toLowerCase();
		if (tag === "INPUT" && [
			"button",
			"submit",
			"reset"
		].includes(type)) {
			const v = collapse(el.value) || (type === "submit" ? "Submit" : type === "reset" ? "Reset" : "");
			if (v) return cap(v, MAX_NAME);
		}
		if (tag === "INPUT" && type === "image") {
			const alt = collapse(el.getAttribute("alt"));
			if (alt) return cap(alt, MAX_NAME);
		}
		const label = labelTextOf(el);
		if (label) return cap(label, MAX_NAME);
		const role = roleOf(el);
		if (role && [
			"button",
			"link",
			"option",
			"heading",
			"tab",
			"menuitem",
			"checkbox",
			"radio",
			"listitem",
			"cell",
			"gridcell"
		].includes(role)) {
			const content = collapse(textOf(el));
			if (content) return cap(content, MAX_NAME);
		}
		const title = collapse(el.getAttribute("title"));
		if (title) return cap(title, MAX_NAME);
		const placeholder = collapse(el.getAttribute("placeholder"));
		return placeholder ? cap(placeholder, MAX_NAME) : null;
	}
	var cssIdent = (s) => CSS.escape(s);
	function isUniqueIn(scope, selector, el) {
		try {
			const found = scope.querySelectorAll(selector);
			return found.length === 1 && found[0] === el;
		} catch {
			return false;
		}
	}
	/** Shortest selector unique within the element's root (document or shadow root). */
	function cssPath(el) {
		const scope = root(el);
		const tag = el.tagName.toLowerCase();
		const id = el.getAttribute("id");
		if (id && !isGeneratedId(id) && isUniqueIn(scope, `#${cssIdent(id)}`, el)) return `#${cssIdent(id)}`;
		for (const attr of TESTID_ATTRS) {
			const v = el.getAttribute(attr);
			if (v && isUniqueIn(scope, `[${attr}="${CSS.escape(v)}"]`, el)) return `[${attr}="${CSS.escape(v)}"]`;
		}
		const name = el.getAttribute("name");
		if (name && isUniqueIn(scope, `${tag}[name="${CSS.escape(name)}"]`, el)) return `${tag}[name="${CSS.escape(name)}"]`;
		const segments = [];
		let node = el;
		while (node && node.nodeType === Node.ELEMENT_NODE) {
			const nodeTag = node.tagName.toLowerCase();
			const nodeId = node.getAttribute("id");
			if (node !== el && nodeId && !isGeneratedId(nodeId) && isUniqueIn(scope, `#${cssIdent(nodeId)}`, node)) {
				segments.unshift(`#${cssIdent(nodeId)}`);
				break;
			}
			let segment = nodeTag + Array.from(node.classList).filter((c) => !isGeneratedClass(c)).slice(0, 2).map((c) => `.${cssIdent(c)}`).join("");
			const parent = node.parentElement;
			if (parent) {
				const sameTag = Array.from(parent.children).filter((c) => c.tagName === node.tagName);
				if (sameTag.length > 1) segment += `:nth-of-type(${sameTag.indexOf(node) + 1})`;
			}
			segments.unshift(segment);
			const candidate = segments.join(" > ");
			if (isUniqueIn(scope, candidate, el)) return candidate;
			node = parent;
		}
		return segments.join(" > ");
	}
	function xPath(el) {
		const parts = [];
		let node = el;
		while (node && node.nodeType === Node.ELEMENT_NODE) {
			const tag = node.tagName.toLowerCase();
			const parent = node.parentElement;
			if (!parent) {
				parts.unshift(tag);
				break;
			}
			const same = Array.from(parent.children).filter((c) => c.tagName === node.tagName);
			parts.unshift(same.length > 1 ? `${tag}[${same.indexOf(node) + 1}]` : tag);
			node = parent;
		}
		return `/${parts.join("/")}`;
	}
	var INTERACTIVE$1 = "a[href],button,input,select,textarea,summary,[role],[tabindex],[contenteditable='true'],label,option,li,td,th";
	function countWhere(scope, predicate) {
		let n = 0;
		for (const e of Array.from(scope.querySelectorAll(INTERACTIVE$1))) if (predicate(e)) n++;
		return n;
	}
	var NEARBY = "label,h1,h2,h3,h4,h5,h6,th,legend,dt,[role=heading],.card-title,caption";
	function nearbyText(el, rect) {
		const own = collapse(textOf(el));
		const cx = rect.x + rect.width / 2;
		const cy = rect.y + rect.height / 2;
		const found = [];
		for (const candidate of Array.from(root(el).querySelectorAll(NEARBY))) {
			if (candidate === el || candidate.contains(el)) continue;
			const text = cap(collapse(textOf(candidate)), 60);
			if (!text || text === own) continue;
			const r = candidate.getBoundingClientRect();
			const d = Math.hypot(r.x + r.width / 2 - cx, r.y + r.height / 2 - cy);
			if (d <= 200 || r.width === 0 && rect.width === 0) found.push([d, text]);
		}
		found.sort((a, b) => a[0] - b[0]);
		return [...new Set(found.map(([, t]) => t))].slice(0, 5);
	}
	function shadowHosts(el) {
		const hosts = [];
		let r = el.getRootNode();
		while (r instanceof ShadowRoot) {
			hosts.unshift(cssPath(r.host));
			r = r.host.getRootNode();
		}
		return hosts;
	}
	function describe(el) {
		const scope = root(el);
		const rect = el.getBoundingClientRect();
		const view = el.ownerDocument?.defaultView;
		const attrs = {};
		for (const a of KEPT_ATTRS) {
			let v = el.getAttribute(a);
			if (a === "href" && v) v = v.split("#")[0].slice(0, 300) || v;
			attrs[a] = v;
		}
		const role = roleOf(el);
		const name = accessibleName(el);
		const tag = el.tagName.toLowerCase();
		const text = [
			"input",
			"select",
			"textarea"
		].includes(tag) ? null : cap(collapse(textOf(el)), MAX_TEXT) || null;
		const label = labelTextOf(el);
		const id = el.getAttribute("id");
		const testidAttr = TESTID_ATTRS.find((a) => el.hasAttribute(a));
		const css = cssPath(el);
		return {
			tag,
			role,
			accessible_name: name,
			text,
			id: id && !isGeneratedId(id) ? id : null,
			classes: Array.from(el.classList).filter((c) => !isGeneratedClass(c)),
			attrs,
			label_text: label,
			css_path: css,
			xpath: xPath(el),
			bbox: [
				Math.round(rect.x),
				Math.round(rect.y),
				Math.round(rect.width),
				Math.round(rect.height)
			],
			viewport: [view?.innerWidth ?? 0, view?.innerHeight ?? 0],
			nearby_text: nearbyText(el, rect),
			is_unique: {
				testid: testidAttr ? scope.querySelectorAll(`[${testidAttr}="${CSS.escape(el.getAttribute(testidAttr))}"]`).length === 1 : null,
				role_name: role && name ? countWhere(scope, (e) => roleOf(e) === role && accessibleName(e) === name) === 1 : null,
				text: text ? countWhere(scope, (e) => e.tagName === el.tagName && cap(collapse(textOf(e)), MAX_TEXT) === text) === 1 : null,
				css: isUniqueIn(scope, css, el),
				label: label ? countWhere(scope, (e) => labelTextOf(e) === label) === 1 : null
			},
			shadow_hosts: shadowHosts(el)
		};
	}
	/** The element an action really targeted: walk up from inner spans/icons to the control. */
	function actionTarget(start) {
		return start.closest("button,a[href],input,select,textarea,summary,label,option,[role=button],[role=link],[role=option],[role=menuitem],[role=tab],[role=checkbox],[role=radio],[role=switch],[role=combobox],[contenteditable='true']") ?? start;
	}
	//#endregion
	//#region src/runner/page-agent.ts
	var INTERACTIVE = [
		"a[href]",
		"button",
		"input:not([type=hidden])",
		"select",
		"textarea",
		"summary",
		"[role=button]",
		"[role=link]",
		"[role=checkbox]",
		"[role=radio]",
		"[role=combobox]",
		"[role=option]",
		"[role=menuitem]",
		"[role=tab]",
		"[role=switch]",
		"[role=textbox]",
		"[contenteditable='true']",
		"[onclick]"
	].join(",");
	var MARK = "data-wo-candidate";
	function visible(el) {
		const rect = el.getBoundingClientRect();
		if (rect.width < 2 || rect.height < 2) return false;
		const style = getComputedStyle(el);
		return style.visibility !== "hidden" && style.display !== "none" && Number(style.opacity) > .05;
	}
	/** Visible interactive elements, each marked with ``data-wo-candidate`` so the runner can
	* address the one it picks. Earlier marks are cleared first. */
	function candidates(limit = 150) {
		for (const old of Array.from(document.querySelectorAll(`[${MARK}]`))) old.removeAttribute(MARK);
		const seen = /* @__PURE__ */ new Set();
		const out = [];
		for (const raw of Array.from(document.querySelectorAll(INTERACTIVE))) {
			const el = actionTarget(raw);
			if (seen.has(el) || !visible(el)) continue;
			seen.add(el);
			const id = `e${out.length + 1}`;
			el.setAttribute(MARK, id);
			out.push({
				id,
				descriptor: describe(el),
				enabled: !el.disabled && el.getAttribute("aria-disabled") !== "true"
			});
			if (out.length >= limit) break;
		}
		return out;
	}
	/** Remove the marks again once a candidate has been chosen (or none was). */
	function clearMarks() {
		for (const el of Array.from(document.querySelectorAll(`[${MARK}]`))) el.removeAttribute(MARK);
	}
	/** The descriptor of one element (to check a positional fallback against the fingerprint). */
	function describeOne(el) {
		return describe(el);
	}
	//#endregion
	exports.candidates = candidates;
	exports.clearMarks = clearMarks;
	exports.describeOne = describeOne;
	return exports;
})({});
