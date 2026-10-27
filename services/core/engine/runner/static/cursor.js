// A visible pointer for the live view: the runner moves it to each element before acting, and
// shows a ripple on clicks. Purely visual: it ignores pointer events and has no text or role,
// so it never changes what the page does or what self-healing sees.
(() => {
	if (window.__woCursor) return;
	const css = `
#__wo-cursor{position:fixed;left:0;top:0;width:22px;height:22px;z-index:2147483647;pointer-events:none;
  transition:transform .35s cubic-bezier(.3,.7,.4,1);transform:translate(-40px,-40px);filter:drop-shadow(0 2px 3px rgba(0,0,0,.45))}
.__wo-ripple{position:fixed;width:34px;height:34px;margin:-17px 0 0 -17px;border-radius:50%;z-index:2147483646;pointer-events:none;
  border:3px solid #2563eb;animation:__wo-ripple .55s ease-out forwards}
@keyframes __wo-ripple{from{transform:scale(.3);opacity:1}to{transform:scale(1.6);opacity:0}}`;
	let cursor = null;
	function ensure() {
		if (cursor && cursor.isConnected) return cursor;
		if (!document.documentElement) return null;
		const style = document.createElement("style");
		style.textContent = css;
		document.documentElement.appendChild(style);
		cursor = document.createElement("div");
		cursor.id = "__wo-cursor";
		cursor.setAttribute("aria-hidden", "true");
		cursor.innerHTML =
			'<svg width="22" height="22" viewBox="0 0 24 24"><path d="M3 2l7.5 19 2.6-7.9L21 10.5z" fill="#111827" stroke="#fff" stroke-width="1.6" stroke-linejoin="round"/></svg>';
		document.documentElement.appendChild(cursor);
		return cursor;
	}
	window.__woCursor = {
		move(x, y) {
			const c = ensure();
			if (c) c.style.transform = `translate(${x - 3}px, ${y - 2}px)`;
		},
		click(x, y) {
			this.move(x, y);
			if (!document.documentElement) return;
			const r = document.createElement("div");
			r.className = "__wo-ripple";
			r.setAttribute("aria-hidden", "true");
			r.style.left = `${x}px`;
			r.style.top = `${y}px`;
			document.documentElement.appendChild(r);
			setTimeout(() => r.remove(), 600);
		},
	};
})();
