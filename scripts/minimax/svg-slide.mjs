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
