const SLIDE_W = 10;
const SLIDE_H = 5.625;

function toNumber(value, fallback = 0) {
  const n = Number(String(value ?? "").replace(/[^\d+-.eE]/g, ""));
  return Number.isFinite(n) ? n : fallback;
}

function cleanHex(value, fallback = "000000") {
  const v = String(value || "").trim().replace("#", "");
  return /^[0-9a-fA-F]{6}$/.test(v) ? v.toUpperCase() : fallback;
}

function decodeHtmlEntities(text) {
  return String(text || "")
    .replace(/&nbsp;/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, "\"")
    .replace(/&#39;/g, "'");
}

function parseAttrs(attrText = "") {
  const attrs = {};
  const re = /([a-zA-Z_:][-a-zA-Z0-9_:.]*)\s*=\s*(?:"([^"]*)"|'([^']*)')/g;
  let match;
  while ((match = re.exec(String(attrText))) !== null) {
    const key = String(match[1] || "").trim();
    const value = match[2] ?? match[3] ?? "";
    if (key) attrs[key] = value;
  }
  if (attrs.style) {
    const styleParts = String(attrs.style)
      .split(";")
      .map((item) => item.trim())
      .filter(Boolean);
    for (const item of styleParts) {
      const [k, v] = item.split(":");
      const key = String(k || "").trim();
      const val = String(v || "").trim();
      if (!key || !val || attrs[key] !== undefined) continue;
      attrs[key] = val;
    }
  }
  return attrs;
}

function readSvgCanvas(svgMarkup) {
  const rootMatch = String(svgMarkup || "").match(/<svg\b([^>]*)>/i);
  const attrs = parseAttrs(rootMatch?.[1] || "");
  let width = toNumber(attrs.width, 0);
  let height = toNumber(attrs.height, 0);
  if ((!width || !height) && attrs.viewBox) {
    const parts = String(attrs.viewBox)
      .trim()
      .split(/[\s,]+/)
      .map((v) => Number(v));
    if (parts.length === 4 && Number.isFinite(parts[2]) && Number.isFinite(parts[3])) {
      width = parts[2];
      height = parts[3];
    }
  }
  if (!width) width = 960;
  if (!height) height = 540;
  return { width, height, attrs };
}

export function resolveSlideSvgMarkup(sourceSlide = {}) {
  const direct = [sourceSlide?.svg_markup, sourceSlide?.svg, sourceSlide?.svgMarkup];
  for (const value of direct) {
    const text = String(value || "").trim();
    if (text.startsWith("<svg")) return text;
  }
  const blocks = Array.isArray(sourceSlide?.blocks) ? sourceSlide.blocks : [];
  for (const block of blocks) {
    const blockType = String(block?.block_type || block?.type || "").trim().toLowerCase();
    if (blockType !== "svg") continue;
    const content = block?.content;
    if (typeof content === "string" && content.trim().startsWith("<svg")) return content.trim();
    if (content && typeof content === "object") {
      for (const key of ["svg", "markup", "svg_markup"]) {
        const val = String(content[key] || "").trim();
        if (val.startsWith("<svg")) return val;
      }
    }
  }
  return "";
}

export function parseSvgElements(svgMarkup) {
  const svg = String(svgMarkup || "");
  const canvas = readSvgCanvas(svg);
  const elements = [];

  const textPattern = /<text\b([^>]*)>([\s\S]*?)<\/text>/gi;
  let textMatch;
  while ((textMatch = textPattern.exec(svg)) !== null) {
    elements.push({
      type: "text",
      attrs: parseAttrs(textMatch[1] || ""),
      content: decodeHtmlEntities(String(textMatch[2] || "").replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim()),
    });
  }

  const svgWithoutText = svg.replace(textPattern, "");
  const shapePattern = /<(rect|circle|ellipse|line|path)\b([^>]*)\/?>/gi;
  let shapeMatch;
  while ((shapeMatch = shapePattern.exec(svgWithoutText)) !== null) {
    elements.push({
      type: String(shapeMatch[1] || "").toLowerCase(),
      attrs: parseAttrs(shapeMatch[2] || ""),
      content: "",
    });
  }
  return {
    width: canvas.width,
    height: canvas.height,
    elements,
  };
}

function toInchesX(x, svgWidth) {
  return (toNumber(x, 0) / Math.max(1, svgWidth)) * SLIDE_W;
}

function toInchesY(y, svgHeight) {
  return (toNumber(y, 0) / Math.max(1, svgHeight)) * SLIDE_H;
}

function tokenizePath(d = "") {
  const out = [];
  const re = /([MmLlHhVvCcSsQqTtAaZz])|(-?\d*\.?\d+(?:e[-+]?\d+)?)/g;
  let match;
  while ((match = re.exec(String(d))) !== null) {
    if (match[1]) out.push(match[1]);
    else if (match[2] !== undefined) out.push(Number(match[2]));
  }
  return out;
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function signedAngle(ux, uy, vx, vy) {
  const denom = Math.sqrt((ux * ux + uy * uy) * (vx * vx + vy * vy));
  if (!Number.isFinite(denom) || denom <= 1e-12) return 0;
  const dot = clamp((ux * vx + uy * vy) / denom, -1, 1);
  const sign = ux * vy - uy * vx < 0 ? -1 : 1;
  return sign * Math.acos(dot);
}

function arcToCubicSegments({
  x1,
  y1,
  rx,
  ry,
  phiDeg,
  largeArcFlag,
  sweepFlag,
  x2,
  y2,
}) {
  const rxAbs = Math.abs(Number(rx) || 0);
  const ryAbs = Math.abs(Number(ry) || 0);
  if (rxAbs <= 1e-9 || ryAbs <= 1e-9) return [];
  if (Math.abs(x1 - x2) <= 1e-9 && Math.abs(y1 - y2) <= 1e-9) return [];

  const phi = (Number(phiDeg) || 0) * (Math.PI / 180);
  const cosPhi = Math.cos(phi);
  const sinPhi = Math.sin(phi);
  const dx2 = (x1 - x2) / 2;
  const dy2 = (y1 - y2) / 2;
  const x1p = cosPhi * dx2 + sinPhi * dy2;
  const y1p = -sinPhi * dx2 + cosPhi * dy2;

  let rxAdj = rxAbs;
  let ryAdj = ryAbs;
  const lambda = (x1p * x1p) / (rxAdj * rxAdj) + (y1p * y1p) / (ryAdj * ryAdj);
  if (lambda > 1) {
    const scale = Math.sqrt(lambda);
    rxAdj *= scale;
    ryAdj *= scale;
  }

  const rxSq = rxAdj * rxAdj;
  const rySq = ryAdj * ryAdj;
  const x1pSq = x1p * x1p;
  const y1pSq = y1p * y1p;
  const numerator = Math.max(0, rxSq * rySq - rxSq * y1pSq - rySq * x1pSq);
  const denominator = Math.max(1e-12, rxSq * y1pSq + rySq * x1pSq);
  const coefSign = Number(largeArcFlag) === Number(sweepFlag) ? -1 : 1;
  const coef = coefSign * Math.sqrt(numerator / denominator);
  const cxp = coef * ((rxAdj * y1p) / Math.max(1e-12, ryAdj));
  const cyp = coef * (-(ryAdj * x1p) / Math.max(1e-12, rxAdj));

  const cx = cosPhi * cxp - sinPhi * cyp + (x1 + x2) / 2;
  const cy = sinPhi * cxp + cosPhi * cyp + (y1 + y2) / 2;

  const ux = (x1p - cxp) / rxAdj;
  const uy = (y1p - cyp) / ryAdj;
  const vx = (-x1p - cxp) / rxAdj;
  const vy = (-y1p - cyp) / ryAdj;
  let theta1 = signedAngle(1, 0, ux, uy);
  let deltaTheta = signedAngle(ux, uy, vx, vy);
  if (!Number(sweepFlag) && deltaTheta > 0) deltaTheta -= Math.PI * 2;
  if (Number(sweepFlag) && deltaTheta < 0) deltaTheta += Math.PI * 2;

  const segmentsCount = Math.max(1, Math.ceil(Math.abs(deltaTheta) / (Math.PI / 2)));
  const step = deltaTheta / segmentsCount;
  const mapUnitPoint = (uxPoint, uyPoint) => ({
    x: cx + rxAdj * cosPhi * uxPoint - ryAdj * sinPhi * uyPoint,
    y: cy + rxAdj * sinPhi * uxPoint + ryAdj * cosPhi * uyPoint,
  });
  const segments = [];
  for (let idx = 0; idx < segmentsCount; idx += 1) {
    const t1 = theta1 + idx * step;
    const t2 = t1 + step;
    const sinT1 = Math.sin(t1);
    const cosT1 = Math.cos(t1);
    const sinT2 = Math.sin(t2);
    const cosT2 = Math.cos(t2);
    const alpha = (4 / 3) * Math.tan((t2 - t1) / 4);
    const p1 = { x: cosT1, y: sinT1 };
    const p2 = { x: cosT2, y: sinT2 };
    const c1 = { x: p1.x - alpha * p1.y, y: p1.y + alpha * p1.x };
    const c2 = { x: p2.x + alpha * p2.y, y: p2.y - alpha * p2.x };
    const mappedC1 = mapUnitPoint(c1.x, c1.y);
    const mappedC2 = mapUnitPoint(c2.x, c2.y);
    const mappedP2 = mapUnitPoint(p2.x, p2.y);
    segments.push({
      c1x: mappedC1.x,
      c1y: mappedC1.y,
      c2x: mappedC2.x,
      c2y: mappedC2.y,
      x: mappedP2.x,
      y: mappedP2.y,
    });
  }
  return segments;
}

export function svgPathToCustomGeometryPoints(d, { svgWidth = 960, svgHeight = 540 } = {}) {
  const tokens = tokenizePath(d);
  const points = [];
  let i = 0;
  let cmd = "";
  let cx = 0;
  let cy = 0;
  let subpathStartX = 0;
  let subpathStartY = 0;
  let prevUpper = "";
  let lastCubicControlX = null;
  let lastCubicControlY = null;
  let lastQuadraticControlX = null;
  let lastQuadraticControlY = null;

  const readNum = () => {
    const token = tokens[i];
    if (typeof token !== "number" || !Number.isFinite(token)) return null;
    i += 1;
    return token;
  };

  const pushPoint = (x, y, curve = null) => {
    const point = {
      x: toInchesX(x, svgWidth),
      y: toInchesY(y, svgHeight),
    };
    if (curve && typeof curve === "object") point.curve = curve;
    points.push(point);
  };

  while (i < tokens.length) {
    if (typeof tokens[i] === "string") {
      cmd = tokens[i];
      i += 1;
    }
    if (!cmd) break;

    if (cmd === "Z" || cmd === "z") {
      points.push({ close: true });
      cx = subpathStartX;
      cy = subpathStartY;
      prevUpper = "Z";
      lastCubicControlX = null;
      lastCubicControlY = null;
      lastQuadraticControlX = null;
      lastQuadraticControlY = null;
      cmd = "";
      continue;
    }

    const isRelative = cmd === cmd.toLowerCase();
    const upper = cmd.toUpperCase();

    if (upper === "M") {
      const x = readNum();
      const y = readNum();
      if (x === null || y === null) break;
      cx = isRelative ? cx + x : x;
      cy = isRelative ? cy + y : y;
      subpathStartX = cx;
      subpathStartY = cy;
      pushPoint(cx, cy);
      prevUpper = "M";
      lastCubicControlX = null;
      lastCubicControlY = null;
      lastQuadraticControlX = null;
      lastQuadraticControlY = null;
      cmd = isRelative ? "l" : "L";
      continue;
    }

    if (upper === "H") {
      const x = readNum();
      if (x === null) break;
      cx = isRelative ? cx + x : x;
      pushPoint(cx, cy);
      prevUpper = "H";
      lastCubicControlX = null;
      lastCubicControlY = null;
      lastQuadraticControlX = null;
      lastQuadraticControlY = null;
      continue;
    }

    if (upper === "V") {
      const y = readNum();
      if (y === null) break;
      cy = isRelative ? cy + y : y;
      pushPoint(cx, cy);
      prevUpper = "V";
      lastCubicControlX = null;
      lastCubicControlY = null;
      lastQuadraticControlX = null;
      lastQuadraticControlY = null;
      continue;
    }

    if (upper === "L") {
      const x = readNum();
      const y = readNum();
      if (x === null || y === null) break;
      cx = isRelative ? cx + x : x;
      cy = isRelative ? cy + y : y;
      pushPoint(cx, cy);
      prevUpper = "L";
      lastCubicControlX = null;
      lastCubicControlY = null;
      lastQuadraticControlX = null;
      lastQuadraticControlY = null;
      continue;
    }

    if (upper === "Q") {
      const x1 = readNum();
      const y1 = readNum();
      const x = readNum();
      const y = readNum();
      if ([x1, y1, x, y].some((item) => item === null)) break;
      const c1x = isRelative ? cx + x1 : x1;
      const c1y = isRelative ? cy + y1 : y1;
      cx = isRelative ? cx + x : x;
      cy = isRelative ? cy + y : y;
      pushPoint(cx, cy, {
        type: "quadratic",
        x1: toInchesX(c1x, svgWidth),
        y1: toInchesY(c1y, svgHeight),
      });
      prevUpper = "Q";
      lastQuadraticControlX = c1x;
      lastQuadraticControlY = c1y;
      lastCubicControlX = null;
      lastCubicControlY = null;
      continue;
    }

    if (upper === "T") {
      const x = readNum();
      const y = readNum();
      if ([x, y].some((item) => item === null)) break;
      const c1x =
        (prevUpper === "Q" || prevUpper === "T") && Number.isFinite(lastQuadraticControlX)
          ? cx * 2 - lastQuadraticControlX
          : cx;
      const c1y =
        (prevUpper === "Q" || prevUpper === "T") && Number.isFinite(lastQuadraticControlY)
          ? cy * 2 - lastQuadraticControlY
          : cy;
      cx = isRelative ? cx + x : x;
      cy = isRelative ? cy + y : y;
      pushPoint(cx, cy, {
        type: "quadratic",
        x1: toInchesX(c1x, svgWidth),
        y1: toInchesY(c1y, svgHeight),
      });
      prevUpper = "T";
      lastQuadraticControlX = c1x;
      lastQuadraticControlY = c1y;
      lastCubicControlX = null;
      lastCubicControlY = null;
      continue;
    }

    if (upper === "C") {
      const x1 = readNum();
      const y1 = readNum();
      const x2 = readNum();
      const y2 = readNum();
      const x = readNum();
      const y = readNum();
      if ([x1, y1, x2, y2, x, y].some((item) => item === null)) break;
      const c1x = isRelative ? cx + x1 : x1;
      const c1y = isRelative ? cy + y1 : y1;
      const c2x = isRelative ? cx + x2 : x2;
      const c2y = isRelative ? cy + y2 : y2;
      cx = isRelative ? cx + x : x;
      cy = isRelative ? cy + y : y;
      pushPoint(cx, cy, {
        type: "cubic",
        x1: toInchesX(c1x, svgWidth),
        y1: toInchesY(c1y, svgHeight),
        x2: toInchesX(c2x, svgWidth),
        y2: toInchesY(c2y, svgHeight),
      });
      prevUpper = "C";
      lastCubicControlX = c2x;
      lastCubicControlY = c2y;
      lastQuadraticControlX = null;
      lastQuadraticControlY = null;
      continue;
    }

    if (upper === "S") {
      const x2 = readNum();
      const y2 = readNum();
      const x = readNum();
      const y = readNum();
      if ([x2, y2, x, y].some((item) => item === null)) break;
      const c1x =
        (prevUpper === "C" || prevUpper === "S") && Number.isFinite(lastCubicControlX)
          ? cx * 2 - lastCubicControlX
          : cx;
      const c1y =
        (prevUpper === "C" || prevUpper === "S") && Number.isFinite(lastCubicControlY)
          ? cy * 2 - lastCubicControlY
          : cy;
      const c2x = isRelative ? cx + x2 : x2;
      const c2y = isRelative ? cy + y2 : y2;
      cx = isRelative ? cx + x : x;
      cy = isRelative ? cy + y : y;
      pushPoint(cx, cy, {
        type: "cubic",
        x1: toInchesX(c1x, svgWidth),
        y1: toInchesY(c1y, svgHeight),
        x2: toInchesX(c2x, svgWidth),
        y2: toInchesY(c2y, svgHeight),
      });
      prevUpper = "S";
      lastCubicControlX = c2x;
      lastCubicControlY = c2y;
      lastQuadraticControlX = null;
      lastQuadraticControlY = null;
      continue;
    }

    if (upper === "A") {
      const rx = readNum();
      const ry = readNum();
      const xAxisRotation = readNum();
      const largeArcFlag = readNum();
      const sweepFlag = readNum();
      const x = readNum();
      const y = readNum();
      if ([rx, ry, xAxisRotation, largeArcFlag, sweepFlag, x, y].some((item) => item === null)) break;
      const x2 = isRelative ? cx + x : x;
      const y2 = isRelative ? cy + y : y;
      const segments = arcToCubicSegments({
        x1: cx,
        y1: cy,
        rx,
        ry,
        phiDeg: xAxisRotation,
        largeArcFlag: Number(largeArcFlag) ? 1 : 0,
        sweepFlag: Number(sweepFlag) ? 1 : 0,
        x2,
        y2,
      });
      if (!segments.length) {
        cx = x2;
        cy = y2;
        pushPoint(cx, cy);
        prevUpper = "A";
        lastCubicControlX = null;
        lastCubicControlY = null;
        lastQuadraticControlX = null;
        lastQuadraticControlY = null;
        continue;
      }
      for (const seg of segments) {
        cx = seg.x;
        cy = seg.y;
        pushPoint(cx, cy, {
          type: "cubic",
          x1: toInchesX(seg.c1x, svgWidth),
          y1: toInchesY(seg.c1y, svgHeight),
          x2: toInchesX(seg.c2x, svgWidth),
          y2: toInchesY(seg.c2y, svgHeight),
        });
      }
      prevUpper = "A";
      lastCubicControlX = null;
      lastCubicControlY = null;
      lastQuadraticControlX = null;
      lastQuadraticControlY = null;
      continue;
    }

    // Unsupported command: stop parsing to keep renderer predictable.
    break;
  }

  if (points.length < 2) return [];
  if (!points.some((item) => item && typeof item === "object" && item.close === true)) {
    points.push({ close: true });
  }
  return points;
}

function resolveTextRect(text, attrs, svgWidth, svgHeight) {
  const x = toInchesX(attrs.x, svgWidth);
  const y = toInchesY(attrs.y, svgHeight);
  const fontSize = Math.max(9, Math.min(36, toNumber(attrs["font-size"], 16) * (SLIDE_H / svgHeight) * 540 / 96));
  const width = Math.max(1.2, Math.min(6.8, (String(text || "").length * fontSize * 0.56) / 72));
  const height = Math.max(0.26, Math.min(1.2, (fontSize + 6) / 72));
  return { x, y: Math.max(0, y - height * 0.72), w: width, h: height, fontSize };
}

export function renderSvgSlideToPptx({
  slide,
  pptx,
  sourceSlide = {},
  theme = {},
  designSpec = {},
} = {}) {
  if (!slide || typeof slide.addShape !== "function") {
    return { applied: false, mode: "none", reason: "slide_unavailable" };
  }

  const svgMarkup = resolveSlideSvgMarkup(sourceSlide);
  if (!svgMarkup) {
    return { applied: false, mode: "none", reason: "svg_missing" };
  }

  const parsed = parseSvgElements(svgMarkup);
  const svgWidth = parsed.width || 960;
  const svgHeight = parsed.height || 540;
  const customShapeType = pptx?.shapes?.CUSTOM_GEOMETRY || "custGeom";
  const textTheme = designSpec?.typography || {};
  const bodyFont = String(textTheme.body_font || "Microsoft YaHei");

  const stats = {
    shapeCount: 0,
    customGeometryCount: 0,
    textCount: 0,
  };

  for (const item of parsed.elements) {
    const type = String(item?.type || "").toLowerCase();
    const attrs = item?.attrs && typeof item.attrs === "object" ? item.attrs : {};
    const fillColor = cleanHex(attrs.fill, cleanHex(theme?.primary, "2F7BFF"));
    const strokeColor = cleanHex(attrs.stroke, cleanHex(theme?.borderColor || theme?.light, "1E335E"));

    if (type === "rect") {
      const x = toInchesX(attrs.x, svgWidth);
      const y = toInchesY(attrs.y, svgHeight);
      const w = Math.max(0.06, toInchesX(attrs.width, svgWidth));
      const h = Math.max(0.06, toInchesY(attrs.height, svgHeight));
      slide.addShape("rect", {
        x,
        y,
        w,
        h,
        fill: { color: fillColor },
        line: { color: strokeColor, pt: 0.6 },
      });
      stats.shapeCount += 1;
      continue;
    }

    if (type === "circle" || type === "ellipse") {
      const cx = toInchesX(attrs.cx, svgWidth);
      const cy = toInchesY(attrs.cy, svgHeight);
      const rx = toInchesX(type === "circle" ? attrs.r : attrs.rx, svgWidth);
      const ry = toInchesY(type === "circle" ? attrs.r : attrs.ry, svgHeight);
      slide.addShape("ellipse", {
        x: Math.max(0, cx - rx),
        y: Math.max(0, cy - ry),
        w: Math.max(0.08, rx * 2),
        h: Math.max(0.08, ry * 2),
        fill: { color: fillColor },
        line: { color: strokeColor, pt: 0.6 },
      });
      stats.shapeCount += 1;
      continue;
    }

    if (type === "line") {
      const x1 = toInchesX(attrs.x1, svgWidth);
      const y1 = toInchesY(attrs.y1, svgHeight);
      const x2 = toInchesX(attrs.x2, svgWidth);
      const y2 = toInchesY(attrs.y2, svgHeight);
      slide.addShape("line", {
        x: x1,
        y: y1,
        w: x2 - x1,
        h: y2 - y1,
        line: { color: strokeColor, pt: Math.max(0.4, toNumber(attrs["stroke-width"], 1) * 0.6) },
      });
      stats.shapeCount += 1;
      continue;
    }

    if (type === "path") {
      const points = svgPathToCustomGeometryPoints(attrs.d, { svgWidth, svgHeight });
      if (points.length >= 3) {
        slide.addShape(customShapeType, {
          x: 0,
          y: 0,
          w: SLIDE_W,
          h: SLIDE_H,
          points,
          fill: { color: fillColor },
          line: { color: strokeColor, pt: Math.max(0.3, toNumber(attrs["stroke-width"], 0.8) * 0.5) },
        });
        stats.customGeometryCount += 1;
      }
      continue;
    }

    if (type === "text" && typeof slide.addText === "function") {
      const text = decodeHtmlEntities(item.content || "");
      if (!text) continue;
      const rect = resolveTextRect(text, attrs, svgWidth, svgHeight);
      slide.addText(text, {
        x: rect.x,
        y: rect.y,
        w: rect.w,
        h: rect.h,
        fontFace: bodyFont,
        fontSize: rect.fontSize,
        color: cleanHex(attrs.fill, cleanHex(theme?.darkText, "E8F0FF")),
        margin: 0,
        valign: "mid",
      });
      stats.textCount += 1;
      continue;
    }
  }

  const applied = stats.shapeCount + stats.customGeometryCount + stats.textCount > 0;
  return {
    applied,
    mode: stats.customGeometryCount > 0 ? "custgeom" : "native_shape",
    ...stats,
  };
}
