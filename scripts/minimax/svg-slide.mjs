import { rasterizeSvgToPngDataUri } from "./sharp-rasterizer.mjs";

function esc(text) {
  return String(text || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function toSvgDataUri(svgText) {
  const b64 = Buffer.from(String(svgText || ""), "utf-8").toString("base64");
  // pptxgenjs addImage({data}) expects "mime;base64,<payload>" without "data:" prefix.
  return `image/svg+xml;base64,${b64}`;
}

export function buildSlideSvg(sourceSlide, theme = {}, width = 1600, height = 900) {
  const title = esc(sourceSlide?.title || "Slide");
  const subtitle = esc(sourceSlide?.narration || "");
  const layout = esc(sourceSlide?.layout_grid || "");
  const primary = theme.primary || "2F7BFF";
  const border = theme.borderColor || theme.light || "1E335E";
  const bg = theme.bg || "060B17";
  const cardBg = theme.cardBg || "0D1630";
  const text = theme.darkText || "E8F0FF";
  const muted = theme.mutedText || "95A8CC";

  return [
    `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">`,
    `<rect width="${width}" height="${height}" fill="#${bg}" />`,
    `<rect x="48" y="42" width="${width - 96}" height="84" rx="18" fill="#${cardBg}" stroke="#${border}" stroke-width="2"/>`,
    `<rect x="56" y="76" width="8" height="34" rx="4" fill="#${primary}" />`,
    `<text x="78" y="96" fill="#${text}" font-size="38" font-family="Microsoft YaHei, Segoe UI, Arial" font-weight="700">${title}</text>`,
    subtitle
      ? `<text x="78" y="126" fill="#${muted}" font-size="18" font-family="Microsoft YaHei, Segoe UI, Arial">${subtitle}</text>`
      : "",
    `<text x="${width - 250}" y="96" fill="#${muted}" font-size="16" font-family="Segoe UI, Arial">${layout}</text>`,
    `<rect x="48" y="160" width="${width - 96}" height="${height - 210}" rx="20" fill="#${cardBg}" stroke="#${border}" stroke-width="2"/>`,
    `</svg>`,
  ].join("");
}

function cleanHex(value, fallback = "FFFFFF") {
  const raw = String(value || "").replace("#", "").trim();
  return /^[0-9a-fA-F]{6}$/.test(raw) ? raw.toUpperCase() : fallback;
}

export function buildTerminalPageSvg(kind, payload = {}, theme = {}, width = 1280, height = 720) {
  const primary = cleanHex(theme.primary, "005587");
  const secondary = cleanHex(theme.secondary || theme.accentStrong, "0076A8");
  const accent = cleanHex(theme.accentStrong || theme.accent, "F5A623");
  const bg = cleanHex(theme.white || theme.bg, kind === "toc" ? "F7F8FA" : "FFFFFF");
  const muted = cleanHex(theme.mutedText, "7F8C8D");
  const sections = Array.isArray(payload.sections) ? payload.sections.slice(0, 6).map((item) => String(item || "").trim()).filter(Boolean) : [];
  if (kind === "cover") {
    return [
      `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${width} ${height}">`,
      `<defs><linearGradient id="headerGrad" x1="0%" y1="0%" x2="100%" y2="0%"><stop offset="0%" stop-color="#${primary}"/><stop offset="100%" stop-color="#${secondary}"/></linearGradient><linearGradient id="decoGrad" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" stop-color="#${primary}" stop-opacity="0.12"/><stop offset="100%" stop-color="#${secondary}" stop-opacity="0.04"/></linearGradient></defs>`,
      `<rect width="${width}" height="${height}" fill="#${bg}"/>`,
      `<rect x="0" y="0" width="12" height="${height}" fill="url(#headerGrad)"/>`,
      `<rect x="12" y="0" width="3" height="${height}" fill="#${accent}"/>`,
      `<rect x="60" y="55" width="180" height="5" fill="#${primary}"/>`,
      `<rect x="60" y="65" width="100" height="3" fill="#${secondary}" fill-opacity="0.5"/>`,
      `<rect x="780" y="0" width="500" height="${height}" fill="url(#decoGrad)"/>`,
      `<rect x="850" y="120" width="360" height="360" fill="none" stroke="#${primary}" stroke-width="1" stroke-opacity="0.15"/>`,
      `<rect x="900" y="170" width="260" height="260" fill="none" stroke="#${primary}" stroke-width="1" stroke-opacity="0.1"/>`,
      `<rect x="950" y="220" width="160" height="160" fill="#${primary}" fill-opacity="0.03"/>`,
      `<path d="M 1050,140 L 1220,140 L 1135,320 Z" fill="#${primary}" fill-opacity="0.06"/>`,
      `<path d="M 880,400 L 1000,400 L 940,520 Z" fill="#${secondary}" fill-opacity="0.05"/>`,
      `</svg>`,
    ].join("");
  }

  if (kind === "toc") {
    const rowY = [170, 170, 300, 300, 430, 430];
    const rowX = [60, 660, 60, 660, 60, 660];
    const colors = [primary, secondary, cleanHex(theme.light, "004D5C"), accent, muted, muted];
    const rows = sections.map((_item, idx) => {
      const x = rowX[idx] || 60;
      const y = rowY[idx] || (170 + idx * 110);
      const color = colors[idx] || primary;
      const dashed = idx >= 4 ? ' stroke-dasharray="6,4"' : "";
      const opacity = idx >= 4 ? ' fill="#FAFAFA" stroke="#E5E7EB" stroke-width="1"' : ` fill="#FFFFFF" stroke="#E5E7EB" stroke-width="1.5"`;
      return `
        <g>
          <rect x="${x}" y="${y}" width="560" height="110" ${opacity}${dashed} rx="6"/>
          <rect x="${x}" y="${y}" width="6" height="110" fill="#${color}" rx="3"/>
          <rect x="${x + 20}" y="${y + 20}" width="60" height="60" fill="#${color}" fill-opacity="0.08" rx="4"/>
        </g>`;
    }).join("");
    return [
      `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${width} ${height}">`,
      `<rect width="${width}" height="${height}" fill="#${bg}"/>`,
      `<rect x="0" y="0" width="${width}" height="12" fill="#${primary}"/>`,
      `<rect x="60" y="115" width="180" height="5" fill="#${primary}"/><rect x="245" y="115" width="90" height="5" fill="#${accent}"/>`,
      `${rows}`,
      `<rect x="60" y="580" width="1160" height="60" fill="#F8F9FA" rx="6"/>`,
      `</svg>`,
    ].join("");
  }

  return [
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${width} ${height}">`,
    `<defs><linearGradient id="headerGrad" x1="0%" y1="0%" x2="100%" y2="0%"><stop offset="0%" stop-color="#${primary}"/><stop offset="100%" stop-color="#${secondary}"/></linearGradient><linearGradient id="cardGrad" x1="0%" y1="0%" x2="0%" y2="100%"><stop offset="0%" stop-color="#FAFBFC"/><stop offset="100%" stop-color="#F1F3F4"/></linearGradient></defs>`,
    `<rect width="${width}" height="${height}" fill="#${bg}"/>`,
    `<rect x="0" y="0" width="${width}" height="6" fill="url(#headerGrad)"/>`,
    `<rect x="0" y="0" width="400" height="${height}" fill="#${primary}" fill-opacity="0.02"/>`,
    `<rect x="880" y="0" width="400" height="${height}" fill="#${primary}" fill-opacity="0.02"/>`,
    `<rect x="80" y="100" width="180" height="180" fill="none" stroke="#${primary}" stroke-width="1" stroke-opacity="0.08"/>`,
    `<rect x="1020" y="420" width="180" height="180" fill="none" stroke="#${primary}" stroke-width="1" stroke-opacity="0.08"/>`,
    `<line x1="480" y1="340" x2="600" y2="340" stroke="#${primary}" stroke-width="3"/>`,
    `<circle cx="640" cy="340" r="8" fill="#${accent}"/>`,
    `<line x1="680" y1="340" x2="800" y2="340" stroke="#${primary}" stroke-width="3"/>`,
    `<rect x="390" y="440" width="500" height="150" fill="url(#cardGrad)" stroke="#E5E7EB" stroke-width="1.5" rx="8"/>`,
    `<rect x="390" y="440" width="6" height="150" fill="#${primary}" rx="3"/>`,
    `</svg>`,
  ].join("");
}

export function addSvgOverlay(
  slide,
  svgText,
  position = { x: 0, y: 0, w: 10, h: 5.625 },
  options = {},
) {
  if (!slide || typeof slide.addImage !== "function") return false;
  try {
    const preferPng = Boolean(options?.preferPng);
    const pngWidth = Math.max(
      400,
      Math.round(((Number(position?.w) || 10) / 10) * Number(options?.pngPixelWidth || 1600)),
    );
    const pngHeight = Math.max(
      240,
      Math.round(((Number(position?.h) || 5.625) / 5.625) * Number(options?.pngPixelHeight || 900)),
    );
    const data = preferPng
      ? (
        rasterizeSvgToPngDataUri(svgText, {
          width: pngWidth,
          height: pngHeight,
          density: 420,
        }) || toSvgDataUri(svgText)
      )
      : toSvgDataUri(svgText);
    slide.addImage({
      data,
      x: position.x,
      y: position.y,
      w: position.w,
      h: position.h,
    });
    return true;
  } catch {
    // Keep the render path alive: callers can still render normal PPT elements.
    return false;
  }
}
