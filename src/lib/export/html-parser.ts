/**
 * HTML → PPTX 文本属性解析器
 *
 * 将 HTML 富文本解析为 pptxgenjs TextProps[] 数组
 * 支持: <b>, <i>, <u>, <s>, <sup>, <sub>, <ul>/<ol>/<li>, <a>, <p>, <br>
 *
 * 提取自 OpenMAIC (THU-MAIC/OpenMAIC) lib/export/html-parser.ts
 */

export interface AST {
  tagName?: string;
  content?: string;
  attributes?: Array<{ key: string; value: string }>;
  children?: AST[];
}

interface TextSlice {
  text: string;
  options: {
    bold?: boolean;
    italic?: boolean;
    underline?: { color: string; style: string };
    strike?: 'sngStrike';
    superscript?: boolean;
    subscript?: boolean;
    fontSize?: number;
    color?: string;
    fontFace?: string;
    highlight?: string;
    hyperlink?: { url: string };
    bullet?: { type?: string; indent: number };
    paraSpaceBefore?: number;
    indentLevel?: number;
    breakLine?: boolean;
    charSpacing?: number;
    lineSpacingMultiple?: number;
  };
}

/**
 * 简易HTML→AST解析器
 */
export function toAST(html: string): AST[] {
  const ast: AST[] = [];
  let i = 0;

  function parseText(): AST | null {
    const start = i;
    while (i < html.length && html[i] !== '<') i++;
    if (i > start) {
      const text = html.substring(start, i).replace(/&nbsp;/g, ' ')
        .replace(/&gt;/g, '>').replace(/&lt;/g, '<').replace(/&amp;/g, '&');
      if (text) return { content: text };
    }
    return null;
  }

  function parseTag(): AST | null {
    if (html[i] !== '<') return null;

    // Self-closing tags
    if (html.substring(i, i + 4) === '<br>' || html.substring(i, i + 5) === '<br/>') {
      const end = html.indexOf('>', i);
      i = end + 1;
      return { tagName: 'br' };
    }

    // Opening tag
    const tagMatch = html.substring(i).match(/^<(\w+)([^>]*)>/);
    if (!tagMatch) {
      i++;
      return null;
    }

    const tagName = tagMatch[1];
    const attrStr = tagMatch[2];
    i += tagMatch[0].length;

    // Parse attributes
    const attributes: Array<{ key: string; value: string }> = [];
    const attrRegex = /(\w[\w-]*)\s*=\s*"([^"]*)"/g;
    let attrMatch;
    while ((attrMatch = attrRegex.exec(attrStr)) !== null) {
      attributes.push({ key: attrMatch[1], value: attrMatch[2] });
    }

    // Find closing tag
    const closeTag = `</${tagName}>`;
    const closeIndex = html.indexOf(closeTag, i);
    const selfClosing = ['br', 'img', 'hr'];

    if (selfClosing.includes(tagName)) {
      return { tagName, attributes };
    }

    if (closeIndex === -1) {
      // No closing tag found, consume rest
      const children = toASTInternal(html.substring(i));
      i = html.length;
      return { tagName, attributes, children };
    }

    const innerHtml = html.substring(i, closeIndex);
    i = closeIndex + closeTag.length;

    return { tagName, attributes, children: toASTInternal(innerHtml) };
  }

  function toASTInternal(source: string): AST[] {
    const oldHtml = html;
    const oldI = i;
    html = source;
    i = 0;
    const result: AST[] = [];

    while (i < html.length) {
      if (html[i] === '<') {
        const tag = parseTag();
        if (tag) result.push(tag);
      } else {
        const text = parseText();
        if (text) result.push(text);
      }
    }

    html = oldHtml;
    i = oldI;
    return result;
  }

  // Parse main
  while (i < html.length) {
    if (html[i] === '<') {
      const tag = parseTag();
      if (tag) ast.push(tag);
    } else {
      const text = parseText();
      if (text) ast.push(text);
    }
  }

  return ast;
}

/**
 * 将HTML解析为pptxgenjs TextProps数组
 *
 * @param html HTML富文本字符串
 * @param ratioPx2Pt 像素→点的比率
 * @param defaults 默认样式
 */
export function formatHTML(
  html: string,
  ratioPx2Pt: number,
  defaults: { fontSize?: number; fontFace?: string; color?: string } = {},
): TextSlice[] {
  if (!html) return [];

  const ast = toAST(html);
  const slices: TextSlice[] = [];
  let bulletFlag = false;
  let listType: string | null = null;
  let indent = 0;

  function parse(nodes: AST[], baseStyle: Record<string, string> = {}) {
    for (const node of nodes) {
      const isBlock = node.tagName && ['div', 'li', 'p'].includes(node.tagName);

      if (isBlock && slices.length) {
        const last = slices[slices.length - 1];
        if (!last.options) last.options = {};
        last.options.breakLine = true;
      }

      const style = { ...baseStyle };

      // Parse inline style attribute
      const styleAttr = node.attributes?.find(a => a.key === 'style');
      if (styleAttr?.value) {
        for (const item of styleAttr.value.split(';')) {
          const m = item.match(/([^:]+):\s*(.+)/);
          if (m) style[m[1].trim()] = m[2].trim();
        }
      }

      // Tag-based styles
      if (node.tagName === 'em' || node.tagName === 'i') style['font-style'] = 'italic';
      if (node.tagName === 'strong' || node.tagName === 'b') style['font-weight'] = 'bold';
      if (node.tagName === 'u') style['text-decoration'] = 'underline';
      if (node.tagName === 's' || node.tagName === 'strike') style['text-decoration'] = 'line-through';
      if (node.tagName === 'sup') style['vertical-align'] = 'super';
      if (node.tagName === 'sub') style['vertical-align'] = 'sub';
      if (node.tagName === 'a') {
        const href = node.attributes?.find(a => a.key === 'href');
        if (href) style['href'] = href.value;
      }
      if (node.tagName === 'ul') style['list-type'] = 'ul';
      if (node.tagName === 'ol') style['list-type'] = 'ol';
      if (node.tagName === 'li') {
        bulletFlag = true;
        listType = style['list-type'] || 'ul';
      }

      if (node.tagName === 'br') {
        slices.push({ text: '', options: { breakLine: true } });
      } else if (node.content !== undefined) {
        const text = node.content;
        const opts: TextSlice['options'] = {};

        if (style['font-size']) opts.fontSize = parseInt(style['font-size']) / ratioPx2Pt;
        if (style['color']) opts.color = style['color'];
        if (style['background-color']) opts.highlight = style['background-color'];
        if (style['font-weight'] === 'bold') opts.bold = true;
        if (style['font-style'] === 'italic') opts.italic = true;
        if (style['font-family']) opts.fontFace = style['font-family'];
        if (style['href']) opts.hyperlink = { url: style['href'] };

        if (style['text-decoration']?.includes('underline')) {
          opts.underline = { color: opts.color || '#000000', style: 'sng' };
        }
        if (style['text-decoration']?.includes('line-through')) {
          opts.strike = 'sngStrike';
        }

        if (style['vertical-align'] === 'super') opts.superscript = true;
        if (style['vertical-align'] === 'sub') opts.subscript = true;

        if (bulletFlag) {
          const indentPx = (opts.fontSize || defaults.fontSize || 16) * 1.25;
          opts.bullet = {
            type: listType === 'ol' ? 'number' : undefined,
            indent: indentPx,
          };
          opts.paraSpaceBefore = 0.1;
          bulletFlag = false;
        }

        if (indent) {
          opts.indentLevel = indent;
          indent = 0;
        }

        slices.push({ text, options: opts });
      } else if (node.children) {
        parse(node.children, style);
      }
    }
  }

  parse(ast);
  return slices;
}
