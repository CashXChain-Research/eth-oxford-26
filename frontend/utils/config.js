const API_URL = process.env.NEXT_PUBLIC_API_URL || "/backend";
const WS_URL = process.env.NEXT_PUBLIC_WS_URL;

const toWsBase = (url) => {
	if (!url) return null;
	try {
		const base =
			typeof window !== "undefined" ? window.location.origin : "http://localhost";
		const parsed = new URL(url, base);
		const protocol = parsed.protocol === "https:" ? "wss:" : "ws:";
		return `${protocol}//${parsed.host}`;
	} catch {
		return null;
	}
};

const fallbackWsBase =
	typeof window !== "undefined"
		? `${window.location.protocol === "https:" ? "wss:" : "ws:"}//${window.location.host}`
		: "ws://localhost:3001";

export const API_BASE = API_URL;
export const WS_BASE = WS_URL || toWsBase(API_URL) || fallbackWsBase;
