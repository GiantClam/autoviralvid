import { renderTemplateContent, renderTemplateCover } from "../minimax/templates/template-renderers.mjs";

const SLIDE_W = 10;
const SLIDE_H = 5.625;

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function makeFakeSlide() {
  return {
    shapes: [],
    texts: [],
    images: [],
    addShape(type, options) {
      this.shapes.push({ type, options });
    },
    addText(text, options) {
      this.texts.push({ text: String(text ?? ""), options: options || {} });
    },
    addImage(options) {
      this.images.push(options || {});
    },
  };
}

function assertInBoundsRect(rect, where, allowNegativeSpan = false) {
  const x = Number(rect?.x ?? 0);
  const y = Number(rect?.y ?? 0);
  const w = Number(rect?.w ?? 0);
  const h = Number(rect?.h ?? 0);
  const x1 = allowNegativeSpan ? Math.min(x, x + w) : x;
  const x2 = allowNegativeSpan ? Math.max(x, x + w) : x + w;
  const y1 = allowNegativeSpan ? Math.min(y, y + h) : y;
  const y2 = allowNegativeSpan ? Math.max(y, y + h) : y + h;
  assert(x1 >= -0.001 && y1 >= -0.001, `${where}: negative origin`);
  if (!allowNegativeSpan) {
    assert(w >= 0 && h >= 0, `${where}: negative size`);
  }
  assert(x2 <= SLIDE_W + 0.001, `${where}: overflow width (${x2})`);
  assert(y2 <= SLIDE_H + 0.001, `${where}: overflow height (${y2})`);
}

function assertNoMojibake(texts) {
  const bad = ["鈥", "锛", "鍙", "鐨", "銆", "闄", "\uFFFD"];
  for (const item of texts) {
    const value = String(item?.text ?? "");
    for (const token of bad) {
      assert(!value.includes(token), `mojibake detected in text: ${value}`);
    }
  }
}

const helpers = {
  FONT_BY_STYLE: {
    soft: { enTitle: "Aptos Display", enBody: "Aptos" },
    pill: { enTitle: "Gill Sans MT", enBody: "Segoe UI" },
  },
  FONT_ZH: "Microsoft YaHei",
  addPageBadge(slide) {
    slide.addShape("roundRect", { x: 9.2, y: 5.1, w: 0.5, h: 0.3 });
  },
  addBulletList(slide, bullets, x, y, w, h) {
    const lines = Array.isArray(bullets) ? bullets.slice(0, 4) : [];
    slide.addText(lines.join("\n"), { x, y, w, h });
  },
};

const theme = {
  bg: "060B17",
  cardBg: "0D1630",
  cardAltBg: "101D3A",
  borderColor: "1E335E",
  primary: "2F7BFF",
  secondary: "12B6F5",
  accent: "18E0D1",
  accentStrong: "22D3EE",
  accentSoft: "1C4FA8",
  darkText: "E8F0FF",
  mutedText: "95A8CC",
  light: "2C446E",
};

{
  const slide = makeFakeSlide();
  const ok = renderTemplateCover({
    templateFamily: "hero_tech_cover",
    slide,
    title: "2026 灵创智能产品技术架构与核心能力剖析",
    subtitle: "连接大模型能力与业务逻辑的开源 LLMOps 平台",
    style: "soft",
    theme,
    helpers,
    sourceSlide: { meta: { presenter: "李雷", organization: "灵创智能" } },
  });
  assert(ok, "cover renderer should return true");
  for (const shape of slide.shapes) assertInBoundsRect(shape.options, "cover-shape", shape.type === "line");
  for (const text of slide.texts) assertInBoundsRect(text.options, "cover-text");
  assertNoMojibake(slide.texts);
}

for (const templateFamily of [
  "architecture_dark_panel",
  "ecosystem_orange_dark",
  "neural_blueprint_light",
  "ops_lifecycle_light",
  "consulting_warm_light",
  "split_media_dark",
  "dashboard_dark",
  "bento_2x2_dark",
  "bento_mosaic_dark",
  "kpi_dashboard_dark",
  "image_showcase_light",
  "process_flow_dark",
  "comparison_cards_light",
  "quote_hero_dark",
]) {
  const slide = makeFakeSlide();
  const ok = renderTemplateContent({
    templateFamily,
    slide,
    title: "测试页",
    bullets: [
      "核心价值提升",
      "可视化编排",
      "数据闭环",
      "全链路监控",
      "部署效率提升 80%",
      "覆盖 200+ 模型",
    ],
    pageNumber: 2,
    theme,
    style: "soft",
    helpers,
    sourceSlide: {
      title: "测试页",
      narration: "用于模板回归测试",
      blocks: [
        {
          block_type: "image",
          content: {
            url: "image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIxMjAwIiBoZWlnaHQ9IjY3NSI+PHJlY3Qgd2lkdGg9IjEyMDAiIGhlaWdodD0iNjc1IiBmaWxsPSIjZGRlZWZmIi8+PC9zdmc+",
          },
        },
        { block_type: "kpi", data: { number: 92, unit: "%", trend: 12, label: "可用率" } },
      ],
    },
  });
  assert(ok, `${templateFamily} renderer should return true`);
  for (const shape of slide.shapes) assertInBoundsRect(shape.options, `${templateFamily}-shape`, shape.type === "line");
  for (const text of slide.texts) assertInBoundsRect(text.options, `${templateFamily}-text`);
  for (const image of slide.images) assertInBoundsRect(image, `${templateFamily}-image`);
  assertNoMojibake(slide.texts);
}

console.log("template-renderers harness passed");
